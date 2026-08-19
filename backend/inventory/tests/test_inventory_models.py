"""Inventory model field-level unit tests (CLI-61).

Focuses on Product field defaults and storage that are not covered by
the existing test_product.py (which covers _apply_stock_delta, __str__,
unique constraints, and low-stock logic).
"""

from decimal import Decimal

from django.test import TestCase

from inventory.models import Product, ProductType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid = 0


def _product(**kwargs):
    global _uid
    _uid += 1
    defaults = {
        "name":          f"محصول آزمایش {_uid}",
        "internal_code": f"IM-{_uid:04d}",
        "product_type":  ProductType.MEDICINE,
        "unit":          "عدد",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Field defaults
# ---------------------------------------------------------------------------

class ProductDefaultsTest(TestCase):
    """Verify every model field that has a default value."""

    def test_initial_current_stock_is_zero(self):
        p = _product()
        self.assertEqual(p.current_stock, Decimal("0"))

    def test_initial_sale_price_is_zero(self):
        p = _product()
        self.assertEqual(p.sale_price, Decimal("0"))

    def test_initial_purchase_price_is_zero(self):
        p = _product()
        self.assertEqual(p.purchase_price, Decimal("0"))

    def test_initial_minimum_stock_is_zero(self):
        p = _product()
        self.assertEqual(p.minimum_stock, Decimal("0"))

    def test_is_active_defaults_to_true(self):
        p = _product()
        self.assertTrue(p.is_active)

    def test_barcode_defaults_to_null(self):
        p = _product()
        self.assertIsNone(p.barcode)

    def test_internal_notes_defaults_to_empty(self):
        p = _product()
        self.assertEqual(p.internal_notes, "")


# ---------------------------------------------------------------------------
# Field storage
# ---------------------------------------------------------------------------

class ProductFieldStorageTest(TestCase):
    """Verify that explicitly-set field values are round-tripped correctly."""

    def test_purchase_price_stored(self):
        p = _product(purchase_price=Decimal("12500.50"))
        p.refresh_from_db()
        self.assertEqual(p.purchase_price, Decimal("12500.50"))

    def test_sale_price_stored(self):
        p = _product(sale_price=Decimal("15000.00"))
        p.refresh_from_db()
        self.assertEqual(p.sale_price, Decimal("15000.00"))

    def test_minimum_stock_stored(self):
        p = _product(minimum_stock=Decimal("5.5"))
        p.refresh_from_db()
        self.assertEqual(p.minimum_stock, Decimal("5.5"))

    def test_unit_stored(self):
        p = _product(unit="ml")
        p.refresh_from_db()
        self.assertEqual(p.unit, "ml")

    def test_product_type_medicine(self):
        p = _product(product_type=ProductType.MEDICINE)
        p.refresh_from_db()
        self.assertEqual(p.product_type, ProductType.MEDICINE)

    def test_product_type_equipment(self):
        p = _product(product_type=ProductType.EQUIPMENT)
        p.refresh_from_db()
        self.assertEqual(p.product_type, ProductType.EQUIPMENT)

    def test_is_active_false_stored(self):
        p = _product(is_active=False)
        p.refresh_from_db()
        self.assertFalse(p.is_active)

    def test_internal_notes_stored(self):
        note = "این دارو در دمای ۲–۸ درجه نگه‌داری شود."
        p = _product(internal_notes=note)
        p.refresh_from_db()
        self.assertEqual(p.internal_notes, note)

    def test_barcode_stored(self):
        p = _product(barcode="8935003420015")
        p.refresh_from_db()
        self.assertEqual(p.barcode, "8935003420015")

    def test_name_stored(self):
        p = _product(name="ایزوفلوران ۱٪")
        p.refresh_from_db()
        self.assertEqual(p.name, "ایزوفلوران ۱٪")

    def test_internal_code_stored(self):
        p = _product(internal_code="CUST-XXYZ")
        p.refresh_from_db()
        self.assertEqual(p.internal_code, "CUST-XXYZ")


# ---------------------------------------------------------------------------
# is_active toggle
# ---------------------------------------------------------------------------

class ProductActiveStatusTest(TestCase):
    """Verify active/inactive status behaves correctly."""

    def test_active_product_has_is_active_true(self):
        p = _product(is_active=True)
        self.assertTrue(p.is_active)

    def test_inactive_product_has_is_active_false(self):
        p = _product(is_active=False)
        self.assertFalse(p.is_active)

    def test_can_toggle_from_active_to_inactive(self):
        p = _product(is_active=True)
        p.is_active = False
        p._skip_stock_guard = True   # needed because save() checks current_stock
        # Use update to avoid the stock guard
        Product.objects.filter(pk=p.pk).update(is_active=False)
        p.refresh_from_db()
        self.assertFalse(p.is_active)

    def test_can_toggle_from_inactive_to_active(self):
        p = _product(is_active=False)
        Product.objects.filter(pk=p.pk).update(is_active=True)
        p.refresh_from_db()
        self.assertTrue(p.is_active)
