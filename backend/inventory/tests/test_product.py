"""Tests for the Product model, serializers, and API endpoints."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import ALLOW_NEGATIVE_STOCK, Product, ProductCategory, ProductType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_category(name, parent=None):
    return ProductCategory.objects.create(name=name, parent=parent)


def make_product(**kwargs):
    defaults = {
        "name":          "ایزوفلوران",
        "internal_code": "MED-001",
        "product_type":  ProductType.MEDICINE,
        "unit":          "ml",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class ProductModelTest(TestCase):

    def setUp(self):
        self.root_daro = ProductCategory.objects.get(name="دارو", parent=None)

    def test_create_product_success(self):
        p = make_product()
        self.assertIsNotNone(p.pk)
        self.assertEqual(p.current_stock, Decimal("0"))

    def test_str_returns_code_and_name(self):
        p = make_product(name="ایزوفلوران", internal_code="MED-001")
        self.assertEqual(str(p), "MED-001 — ایزوفلوران")

    def test_internal_code_unique_constraint(self):
        make_product(internal_code="MED-001")
        with self.assertRaises(IntegrityError):
            make_product(internal_code="MED-001", name="دیگری")

    def test_two_null_barcodes_allowed(self):
        p1 = make_product(internal_code="MED-001", barcode=None)
        p2 = make_product(internal_code="MED-002", barcode=None)
        self.assertIsNone(p1.barcode)
        self.assertIsNone(p2.barcode)

    def test_duplicate_non_null_barcode_raises(self):
        make_product(internal_code="MED-001", barcode="BC-999")
        with self.assertRaises(IntegrityError):
            make_product(internal_code="MED-002", barcode="BC-999")

    def test_current_stock_cannot_be_set_directly(self):
        p = make_product(internal_code="MED-001")
        p.current_stock = Decimal("50")
        with self.assertRaises(ValueError):
            p.save()

    def test_apply_stock_delta_positive(self):
        p = make_product(internal_code="MED-001")
        p._apply_stock_delta(Decimal("10"))
        p.refresh_from_db()
        self.assertEqual(p.current_stock, Decimal("10"))

    def test_apply_stock_delta_negative(self):
        p = make_product(internal_code="MED-001")
        p._apply_stock_delta(Decimal("20"))
        p._apply_stock_delta(Decimal("-5"))
        p.refresh_from_db()
        self.assertEqual(p.current_stock, Decimal("15"))

    def test_apply_stock_delta_below_zero_raises(self):
        """ALLOW_NEGATIVE_STOCK=False: going below zero must raise ValidationError."""
        self.assertFalse(ALLOW_NEGATIVE_STOCK)
        p = make_product(internal_code="MED-001")
        with self.assertRaises(ValidationError):
            p._apply_stock_delta(Decimal("-999"))

    def test_apply_stock_delta_exact_zero_allowed(self):
        p = make_product(internal_code="MED-001")
        p._apply_stock_delta(Decimal("5"))
        p._apply_stock_delta(Decimal("-5"))
        p.refresh_from_db()
        self.assertEqual(p.current_stock, Decimal("0"))

    def test_is_low_stock_true(self):
        p = make_product(internal_code="MED-001", minimum_stock=Decimal("10"))
        p._apply_stock_delta(Decimal("5"))
        self.assertTrue(p.is_low_stock)

    def test_is_low_stock_false_when_minimum_zero(self):
        """Threshold of 0 means no alert is configured — is_low_stock must be False."""
        p = make_product(internal_code="MED-001", minimum_stock=Decimal("0"))
        self.assertFalse(p.is_low_stock)

    def test_is_out_of_stock_true(self):
        p = make_product(internal_code="MED-001")
        self.assertTrue(p.is_out_of_stock)

    def test_is_out_of_stock_false_after_delta(self):
        p = make_product(internal_code="MED-001")
        p._apply_stock_delta(Decimal("1"))
        self.assertFalse(p.is_out_of_stock)

    def test_clean_raises_for_mismatched_category(self):
        root_tajhizat = ProductCategory.objects.get(name="تجهیزات", parent=None)
        child = make_category("دستگاه جراحی", parent=root_tajhizat)
        p = Product(
            name="ایزوفلوران",
            internal_code="MED-001",
            product_type=ProductType.MEDICINE,  # MEDICINE
            category=child,                      # under تجهیزات — mismatch
            unit="ml",
        )
        with self.assertRaises(ValidationError):
            p.clean()

    def test_clean_passes_for_correct_category(self):
        child = make_category("داروی بیهوشی", parent=self.root_daro)
        p = Product(
            name="ایزوفلوران",
            internal_code="MED-001",
            product_type=ProductType.MEDICINE,
            category=child,
            unit="ml",
        )
        p.clean()  # should not raise

    def test_clean_passes_when_category_is_none(self):
        """category=None skips the type-consistency check — always valid."""
        p = Product(
            name="ایزوفلوران",
            internal_code="MED-001",
            product_type=ProductType.MEDICINE,
            category=None,
            unit="ml",
        )
        p.clean()  # should not raise


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class ProductAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="staff", password="pass")
        self.client.force_authenticate(user=self.user)

        self.root_daro = ProductCategory.objects.get(name="دارو",     parent=None)
        self.root_eq   = ProductCategory.objects.get(name="تجهیزات", parent=None)

        self.p1 = make_product(internal_code="MED-001", name="ایزوفلوران",
                               product_type=ProductType.MEDICINE,
                               minimum_stock=Decimal("10"))
        self.p2 = make_product(internal_code="EQ-001", name="پالس اکسیمتر",
                               product_type=ProductType.EQUIPMENT)
        self.inactive = make_product(internal_code="MED-999", name="منسوخ", is_active=False)

        # Give p1 low stock (below minimum)
        self.p1._apply_stock_delta(Decimal("5"))

    def test_list_returns_only_active_by_default(self):
        resp = self.client.get("/api/v1/inventory/products/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = [item["internal_code"] for item in resp.data["results"]]
        self.assertNotIn("MED-999", codes)
        self.assertIn("MED-001", codes)

    def test_list_filter_by_product_type(self):
        resp = self.client.get("/api/v1/inventory/products/?product_type=medicine")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        types = {item["product_type"] for item in resp.data["results"]}
        self.assertEqual(types, {"medicine"})

    def test_list_filter_low_stock(self):
        resp = self.client.get("/api/v1/inventory/products/?low_stock=true")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = [item["internal_code"] for item in resp.data["results"]]
        self.assertIn("MED-001", codes)
        self.assertNotIn("EQ-001", codes)

    def test_low_stock_action_ordered_ascending(self):
        p3 = make_product(internal_code="MED-002", name="کتامین",
                          minimum_stock=Decimal("20"))
        p3._apply_stock_delta(Decimal("3"))  # stock=3, lower than p1's 5

        resp = self.client.get("/api/v1/inventory/products/low_stock/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        stocks = [Decimal(str(item["current_stock"])) for item in resp.data]
        self.assertEqual(stocks, sorted(stocks))  # ascending

    def test_post_with_current_stock_in_payload_is_ignored(self):
        """current_stock in POST payload must be silently dropped — stays 0."""
        resp = self.client.post("/api/v1/inventory/products/", {
            "name":          "پروپوفول",
            "internal_code": "MED-010",
            "product_type":  "medicine",
            "unit":          "ml",
            "current_stock": "999",  # attempted injection
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(str(resp.data["current_stock"])), Decimal("0"))

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/v1/inventory/products/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
