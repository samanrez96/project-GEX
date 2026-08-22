"""Purchase → inventory flow unit tests (CLI-61).

Covers gaps not present in the existing test_purchase.py:
- movement_date matches purchase.purchase_date
- movement description contains vendor name
- cancel() creates SourceType.RETURN movement
- cancel() movement quantity equals original purchase quantity
- confirm + cancel leaves stock neutral
- pending purchase creation does not change product stock

Note: confirm() creates IN movements, idempotency, reference_id, and
multiple-item handling are already tested in test_purchase.py and are
NOT duplicated here.
"""

from decimal import Decimal

from django.test import TestCase

from inventory.models import (
    MovementType,
    Product,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    SourceType,
    StockMovement,
    Vendor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid = 0


def _vendor(name=None):
    global _uid
    _uid += 1
    return Vendor.objects.create(name=name or f"تأمین‌کننده {_uid}")


def _product(**kwargs):
    global _uid
    _uid += 1
    defaults = {
        "name":          f"دارو {_uid}",
        "internal_code": f"PIF-{_uid:04d}",
        "product_type":  ProductType.MEDICINE,
        "unit":          "ml",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def _purchase(vendor=None, **kwargs):
    return Purchase.objects.create(vendor=vendor or _vendor(), **kwargs)


def _item(purchase, product, quantity=Decimal("10"), unit_price=Decimal("500")):
    return PurchaseItem.objects.create(
        purchase=purchase, product=product,
        quantity=quantity, unit_price=unit_price,
    )


# ---------------------------------------------------------------------------
# Pending purchase — no stock change
# ---------------------------------------------------------------------------

class PendingPurchaseNoStockTest(TestCase):

    def test_creating_pending_purchase_does_not_change_stock(self):
        """A pending purchase record must not touch current_stock."""
        product = _product()
        purchase = _purchase()
        _item(purchase, product, quantity=Decimal("50"))

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal("0"))

    def test_creating_pending_purchase_creates_no_movement(self):
        """No StockMovement must be created for a pending purchase."""
        product = _product()
        purchase = _purchase()
        _item(purchase, product)

        self.assertEqual(StockMovement.objects.filter(product=product).count(), 0)


# ---------------------------------------------------------------------------
# confirm() movement field details
# ---------------------------------------------------------------------------

class PurchaseConfirmMovementFieldsTest(TestCase):

    def setUp(self):
        self.vendor  = _vendor(name="شرکت داروسازی آلفا")
        self.product = _product()
        self.purchase = _purchase(vendor=self.vendor)
        _item(self.purchase, self.product, quantity=Decimal("20"))
        self.purchase.confirm()

    def _movement(self):
        return StockMovement.objects.filter(product=self.product).first()

    def test_confirm_movement_type_is_in(self):
        mv = self._movement()
        self.assertEqual(mv.movement_type, MovementType.IN)

    def test_confirm_movement_source_type_is_purchase(self):
        mv = self._movement()
        self.assertEqual(mv.source_type, SourceType.PURCHASE)

    def test_confirm_movement_date_uses_purchase_date(self):
        """movement_date must be the purchase's purchase_date, not timezone.now()."""
        mv = self._movement()
        self.assertEqual(mv.movement_date, self.purchase.purchase_date)

    def test_confirm_movement_description_contains_vendor_name(self):
        mv = self._movement()
        self.assertIn("آلفا", mv.description)

    def test_confirm_reference_id_format(self):
        """reference_id should follow the 'purchase-{pk}' convention."""
        mv = self._movement()
        expected = f"purchase-{self.purchase.pk}"
        self.assertEqual(mv.reference_id, expected)

    def test_confirm_movement_quantity_matches_item(self):
        mv = self._movement()
        self.assertEqual(mv.quantity, Decimal("20"))


# ---------------------------------------------------------------------------
# cancel() movement field details
# ---------------------------------------------------------------------------

class PurchaseCancelMovementFieldsTest(TestCase):

    def setUp(self):
        self.vendor  = _vendor()
        self.product = _product()
        self.purchase = _purchase(vendor=self.vendor)
        _item(self.purchase, self.product, quantity=Decimal("15"))
        self.purchase.confirm()
        self.purchase.cancel()

    def _out_movement(self):
        return StockMovement.objects.filter(
            product=self.product,
            movement_type=MovementType.OUT,
        ).first()

    def test_cancel_creates_out_movement(self):
        mv = self._out_movement()
        self.assertIsNotNone(mv)

    def test_cancel_movement_source_type_is_return(self):
        mv = self._out_movement()
        self.assertEqual(mv.source_type, SourceType.RETURN)

    def test_cancel_movement_quantity_matches_original(self):
        mv = self._out_movement()
        self.assertEqual(mv.quantity, Decimal("15"))

    def test_cancel_pending_purchase_creates_no_out_movement(self):
        """Cancelling a pending (stock_applied=False) purchase must not create OUT."""
        product = _product()
        purchase = _purchase()
        _item(purchase, product, quantity=Decimal("10"))
        # Still PENDING — cancel without applying stock
        purchase.cancel()
        self.assertEqual(
            StockMovement.objects.filter(
                product=product, movement_type=MovementType.OUT
            ).count(),
            0,
        )


# ---------------------------------------------------------------------------
# Full flow: confirm → cancel → stock neutral
# ---------------------------------------------------------------------------

class PurchaseFullFlowTest(TestCase):

    def test_confirm_then_cancel_leaves_stock_at_zero(self):
        product  = _product()
        purchase = _purchase()
        _item(purchase, product, quantity=Decimal("25"))

        purchase.confirm()
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal("25"))

        purchase.cancel()
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal("0"))

    def test_confirm_then_cancel_creates_two_movements(self):
        product  = _product()
        purchase = _purchase()
        _item(purchase, product, quantity=Decimal("10"))

        purchase.confirm()
        purchase.cancel()

        movements = StockMovement.objects.filter(product=product)
        self.assertEqual(movements.count(), 2)
        types = {mv.movement_type for mv in movements}
        self.assertIn(MovementType.IN,  types)
        self.assertIn(MovementType.OUT, types)

    def test_multiple_items_confirm_then_cancel_neutral(self):
        p1 = _product()
        p2 = _product()
        purchase = _purchase()
        _item(purchase, p1, quantity=Decimal("10"))
        _item(purchase, p2, quantity=Decimal("5"))

        purchase.confirm()
        purchase.cancel()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.current_stock, Decimal("0"))
        self.assertEqual(p2.current_stock, Decimal("0"))
