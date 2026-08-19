"""Tests for Purchase / PurchaseItem models and API endpoints."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import (
    Product,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    StockMovement,
    Vendor,
)

LIST_URL          = "/api/v1/inventory/purchases/"
ITEMS_URL         = "/api/v1/inventory/purchase-items/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vendor(**kwargs):
    defaults = {"name": "تأمین‌کننده آزمایشی"}
    defaults.update(kwargs)
    return Vendor.objects.create(**defaults)


def _product(**kwargs):
    defaults = {
        "name":          "ایزوفلوران",
        "internal_code": "PUR-MED-001",
        "product_type":  ProductType.MEDICINE,
        "unit":          "ml",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def _purchase(vendor=None, **kwargs):
    vendor = vendor or _vendor()
    defaults = {"vendor": vendor}
    defaults.update(kwargs)
    return Purchase.objects.create(**defaults)


def _item(purchase, product, quantity=Decimal("10"), **kwargs):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=quantity,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Model tests — Purchase
# ---------------------------------------------------------------------------

class PurchaseModelTest(TestCase):

    def setUp(self):
        self.vendor  = _vendor()
        self.product = _product()

    def test_create_purchase_default_pending(self):
        p = _purchase(vendor=self.vendor)
        self.assertEqual(p.status, PurchaseStatus.PENDING)
        self.assertFalse(p.stock_applied)

    def test_confirm_creates_in_movements(self):
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("20"))

        purchase.confirm()

        movements = StockMovement.objects.filter(product=self.product)
        self.assertEqual(movements.count(), 1)
        mv = movements.first()
        self.assertEqual(mv.movement_type, "IN")
        self.assertEqual(mv.source_type, "PURCHASE")
        self.assertEqual(Decimal(str(mv.quantity)), Decimal("20"))

    def test_confirm_increases_product_stock(self):
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("15"))

        purchase.confirm()

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("15"))

    def test_confirm_sets_status_confirmed(self):
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product)
        purchase.confirm()
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)

    def test_confirm_sets_stock_applied_true(self):
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product)
        purchase.confirm()
        purchase.refresh_from_db()
        self.assertTrue(purchase.stock_applied)

    def test_confirm_idempotent_no_duplicate_movements(self):
        """Calling confirm() twice must NOT create duplicate stock movements."""
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))

        purchase.confirm()
        purchase.confirm()  # second call — must be idempotent

        movement_count = StockMovement.objects.filter(product=self.product).count()
        self.assertEqual(movement_count, 1)

    def test_confirm_idempotent_stock_not_doubled(self):
        """Confirming twice must NOT double the stock increase."""
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))

        purchase.confirm()
        purchase.confirm()

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("10"))

    def test_confirm_multiple_items(self):
        p2 = _product(internal_code="PUR-MED-002", name="پروپوفول")
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))
        _item(purchase, p2,           quantity=Decimal("5"))

        purchase.confirm()

        self.product.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("10"))
        self.assertEqual(p2.current_stock, Decimal("5"))
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_confirm_cancelled_raises(self):
        purchase = _purchase(vendor=self.vendor, status=PurchaseStatus.CANCELLED)
        with self.assertRaises(ValidationError):
            purchase.confirm()

    def test_confirm_empty_purchase_raises(self):
        """A purchase with no items must not be confirmable."""
        purchase = _purchase(vendor=self.vendor)
        with self.assertRaises(ValidationError):
            purchase.confirm()

    def test_reference_id_stored_on_movement(self):
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product)
        purchase.confirm()

        mv = StockMovement.objects.filter(product=self.product).first()
        self.assertIn(str(purchase.pk), mv.reference_id)

    def test_str(self):
        purchase = _purchase(vendor=self.vendor)
        self.assertIn(self.vendor.name, str(purchase))


# ---------------------------------------------------------------------------
# Model tests — PurchaseItem
# ---------------------------------------------------------------------------

class PurchaseItemModelTest(TestCase):

    def setUp(self):
        self.vendor  = _vendor()
        self.product = _product()
        self.purchase = _purchase(vendor=self.vendor)

    def test_unit_auto_filled_from_product(self):
        item = _item(self.purchase, self.product)
        self.assertEqual(item.unit, "ml")

    def test_explicit_unit_preserved(self):
        item = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product,
            quantity=Decimal("5"),
            unit="cc",
        )
        self.assertEqual(item.unit, "cc")

    def test_clean_rejects_zero_quantity(self):
        item = PurchaseItem(
            purchase=self.purchase,
            product=self.product,
            quantity=Decimal("0"),
        )
        with self.assertRaises(ValidationError):
            item.clean()


# ---------------------------------------------------------------------------
# API tests — Purchase
# ---------------------------------------------------------------------------

class PurchaseAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="buyer", password="pass")
        self.client.force_authenticate(user=self.user)

        self.vendor  = _vendor()
        self.product = _product()

    def test_create_purchase(self):
        resp = self.client.post(LIST_URL, {
            "vendor": self.vendor.pk,
            "reference_number": "INV-001",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], PurchaseStatus.PENDING)

    def test_list_purchases(self):
        _purchase(vendor=self.vendor)
        _purchase(vendor=self.vendor)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_confirm_action_increases_stock(self):
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("25"))

        resp = self.client.post(f"{LIST_URL}{purchase.pk}/confirm/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], PurchaseStatus.CONFIRMED)
        self.assertTrue(resp.data["stock_applied"])

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("25"))

    def test_confirm_empty_purchase_returns_400(self):
        purchase = _purchase(vendor=self.vendor)
        resp = self.client.post(f"{LIST_URL}{purchase.pk}/confirm/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_cancelled_returns_400(self):
        purchase = _purchase(vendor=self.vendor, status=PurchaseStatus.CANCELLED)
        resp = self.client.post(f"{LIST_URL}{purchase.pk}/confirm/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_filter_by_status(self):
        p1 = _purchase(vendor=self.vendor)
        _item(p1, self.product)
        p1.confirm()

        _purchase(vendor=self.vendor)  # PENDING

        resp = self.client.get(LIST_URL, {"status": "CONFIRMED"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)


# ---------------------------------------------------------------------------
# API tests — PurchaseItem
# ---------------------------------------------------------------------------

class PurchaseItemAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="buyer2", password="pass")
        self.client.force_authenticate(user=self.user)

        self.vendor   = _vendor()
        self.product  = _product()
        self.purchase = _purchase(vendor=self.vendor)

    def test_create_item(self):
        resp = self.client.post(ITEMS_URL, {
            "purchase": self.purchase.pk,
            "product":  self.product.pk,
            "quantity": "10.000",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["unit"], "ml")

    def test_cannot_add_item_to_confirmed_purchase(self):
        _item(self.purchase, self.product)
        self.purchase.confirm()

        p2 = _product(internal_code="PUR-MED-003", name="کتامین")
        resp = self.client.post(ITEMS_URL, {
            "purchase": self.purchase.pk,
            "product":  p2.pk,
            "quantity": "5.000",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_item_rejects_zero_quantity(self):
        resp = self.client.post(ITEMS_URL, {
            "purchase": self.purchase.pk,
            "product":  self.product.pk,
            "quantity": "0",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Model tests — cancel()
# ---------------------------------------------------------------------------

class PurchaseCancelModelTest(TestCase):

    def setUp(self):
        self.vendor  = _vendor()
        self.product = _product()

    def _confirmed_purchase(self, qty=Decimal("20")):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=qty)
        p.confirm()
        return p

    def test_cancel_sets_status_cancelled(self):
        p = self._confirmed_purchase()
        p.cancel()
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.CANCELLED)

    def test_cancel_confirmed_creates_out_movement(self):
        p = self._confirmed_purchase(qty=Decimal("20"))
        p.cancel()
        out_movements = StockMovement.objects.filter(
            product=self.product, movement_type="OUT"
        )
        self.assertEqual(out_movements.count(), 1)
        self.assertEqual(out_movements.first().quantity, Decimal("20"))

    def test_cancel_confirmed_decreases_stock(self):
        p = self._confirmed_purchase(qty=Decimal("15"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("15"))

        p.cancel()
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

    def test_cancel_already_cancelled_raises(self):
        p = _purchase(vendor=self.vendor, status=PurchaseStatus.CANCELLED)
        with self.assertRaises(ValidationError):
            p.cancel()

    def test_cancel_pending_no_stock_movement_created(self):
        """Cancelling a PENDING purchase (stock not yet applied) creates no movements."""
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"))
        p.cancel()
        self.assertEqual(StockMovement.objects.filter(product=self.product).count(), 0)

    def test_cancel_pending_sets_status_cancelled(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"))
        p.cancel()
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.CANCELLED)

    def test_cancel_insufficient_stock_raises(self):
        """If downstream consumption has depleted the stock, cancel() must raise."""
        from inventory.models import MovementType, SourceType
        from inventory.services import StockService

        p = self._confirmed_purchase(qty=Decimal("10"))
        # Simulate surgery consuming all the stock
        StockService.create_movement(
            product=self.product,
            quantity=Decimal("10"),
            movement_type=MovementType.OUT,
            source_type=SourceType.SURGERY_CONSUMPTION,
            reference_id="surgery-1",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

        with self.assertRaises(ValidationError):
            p.cancel()

        # Stock must be unchanged (transaction rolled back)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

    def test_full_flow_confirm_cancel_stock_neutral(self):
        """confirm() then cancel() leaves product stock exactly as it started."""
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("30"))
        p.confirm()
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("30"))

        p.cancel()
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

        total_movements = StockMovement.objects.filter(product=self.product).count()
        self.assertEqual(total_movements, 2)  # 1 IN + 1 OUT


# ---------------------------------------------------------------------------
# API tests — cancel action
# ---------------------------------------------------------------------------

class PurchaseCancelAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="canceller", password="pass")
        self.client.force_authenticate(user=self.user)

        self.vendor  = _vendor()
        self.product = _product()

    def test_cancel_action_reverses_stock(self):
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("25"))
        purchase.confirm()
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("25"))

        resp = self.client.post(f"{LIST_URL}{purchase.pk}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], PurchaseStatus.CANCELLED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

    def test_cancel_already_cancelled_returns_400(self):
        purchase = _purchase(vendor=self.vendor, status=PurchaseStatus.CANCELLED)
        resp = self.client.post(f"{LIST_URL}{purchase.pk}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_pending_purchase_ok(self):
        """Cancelling a PENDING purchase requires no stock reversal and succeeds."""
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))
        resp = self.client.post(f"{LIST_URL}{purchase.pk}/cancel/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], PurchaseStatus.CANCELLED)


# ---------------------------------------------------------------------------
# API tests — delete protection
# ---------------------------------------------------------------------------

class PurchaseDeleteProtectionTest(TestCase):
    """Confirmed / stock-applied purchases must not be directly deletable via API."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="deleter", password="pass")
        self.client.force_authenticate(user=self.user)
        self.vendor  = _vendor()
        self.product = _product()

    def test_delete_confirmed_purchase_blocked(self):
        """DELETE on a CONFIRMED purchase must return HTTP 400."""
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))
        purchase.confirm()

        resp = self.client.delete(f"{LIST_URL}{purchase.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_stock_applied_purchase_blocked(self):
        """Even after cancellation, a purchase that once applied stock cannot be deleted.

        The audit trail (StockMovement rows) references this purchase via
        reference_id — deleting it would produce orphaned, untraceable history.
        """
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))
        purchase.confirm()   # stock_applied → True
        purchase.cancel()    # status → CANCELLED, stock_applied stays True

        resp = self.client.delete(f"{LIST_URL}{purchase.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_pending_purchase_allowed(self):
        """A PENDING purchase that never touched inventory can be freely deleted."""
        purchase = _purchase(vendor=self.vendor)
        resp = self.client.delete(f"{LIST_URL}{purchase.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Purchase.objects.filter(pk=purchase.pk).exists())

    def test_delete_cancelled_never_confirmed_allowed(self):
        """A CANCELLED purchase whose stock was never applied can be deleted."""
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))
        purchase.cancel()   # cancelled before confirm → stock_applied stays False

        resp = self.client.delete(f"{LIST_URL}{purchase.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_confirmed_purchase_stock_untouched_after_blocked_delete(self):
        """After a blocked delete, product stock must remain unchanged."""
        purchase = _purchase(vendor=self.vendor)
        _item(purchase, self.product, quantity=Decimal("10"))
        purchase.confirm()

        stock_before = self.product.__class__.objects.get(pk=self.product.pk).current_stock
        self.client.delete(f"{LIST_URL}{purchase.pk}/")
        stock_after = self.product.__class__.objects.get(pk=self.product.pk).current_stock

        self.assertEqual(stock_before, stock_after)


# ---------------------------------------------------------------------------
# API tests — status is read-only
# ---------------------------------------------------------------------------

class PurchaseStatusReadOnlyTest(TestCase):
    """status must only change via confirm/ or cancel/ actions, never via PATCH/PUT."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="patcher", password="pass")
        self.client.force_authenticate(user=self.user)
        self.vendor  = _vendor()
        self.product = _product()

    def test_patch_status_directly_is_ignored(self):
        """PATCH with status=CONFIRMED must not change status (field is read-only)."""
        purchase = _purchase(vendor=self.vendor)
        resp = self.client.patch(
            f"{LIST_URL}{purchase.pk}/",
            {"status": "CONFIRMED"},
            format="json",
        )
        # Request succeeds (200) but status is not changed — it's read-only
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.PENDING)

    def test_put_status_directly_is_ignored(self):
        """PUT must not change status even when included in the payload."""
        purchase = _purchase(vendor=self.vendor)
        resp = self.client.put(
            f"{LIST_URL}{purchase.pk}/",
            {
                "vendor": self.vendor.pk,
                "reference_number": "REF-99",
                "status": "CONFIRMED",
            },
            format="json",
        )
        self.assertIn(resp.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.PENDING)


# ---------------------------------------------------------------------------
# API tests — price_history action
# ---------------------------------------------------------------------------

PRICE_HISTORY_URL = f"{LIST_URL}price_history/"


class PurchasePriceHistoryAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="historian", password="pass")
        self.client.force_authenticate(user=self.user)

        self.vendor  = _vendor()
        self.product = _product()

    def _confirmed_purchase_with_price(self, unit_price, qty=Decimal("10")):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=qty, unit_price=unit_price)
        p.confirm()
        return p

    def test_price_history_requires_product_param(self):
        resp = self.client.get(PRICE_HISTORY_URL)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_price_history_returns_confirmed_only(self):
        self._confirmed_purchase_with_price(Decimal("100"))
        # PENDING purchase — must NOT appear
        pending = _purchase(vendor=self.vendor)
        _item(pending, self.product, quantity=Decimal("5"), unit_price=Decimal("200"))

        resp = self.client.get(PRICE_HISTORY_URL, {"product": self.product.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_price_history_correct_fields(self):
        self._confirmed_purchase_with_price(Decimal("500"), qty=Decimal("3"))
        resp = self.client.get(PRICE_HISTORY_URL, {"product": self.product.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = resp.data[0]
        self.assertIn("purchase_date", row)
        self.assertIn("vendor",        row)
        self.assertIn("vendor_name",   row)
        self.assertIn("unit_price",    row)
        self.assertIn("quantity",      row)
        self.assertEqual(row["vendor_name"], self.vendor.name)

    def test_price_history_no_pagination(self):
        """All data points returned without wrapping envelope."""
        for price in [100, 200, 300]:
            self._confirmed_purchase_with_price(Decimal(str(price)))
        resp = self.client.get(PRICE_HISTORY_URL, {"product": self.product.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Plain list, not paginated envelope
        self.assertIsInstance(resp.data, list)
        self.assertEqual(len(resp.data), 3)

    def test_price_history_excludes_other_products(self):
        other = _product(internal_code="PH-OTHER-001", name="محصول دیگر")
        p = _purchase(vendor=self.vendor)
        _item(p, other, quantity=Decimal("5"), unit_price=Decimal("999"))
        p.confirm()
        self._confirmed_purchase_with_price(Decimal("100"))

        resp = self.client.get(PRICE_HISTORY_URL, {"product": self.product.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_price_history_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(PRICE_HISTORY_URL, {"product": self.product.pk})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
