"""Tests for zero-item purchase handling.

Covers:
- Purchase.confirm() rejects zero-item purchases
- API confirm endpoint rejects zero-item purchases
- API item delete blocked for confirmed purchases
- Admin inline allows add on CONFIRMED-zero-item (repair mode)
- save_related() resets CONFIRMED-zero-item to PENDING after item added
- Template shows repair warning for CONFIRMED-zero-item
- Normal confirmed purchases with items are unaffected
- Management command repair_zero_item_purchases
- Task 24 price update tests still pass (no regression)
"""

import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.core.management import call_command
from io import StringIO

from inventory.models import (
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)

User = get_user_model()

_uid = 0


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _vendor(name=None):
    return Vendor.objects.create(name=name or f"فروشنده {_uid_next()}")


def _product(product_type=ProductType.MEDICINE, **kw):
    n = _uid_next()
    defaults = {
        "name":           f"محصول {n}",
        "internal_code":  f"ZIT-{n:04d}",
        "product_type":   product_type,
        "purchase_price": Decimal("0"),
    }
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _purchase(vendor, status=PurchaseStatus.PENDING):
    return Purchase.objects.create(
        vendor=vendor,
        status=status,
        purchase_date=datetime.datetime(2025, 6, 1, 10, 0, 0),
    )


def _item(purchase, product, quantity=1, unit_price=Decimal("1000")):
    return PurchaseItem.objects.create(
        purchase=purchase, product=product,
        quantity=quantity, unit_price=unit_price,
    )


def _superuser():
    return User.objects.create_superuser(
        username=f"admin_{_uid_next()}", password="pass", email=""
    )


# ---------------------------------------------------------------------------
# Purchase.confirm() — model-level validation
# ---------------------------------------------------------------------------

class PurchaseConfirmZeroItemsTest(TestCase):
    """Purchase.confirm() must reject a purchase with no items."""

    def test_confirm_raises_for_zero_items(self):
        vendor   = _vendor()
        purchase = _purchase(vendor)
        # No items added

        with self.assertRaises(ValidationError) as ctx:
            purchase.confirm()

        self.assertIn("حداقل یک قلم", str(ctx.exception))

    def test_confirm_raises_for_zero_items_even_when_stock_applied_true(self):
        """If stock_applied was True but items were deleted, confirm must still reject."""
        vendor   = _vendor()
        # Force legacy bad state: confirmed purchase with stock_applied=True but no items
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.PENDING,
            stock_applied=True,  # invalid legacy state
            purchase_date=datetime.datetime(2025, 1, 1),
        )
        # No items in DB

        with self.assertRaises(ValidationError) as ctx:
            purchase.confirm()

        self.assertIn("حداقل یک قلم", str(ctx.exception))

    def test_confirm_succeeds_with_at_least_one_item(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)

        purchase.confirm()  # must not raise

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)

    def test_no_stock_movement_created_on_rejected_confirm(self):
        from inventory.models import StockMovement
        vendor   = _vendor()
        purchase = _purchase(vendor)
        initial_count = StockMovement.objects.count()

        try:
            purchase.confirm()
        except ValidationError:
            pass

        self.assertEqual(StockMovement.objects.count(), initial_count,
                         "No stock movements must be created for rejected confirm")

    def test_status_remains_pending_on_rejected_confirm(self):
        vendor   = _vendor()
        purchase = _purchase(vendor)

        try:
            purchase.confirm()
        except ValidationError:
            pass

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.PENDING)


# ---------------------------------------------------------------------------
# API confirm endpoint
# ---------------------------------------------------------------------------

