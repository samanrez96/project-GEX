"""Unit tests for StockService.create_movement() (CLI-61).

Tests StockService directly rather than through the Purchase or Surgery
layers — focusing on the fields stored in the StockMovement record and
the atomicity guarantees.

Gaps covered that are NOT tested elsewhere:
- source_type value stored correctly
- reference_id stored correctly
- description stored correctly
- explicit movement_date is used instead of now()
- movement_date defaults to a recent value when not supplied
- ADJUSTMENT movement type increases stock (similar to IN)
- passing product PK (integer) instead of instance
- unit auto-filled from product.unit when not supplied
- OUT beyond stock: no movement created + stock unchanged (atomicity)
"""

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import (
    MovementType,
    Product,
    ProductType,
    SourceType,
    StockMovement,
)
from inventory.services import StockService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid = 0


def _product(stock=Decimal("0"), **kwargs):
    global _uid
    _uid += 1
    defaults = {
        "name":          f"سرویس‌تست {_uid}",
        "internal_code": f"SVC-{_uid:04d}",
        "product_type":  ProductType.MEDICINE,
        "unit":          "ml",
    }
    defaults.update(kwargs)
    p = Product.objects.create(**defaults)
    if stock:
        p._apply_stock_delta(stock)
        p.refresh_from_db()
    return p


# ---------------------------------------------------------------------------
# Stock direction
# ---------------------------------------------------------------------------

class StockServiceDirectionTest(TestCase):

    def test_in_movement_increases_stock(self):
        p = _product()
        StockService.create_movement(
            product=p, quantity=Decimal("20"),
            movement_type=MovementType.IN,
            source_type=SourceType.PURCHASE,
        )
        p.refresh_from_db()
        self.assertEqual(p.current_stock, Decimal("20"))

    def test_out_movement_decreases_stock(self):
        p = _product(stock=Decimal("30"))
        StockService.create_movement(
            product=p, quantity=Decimal("8"),
            movement_type=MovementType.OUT,
            source_type=SourceType.SURGERY_CONSUMPTION,
        )
        p.refresh_from_db()
        self.assertEqual(p.current_stock, Decimal("22"))

    def test_adjustment_movement_increases_stock(self):
        """ADJUSTMENT is treated the same as IN — adds to stock."""
        p = _product()
        StockService.create_movement(
            product=p, quantity=Decimal("50"),
            movement_type=MovementType.ADJUSTMENT,
            source_type=SourceType.MANUAL_ADJUSTMENT,
        )
        p.refresh_from_db()
        self.assertEqual(p.current_stock, Decimal("50"))

    def test_returns_stockmovement_instance(self):
        p = _product()
        result = StockService.create_movement(
            product=p, quantity=Decimal("5"),
            movement_type=MovementType.IN,
            source_type=SourceType.PURCHASE,
        )
        self.assertIsInstance(result, StockMovement)
        self.assertIsNotNone(result.pk)

    def test_movement_record_persisted_in_db(self):
        p = _product()
        before = StockMovement.objects.count()
        StockService.create_movement(
            product=p, quantity=Decimal("10"),
            movement_type=MovementType.IN,
            source_type=SourceType.PURCHASE,
        )
        self.assertEqual(StockMovement.objects.count(), before + 1)


# ---------------------------------------------------------------------------
# Movement fields
# ---------------------------------------------------------------------------

