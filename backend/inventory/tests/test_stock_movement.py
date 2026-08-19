"""Tests for StockMovement model and API endpoint."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import (
    ALLOW_NEGATIVE_STOCK,
    MovementType,
    Product,
    ProductType,
    SourceType,
    StockMovement,
)

LIST_URL = "/api/v2/inventory/stock-movements/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _product(**kwargs):
    defaults = {
        "name":          "ایزوفلوران",
        "internal_code": "MED-SM-001",
        "product_type":  ProductType.MEDICINE,
        "unit":          "ml",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def _movement(product, **kwargs):
    defaults = {
        "quantity":      Decimal("10"),
        "movement_type": MovementType.IN,
        "source_type":   SourceType.PURCHASE,
        "movement_date": timezone.now(),
    }
    defaults.update(kwargs)
    return StockMovement.objects.create(product=product, **defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class StockMovementModelTest(TestCase):

    def setUp(self):
        self.product = _product()

    # ---- IN movement -------------------------------------------------------

    def test_in_movement_increases_stock(self):
        _movement(self.product, quantity=Decimal("15"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("15"))

    def test_multiple_in_movements_accumulate(self):
        _movement(self.product, quantity=Decimal("10"))
        _movement(self.product, quantity=Decimal("5"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("15"))

    # ---- OUT movement ------------------------------------------------------

    def test_out_movement_decreases_stock(self):
        _movement(self.product, quantity=Decimal("20"))
        _movement(self.product, quantity=Decimal("7"), movement_type=MovementType.OUT,
                  source_type=SourceType.SURGERY_CONSUMPTION)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("13"))

    def test_out_movement_exact_zero_allowed(self):
        """Consuming the entire stock down to exactly 0 is valid."""
        _movement(self.product, quantity=Decimal("10"))
        _movement(self.product, quantity=Decimal("10"), movement_type=MovementType.OUT,
                  source_type=SourceType.SURGERY_CONSUMPTION)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

    def test_out_movement_prevents_negative_stock(self):
        """ALLOW_NEGATIVE_STOCK=False: OUT beyond current stock raises ValidationError."""
        self.assertFalse(ALLOW_NEGATIVE_STOCK)
        _movement(self.product, quantity=Decimal("5"))
        with self.assertRaises(ValidationError):
            _movement(self.product, quantity=Decimal("10"),
                      movement_type=MovementType.OUT,
                      source_type=SourceType.SURGERY_CONSUMPTION)

    def test_out_on_empty_stock_raises(self):
        """OUT with zero current stock must raise ValidationError."""
        with self.assertRaises(ValidationError):
            _movement(self.product, quantity=Decimal("1"),
                      movement_type=MovementType.OUT,
                      source_type=SourceType.MANUAL_ADJUSTMENT)

    # ---- ADJUSTMENT movement -----------------------------------------------

    def test_adjustment_increases_stock(self):
        _movement(self.product, quantity=Decimal("30"),
                  movement_type=MovementType.ADJUSTMENT,
                  source_type=SourceType.MANUAL_ADJUSTMENT)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("30"))

    # ---- Quantity validation -----------------------------------------------

    def test_clean_rejects_zero_quantity(self):
        sm = StockMovement(
            product=self.product,
            quantity=Decimal("0"),
            movement_type=MovementType.IN,
            source_type=SourceType.PURCHASE,
            movement_date=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            sm.clean()

    def test_clean_rejects_negative_quantity(self):
        sm = StockMovement(
            product=self.product,
            quantity=Decimal("-5"),
            movement_type=MovementType.IN,
            source_type=SourceType.PURCHASE,
            movement_date=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            sm.clean()

    # ---- Unit auto-fill ----------------------------------------------------

    def test_unit_auto_filled_from_product(self):
        sm = _movement(self.product)
        self.assertEqual(sm.unit, "ml")

    def test_explicit_unit_preserved(self):
        sm = _movement(self.product, unit="cc")
        self.assertEqual(sm.unit, "cc")

    # ---- Dunder ------------------------------------------------------------

    def test_str_contains_type_code_and_quantity(self):
        sm = _movement(self.product, quantity=Decimal("5"))
        s = str(sm)
        self.assertIn("MED-SM-001", s)
        self.assertIn("5", s)

    def test_repr(self):
        sm = _movement(self.product)
        self.assertIn("StockMovement", repr(sm))
        self.assertIn("IN", repr(sm))

    # ---- Stock does not roll back on failed OUT ----------------------------

    def test_failed_out_does_not_corrupt_stock(self):
        """If OUT raises ValidationError, the product stock must be unchanged."""
        _movement(self.product, quantity=Decimal("5"))
        self.product.refresh_from_db()
        stock_before = self.product.current_stock  # 5

        try:
            _movement(self.product, quantity=Decimal("100"),
                      movement_type=MovementType.OUT,
                      source_type=SourceType.SURGERY_CONSUMPTION)
        except ValidationError:
            pass

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, stock_before)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class StockMovementAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="staff_sm", password="pass")
        self.client.force_authenticate(user=self.user)
        self.product = _product()

    # ---- Create (POST) -----------------------------------------------------

    def test_create_in_movement_increases_stock(self):
        resp = self.client.post(LIST_URL, {
            "product":       self.product.pk,
            "quantity":      "10.000",
            "movement_type": "IN",
            "source_type":   "PURCHASE",
            "movement_date": "2024-01-01T10:00:00Z",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("10"))

    def test_create_out_movement_decreases_stock(self):
        _movement(self.product, quantity=Decimal("20"))
        resp = self.client.post(LIST_URL, {
            "product":       self.product.pk,
            "quantity":      "8.000",
            "movement_type": "OUT",
            "source_type":   "SURGERY_CONSUMPTION",
            "movement_date": "2024-01-02T10:00:00Z",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("12"))

    def test_create_rejects_zero_quantity(self):
        resp = self.client.post(LIST_URL, {
            "product":       self.product.pk,
            "quantity":      "0",
            "movement_type": "IN",
            "source_type":   "PURCHASE",
            "movement_date": "2024-01-01T10:00:00Z",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_out_beyond_stock_returns_400(self):
        """OUT that would push stock negative returns HTTP 400."""
        resp = self.client.post(LIST_URL, {
            "product":       self.product.pk,
            "quantity":      "999.000",
            "movement_type": "OUT",
            "source_type":   "SURGERY_CONSUMPTION",
            "movement_date": "2024-01-01T10:00:00Z",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unit_defaults_to_product_unit(self):
        resp = self.client.post(LIST_URL, {
            "product":       self.product.pk,
            "quantity":      "5.000",
            "movement_type": "IN",
            "source_type":   "PURCHASE",
            "movement_date": "2024-01-01T10:00:00Z",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["unit"], "ml")

    # ---- List (GET) --------------------------------------------------------

    def test_list_returns_paginated_results(self):
        _movement(self.product, quantity=Decimal("10"))
        _movement(self.product, quantity=Decimal("5"))
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 2)

    def test_list_filter_by_product(self):
        p2 = _product(internal_code="MED-SM-002", name="پروپوفول")
        _movement(self.product, quantity=Decimal("10"))
        _movement(p2, quantity=Decimal("5"))
        resp = self.client.get(LIST_URL, {"product": self.product.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_list_filter_by_movement_type(self):
        _movement(self.product, quantity=Decimal("20"))
        _movement(self.product, quantity=Decimal("5"),
                  movement_type=MovementType.OUT,
                  source_type=SourceType.SURGERY_CONSUMPTION)
        resp = self.client.get(LIST_URL, {"movement_type": "IN"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    # ---- Retrieve (GET detail) ---------------------------------------------

    def test_retrieve_single_movement(self):
        sm = _movement(self.product, quantity=Decimal("10"))
        resp = self.client.get(f"{LIST_URL}{sm.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], sm.pk)
        self.assertEqual(Decimal(str(resp.data["quantity"])), Decimal("10"))

    def test_retrieve_includes_display_labels(self):
        sm = _movement(self.product, quantity=Decimal("10"))
        resp = self.client.get(f"{LIST_URL}{sm.pk}/")
        self.assertIn("movement_type_display", resp.data)
        self.assertIn("source_type_display", resp.data)

    # ---- Forbidden methods -------------------------------------------------

    def test_delete_not_allowed(self):
        sm = _movement(self.product, quantity=Decimal("10"))
        resp = self.client.delete(f"{LIST_URL}{sm.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_put_not_allowed(self):
        sm = _movement(self.product, quantity=Decimal("10"))
        resp = self.client.put(f"{LIST_URL}{sm.pk}/", {
            "product": self.product.pk,
            "quantity": "99",
            "movement_type": "IN",
            "source_type": "PURCHASE",
            "movement_date": "2024-01-01T10:00:00Z",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ---- Auth --------------------------------------------------------------

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
