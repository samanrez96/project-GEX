"""Tests for Surgery / SurgeryConsumptionItem models and API endpoints."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import Product, ProductType, StockMovement
from surgeries.models import Surgery, SurgeryConsumptionItem, SurgeryStatus

SURGERY_LIST_URL = "/api/v1/surgeries/surgeries/"
ITEMS_URL        = "/api/v1/surgeries/consumption-items/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _product(**kwargs):
    defaults = {
        "name":          "ایزوفلوران",
        "internal_code": "SRG-MED-001",
        "product_type":  ProductType.MEDICINE,
        "unit":          "ml",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def _surgery(**kwargs):
    defaults = {
        "patient_name": "محمد رضایی",
        "surgeon_name": "دکتر احمدی",
    }
    defaults.update(kwargs)
    return Surgery.objects.create(**defaults)


def _item(surgery, product, quantity=Decimal("5"), **kwargs):
    return SurgeryConsumptionItem.objects.create(
        surgery=surgery,
        product=product,
        quantity=quantity,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Model tests — Surgery
# ---------------------------------------------------------------------------

class SurgeryModelTest(TestCase):

    def setUp(self):
        self.product = _product()
        self.product._apply_stock_delta(Decimal("100"))  # seed stock

    def test_create_surgery_default_planned(self):
        s = _surgery()
        self.assertEqual(s.status, SurgeryStatus.PLANNED)
        self.assertFalse(s.stock_applied)

    def test_complete_creates_out_movements(self):
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("20"))

        surgery.complete()

        movements = StockMovement.objects.filter(product=self.product)
        # 1 seeding IN + 1 OUT from surgery
        out_movements = movements.filter(movement_type="OUT")
        self.assertEqual(out_movements.count(), 1)
        mv = out_movements.first()
        self.assertEqual(mv.source_type, "SURGERY_CONSUMPTION")
        self.assertEqual(Decimal(str(mv.quantity)), Decimal("20"))

    def test_complete_decreases_product_stock(self):
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("30"))

        surgery.complete()

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("70"))  # 100 - 30

    def test_complete_sets_status_completed(self):
        surgery = _surgery()
        _item(surgery, self.product)
        surgery.complete()
        surgery.refresh_from_db()
        self.assertEqual(surgery.status, SurgeryStatus.COMPLETED)

    def test_complete_sets_stock_applied_true(self):
        surgery = _surgery()
        _item(surgery, self.product)
        surgery.complete()
        surgery.refresh_from_db()
        self.assertTrue(surgery.stock_applied)

    def test_complete_idempotent_no_duplicate_movements(self):
        """Calling complete() twice must NOT create duplicate OUT movements."""
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("10"))

        surgery.complete()
        surgery.complete()  # second call — must be idempotent

        out_count = StockMovement.objects.filter(
            product=self.product, movement_type="OUT"
        ).count()
        self.assertEqual(out_count, 1)

    def test_complete_idempotent_stock_not_doubled(self):
        """Completing twice must NOT deduct stock twice."""
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("10"))

        surgery.complete()
        surgery.complete()

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("90"))  # 100 - 10

    def test_complete_multiple_items(self):
        p2 = _product(internal_code="SRG-MED-002", name="پروپوفول")
        p2._apply_stock_delta(Decimal("50"))

        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("20"))
        _item(surgery, p2,           quantity=Decimal("10"))

        surgery.complete()

        self.product.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("80"))   # 100 - 20
        self.assertEqual(p2.current_stock, Decimal("40"))              # 50 - 10

        out_count = StockMovement.objects.filter(movement_type="OUT").count()
        self.assertEqual(out_count, 2)

    def test_complete_cancelled_raises(self):
        surgery = _surgery(status=SurgeryStatus.CANCELLED)
        with self.assertRaises(ValidationError):
            surgery.complete()

    def test_complete_insufficient_stock_raises(self):
        """Completing with more consumption than available stock raises ValidationError."""
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("999"))  # more than 100 seeded

        with self.assertRaises(ValidationError):
            surgery.complete()

    def test_insufficient_stock_does_not_corrupt_stock(self):
        """If complete() raises, the product stock must be unchanged."""
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("999"))

        self.product.refresh_from_db()
        stock_before = self.product.current_stock

        try:
            surgery.complete()
        except ValidationError:
            pass

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, stock_before)

    def test_reference_id_stored_on_movement(self):
        surgery = _surgery()
        _item(surgery, self.product)
        surgery.complete()

        mv = StockMovement.objects.filter(
            product=self.product, movement_type="OUT"
        ).first()
        self.assertIn(str(surgery.pk), mv.reference_id)

    def test_str(self):
        surgery = _surgery()
        s = str(surgery)
        self.assertIn("محمد رضایی", s)


# ---------------------------------------------------------------------------
# Model tests — SurgeryConsumptionItem
# ---------------------------------------------------------------------------

class SurgeryConsumptionItemModelTest(TestCase):

    def setUp(self):
        self.product = _product()
        self.surgery = _surgery()

    def test_unit_auto_filled_from_product(self):
        item = _item(self.surgery, self.product)
        self.assertEqual(item.unit, "ml")

    def test_explicit_unit_preserved(self):
        item = SurgeryConsumptionItem.objects.create(
            surgery=self.surgery,
            product=self.product,
            quantity=Decimal("5"),
            unit="cc",
        )
        self.assertEqual(item.unit, "cc")

    def test_clean_rejects_zero_quantity(self):
        item = SurgeryConsumptionItem(
            surgery=self.surgery,
            product=self.product,
            quantity=Decimal("0"),
        )
        with self.assertRaises(ValidationError):
            item.clean()

    def test_clean_rejects_negative_quantity(self):
        item = SurgeryConsumptionItem(
            surgery=self.surgery,
            product=self.product,
            quantity=Decimal("-1"),
        )
        with self.assertRaises(ValidationError):
            item.clean()


# ---------------------------------------------------------------------------
# API tests — Surgery
# ---------------------------------------------------------------------------

class SurgeryAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="surgeon", password="pass")
        self.client.force_authenticate(user=self.user)

        self.product = _product()
        self.product._apply_stock_delta(Decimal("100"))  # seed stock

    def test_create_surgery(self):
        resp = self.client.post(SURGERY_LIST_URL, {
            "patient_name": "علی کریمی",
            "surgeon_name": "دکتر موسوی",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], SurgeryStatus.PLANNED)

    def test_list_surgeries(self):
        _surgery()
        _surgery(patient_name="سارا احمدی")
        resp = self.client.get(SURGERY_LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_complete_action_decreases_stock(self):
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("25"))

        resp = self.client.post(f"{SURGERY_LIST_URL}{surgery.pk}/complete/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], SurgeryStatus.COMPLETED)
        self.assertTrue(resp.data["stock_applied"])

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("75"))  # 100 - 25

    def test_complete_insufficient_stock_returns_400(self):
        surgery = _surgery()
        _item(surgery, self.product, quantity=Decimal("999"))

        resp = self.client.post(f"{SURGERY_LIST_URL}{surgery.pk}/complete/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Stock must be unchanged
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("100"))

    def test_complete_cancelled_returns_400(self):
        surgery = _surgery(status=SurgeryStatus.CANCELLED)
        resp = self.client.post(f"{SURGERY_LIST_URL}{surgery.pk}/complete/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_status(self):
        s1 = _surgery()
        _item(s1, self.product)
        s1.complete()

        _surgery(patient_name="بیمار دوم")  # PLANNED

        resp = self.client.get(SURGERY_LIST_URL, {"status": "COMPLETED"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(SURGERY_LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# API tests — SurgeryConsumptionItem
# ---------------------------------------------------------------------------

class SurgeryConsumptionItemAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="nurse", password="pass")
        self.client.force_authenticate(user=self.user)

        self.product = _product()
        self.product._apply_stock_delta(Decimal("100"))
        self.surgery = _surgery()

    def test_create_item(self):
        resp = self.client.post(ITEMS_URL, {
            "surgery":  self.surgery.pk,
            "product":  self.product.pk,
            "quantity": "5.000",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["unit"], "ml")

    def test_cannot_add_item_to_completed_surgery(self):
        _item(self.surgery, self.product, quantity=Decimal("5"))
        self.surgery.complete()

        p2 = _product(internal_code="SRG-MED-003", name="کتامین")
        resp = self.client.post(ITEMS_URL, {
            "surgery":  self.surgery.pk,
            "product":  p2.pk,
            "quantity": "3.000",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_item_rejects_zero_quantity(self):
        resp = self.client.post(ITEMS_URL, {
            "surgery":  self.surgery.pk,
            "product":  self.product.pk,
            "quantity": "0",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