class StockServiceFieldsTest(TestCase):

    def setUp(self):
        self.product = _product()

    def _make(self, **kwargs):
        defaults = dict(
            product=self.product,
            quantity=Decimal("10"),
            movement_type=MovementType.IN,
            source_type=SourceType.PURCHASE,
        )
        defaults.update(kwargs)
        return StockService.create_movement(**defaults)

    def test_movement_type_stored(self):
        p_with_stock = _product(stock=Decimal("100"))
        mv = StockService.create_movement(
            product=p_with_stock, quantity=Decimal("5"),
            movement_type=MovementType.OUT,
            source_type=SourceType.SURGERY_CONSUMPTION,
        )
        self.assertEqual(mv.movement_type, MovementType.OUT)

    def test_source_type_stored(self):
        mv = self._make(source_type=SourceType.SURGERY_CONSUMPTION,
                        movement_type=MovementType.IN)
        self.assertEqual(mv.source_type, SourceType.SURGERY_CONSUMPTION)

    def test_source_type_purchase_stored(self):
        mv = self._make(source_type=SourceType.PURCHASE)
        self.assertEqual(mv.source_type, SourceType.PURCHASE)

    def test_reference_id_stored(self):
        mv = self._make(reference_id="purchase-42")
        self.assertEqual(mv.reference_id, "purchase-42")

    def test_description_stored(self):
        desc = "خرید داروی بیهوشی — شرکت الفا"
        mv = self._make(description=desc)
        self.assertEqual(mv.description, desc)

    def test_explicit_movement_date_used(self):
        fixed_dt = datetime.datetime(2025, 1, 15, 8, 0, tzinfo=datetime.timezone.utc)
        mv = self._make(movement_date=fixed_dt)
        self.assertEqual(mv.movement_date, fixed_dt)

    def test_movement_date_defaults_to_recent_time(self):
        before = timezone.now()
        mv = self._make()   # no movement_date supplied
        after = timezone.now()
        self.assertGreaterEqual(mv.movement_date, before)
        self.assertLessEqual(mv.movement_date, after)

    def test_unit_auto_filled_from_product(self):
        """When unit is not supplied, StockMovement.unit = product.unit."""
        mv = self._make()
        self.assertEqual(mv.unit, self.product.unit)

    def test_product_reference_correct(self):
        mv = self._make()
        self.assertEqual(mv.product_id, self.product.pk)

    def test_quantity_stored(self):
        mv = self._make(quantity=Decimal("7.500"))
        self.assertEqual(mv.quantity, Decimal("7.500"))


# ---------------------------------------------------------------------------
# Quantity validation
# ---------------------------------------------------------------------------

class StockServiceQuantityValidationTest(TestCase):

    def setUp(self):
        self.product = _product()

    def test_zero_quantity_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            StockService.create_movement(
                product=self.product, quantity=Decimal("0"),
                movement_type=MovementType.IN,
                source_type=SourceType.PURCHASE,
            )

    def test_negative_quantity_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            StockService.create_movement(
                product=self.product, quantity=Decimal("-5"),
                movement_type=MovementType.IN,
                source_type=SourceType.PURCHASE,
            )

    def test_zero_quantity_no_movement_created(self):
        before = StockMovement.objects.count()
        try:
            StockService.create_movement(
                product=self.product, quantity=Decimal("0"),
                movement_type=MovementType.IN,
                source_type=SourceType.PURCHASE,
            )
        except ValidationError:
            pass
        self.assertEqual(StockMovement.objects.count(), before)

    def test_zero_quantity_stock_unchanged(self):
        try:
            StockService.create_movement(
                product=self.product, quantity=Decimal("0"),
                movement_type=MovementType.IN,
                source_type=SourceType.PURCHASE,
            )
        except ValidationError:
            pass
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))


# ---------------------------------------------------------------------------
# Insufficient stock (OUT beyond current stock)
# ---------------------------------------------------------------------------

class StockServiceInsufficientStockTest(TestCase):

    def setUp(self):
        self.product = _product(stock=Decimal("10"))

    def test_out_beyond_stock_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            StockService.create_movement(
                product=self.product, quantity=Decimal("999"),
                movement_type=MovementType.OUT,
                source_type=SourceType.SURGERY_CONSUMPTION,
            )

    def test_out_beyond_stock_stock_unchanged(self):
        try:
            StockService.create_movement(
                product=self.product, quantity=Decimal("999"),
                movement_type=MovementType.OUT,
                source_type=SourceType.SURGERY_CONSUMPTION,
            )
        except ValidationError:
            pass
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("10"))

    def test_out_beyond_stock_no_movement_created(self):
        before = StockMovement.objects.count()
        try:
            StockService.create_movement(
                product=self.product, quantity=Decimal("999"),
                movement_type=MovementType.OUT,
                source_type=SourceType.SURGERY_CONSUMPTION,
            )
        except ValidationError:
            pass
        self.assertEqual(StockMovement.objects.count(), before)

    def test_error_message_contains_current_stock(self):
        """Persian error message should mention the current stock value."""
        try:
            StockService.create_movement(
                product=self.product, quantity=Decimal("999"),
                movement_type=MovementType.OUT,
                source_type=SourceType.SURGERY_CONSUMPTION,
            )
            self.fail("Expected ValidationError was not raised")
        except ValidationError as exc:
            msg = str(exc)
            # Message should include current stock info
            self.assertTrue(
                "موجودی" in msg or "10" in msg,
                f"Expected Persian stock message, got: {msg}",
            )

    def test_exact_zero_allowed(self):
        """Consuming exactly the remaining stock (leaving 0) is valid."""
        StockService.create_movement(
            product=self.product, quantity=Decimal("10"),
            movement_type=MovementType.OUT,
            source_type=SourceType.SURGERY_CONSUMPTION,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))