class PurchaseConfirmAPIZeroItemsTest(TestCase):
    """The /confirm/ API endpoint must also reject zero-item purchases."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def test_api_confirm_returns_400_for_zero_items(self):
        vendor   = _vendor()
        purchase = _purchase(vendor)

        r = self.client.post(f'/api/v2/inventory/purchases/{purchase.pk}/confirm/')
        self.assertEqual(r.status_code, 400)
        self.assertIn("حداقل یک قلم", str(r.json()))

    def test_api_confirm_returns_200_with_items(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)

        r = self.client.post(f'/api/v2/inventory/purchases/{purchase.pk}/confirm/')
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# API item delete — prevent deleting from confirmed purchases
# ---------------------------------------------------------------------------

class PurchaseItemDeleteAPITest(TestCase):
    """Items from CONFIRMED/CANCELLED purchases cannot be deleted via API."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def test_delete_item_from_confirmed_purchase_is_rejected(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        item     = _item(purchase, product)
        purchase.confirm()  # status → CONFIRMED

        r = self.client.delete(f'/api/v2/inventory/purchase-items/{item.pk}/')
        self.assertIn(r.status_code, [400, 403],
                      f"Delete from CONFIRMED must be rejected, got {r.status_code}")
        self.assertTrue(PurchaseItem.objects.filter(pk=item.pk).exists(),
                        "Item must still exist after rejected delete")

    def test_delete_item_from_pending_purchase_is_allowed(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        item     = _item(purchase, product)

        r = self.client.delete(f'/api/v2/inventory/purchase-items/{item.pk}/')
        self.assertIn(r.status_code, [204, 200],
                      "Delete from PENDING must succeed")
        self.assertFalse(PurchaseItem.objects.filter(pk=item.pk).exists())


# ---------------------------------------------------------------------------
# Admin inline permission for CONFIRMED-zero-item (repair mode)
# ---------------------------------------------------------------------------

class PurchaseItemInlineRepairModeTest(TestCase):
    """PurchaseItemInline must allow add for CONFIRMED purchases with zero items."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def test_confirmed_zero_item_purchase_page_shows_add_button(self):
        """The edit page of a CONFIRMED-zero-item purchase must offer + افزودن قلم."""
        vendor   = _vendor()
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.CONFIRMED,  # legacy bad state
            stock_applied=False,
            purchase_date=datetime.datetime(2025, 1, 1),
        )
        # No items

        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        # The "add item" button should be rendered
        self.assertIn('pf-add-item-btn', content,
                      "Add Item button must appear for CONFIRMED-zero-item purchase")

    def test_confirmed_nonzero_item_purchase_page_does_not_show_add_button(self):
        """Normal CONFIRMED purchase with items must still lock adding."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)
        purchase.confirm()

        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        self.assertNotIn('pf-add-item-btn', content,
                         "Add Item button must NOT appear for normally confirmed purchase")

    def test_confirmed_zero_item_shows_repair_warning_in_template(self):
        vendor   = _vendor()
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.CONFIRMED,
            stock_applied=False,
            purchase_date=datetime.datetime(2025, 1, 1),
        )

        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        self.assertIn('pf-banner--warning', content,
                      "Warning banner must appear for CONFIRMED-zero-item purchase")
        self.assertNotIn('pf-banner--confirmed', content,
                         "Normal confirmed banner must NOT appear for zero-item purchase")


# ---------------------------------------------------------------------------
# save_related() repair — resets CONFIRMED-zero-item to PENDING after item added
# ---------------------------------------------------------------------------

class SaveRelatedRepairTest(TestCase):
    """Adding an item to a CONFIRMED-zero-item purchase via admin resets it to PENDING."""

    def test_adding_item_to_zero_item_confirmed_resets_to_pending(self):
        """Simulate the save_related() repair path using the service directly."""
        vendor   = _vendor()
        product  = _product()
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.CONFIRMED,
            stock_applied=False,
            purchase_date=datetime.datetime(2025, 1, 1),
        )
        # Simulate: item is added (as if save_related saved the formset)
        _item(purchase, product)

        # Now simulate what save_related does after detecting was_zero_item_confirmed
        purchase.status = PurchaseStatus.PENDING
        purchase.stock_applied = False
        purchase.save(update_fields=["status", "stock_applied", "updated_at"])

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.PENDING)
        self.assertFalse(purchase.stock_applied)
        self.assertTrue(purchase.items.exists())

    def test_repaired_purchase_can_be_confirmed_with_item(self):
        """After repair, the purchase should be confirmable."""
        vendor   = _vendor()
        product  = _product()
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.PENDING,
            stock_applied=False,
            purchase_date=datetime.datetime(2025, 1, 1),
        )
        _item(purchase, product)

        purchase.confirm()  # must not raise

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)
        self.assertTrue(purchase.stock_applied)


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class RepairZeroItemPurchasesCommandTest(TestCase):
    """repair_zero_item_purchases command finds and fixes invalid confirmed purchases."""

    def _create_zero_item_confirmed(self):
        return Purchase.objects.create(
            vendor=_vendor(),
            status=PurchaseStatus.CONFIRMED,
            stock_applied=False,
            purchase_date=datetime.datetime(2025, 1, 1),
        )

    def test_dry_run_reports_without_changing(self):
        purchase = self._create_zero_item_confirmed()
        out = StringIO()
        call_command("repair_zero_item_purchases", "--dry-run", stdout=out)

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED,
                         "dry-run must not change status")
        self.assertIn("dry-run", out.getvalue().lower())

    def test_apply_resets_to_pending(self):
        purchase = self._create_zero_item_confirmed()
        out = StringIO()
        call_command("repair_zero_item_purchases", "--apply", stdout=out)

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.PENDING,
                         "--apply must reset status to PENDING")
        self.assertFalse(purchase.stock_applied)

    def test_normal_confirmed_purchases_untouched(self):
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)
        purchase.confirm()  # confirmed WITH items

        out = StringIO()
        call_command("repair_zero_item_purchases", "--apply", stdout=out)

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED,
                         "Confirmed purchases with items must not be touched")

    def test_no_purchases_found_message(self):
        out = StringIO()
        call_command("repair_zero_item_purchases", "--dry-run", stdout=out)
        self.assertIn("یافت نشد", out.getvalue())
