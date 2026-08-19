"""
Focused tests for:
 - Purchase list UI: no موجودی column, 9 columns, full Persian status labels, always-present ویرایش action
 - Stock sync when a CONFIRMED purchase's items are edited via admin
 - Restore action: CANCELLED → PENDING
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vendor(**kwargs):
    defaults = {"name": "تأمین‌کننده تست"}
    defaults.update(kwargs)
    return Vendor.objects.create(**defaults)


def _product(code="SYNC-001", **kwargs):
    defaults = {
        "name":          "محصول تست",
        "internal_code": code,
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


def _item(purchase, product, quantity=Decimal("10"), unit_price=Decimal("1000"), **kwargs):
    return PurchaseItem.objects.create(
        purchase=purchase, product=product,
        quantity=quantity, unit_price=unit_price, **kwargs,
    )


def _change_url(purchase):
    return reverse("admin:inventory_purchase_change", args=[purchase.pk])


def _post_edit(client, purchase, items_data=None, extra=None):
    """POST a minimal purchase change-form, optionally including inline item rows."""
    items_data = items_data or []
    data = {
        "vendor":              str(purchase.vendor.pk),
        "purchase_date":       "1404/01/15",
        "notes":               "",
        "reference_number":    "",
        "items-TOTAL_FORMS":   str(len(items_data)),
        "items-INITIAL_FORMS": str(len(items_data)),
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "_save":               "1",
    }
    for row in items_data:
        data.update(row)
    if extra:
        data.update(extra)
    return client.post(_change_url(purchase), data, follow=True)


def _movements_for(purchase):
    ref = f"edit-purchase-{purchase.pk}"
    return StockMovement.objects.filter(reference_id=ref)


# ---------------------------------------------------------------------------
# Admin client setup mixin
# ---------------------------------------------------------------------------

class AdminMixin(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin_sync", password="pass", email="a@b.com"
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product("SYNC-P1")


# ---------------------------------------------------------------------------
# List page UI — column structure
# ---------------------------------------------------------------------------

class PurchaseListUITest(AdminMixin):

    def _get_list(self):
        return self.client.get(reverse("admin:inventory_purchase_changelist"))

    def test_no_stock_column_header(self):
        resp = self._get_list()
        self.assertNotContains(resp, 'pu-th-stock')

    def test_status_filter_options_present(self):
        resp = self._get_list()
        self.assertContains(resp, 'value="PENDING"')
        self.assertContains(resp, 'value="CONFIRMED"')
        self.assertContains(resp, 'value="CANCELLED"')


# ---------------------------------------------------------------------------
# Detail page — restore button visibility
# ---------------------------------------------------------------------------

class RestoreButtonVisibilityTest(AdminMixin):

    def test_restore_btn_shown_for_cancelled(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        p.cancel()
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, 'id="pf-restore-purchase-btn"')

    def test_restore_btn_absent_for_pending(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertNotContains(resp, 'pf-restore-purchase-btn')

    def test_restore_btn_absent_for_confirmed(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self.client.get(_change_url(p))
        self.assertNotContains(resp, 'pf-restore-purchase-btn')

    def test_confirm_btn_absent_for_cancelled(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        p.cancel()
        resp = self.client.get(_change_url(p))
        self.assertNotContains(resp, 'id="pf-confirm-purchase-btn"')


# ---------------------------------------------------------------------------
# Restore action: CANCELLED → PENDING
# ---------------------------------------------------------------------------

class RestoreActionTest(AdminMixin):

    def _post_restore(self, purchase):
        return self.client.post(
            _change_url(purchase),
            {
                "vendor":              str(purchase.vendor.pk),
                "purchase_date":       "1404/01/15",
                "notes":               "",
                "reference_number":    "",
                "items-TOTAL_FORMS":   "0",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "_action":             "restore",
            },
            follow=True,
        )

    def test_restore_cancelled_sets_pending(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        p.cancel()
        self._post_restore(p)
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.PENDING)

    def test_restore_resets_stock_applied(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        p.cancel()
        self._post_restore(p)
        p.refresh_from_db()
        self.assertFalse(p.stock_applied)

    def test_restore_pending_purchase_is_no_op(self):
        p = _purchase(vendor=self.vendor)
        resp = self._post_restore(p)
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.PENDING)
        # Should show a warning, not an error
        msgs = [str(m) for m in resp.context['messages']]
        self.assertTrue(any("فقط خریدهای لغو شده" in m for m in msgs))


# ---------------------------------------------------------------------------
# Stock sync for CONFIRMED purchase edits
# ---------------------------------------------------------------------------

class ConfirmedPurchaseEditSyncTest(AdminMixin):

    def _inline_row(self, item, quantity=None, unit_price=None, delete=False):
        """Build POST key-value pairs for one existing inline item row."""
        prefix = f"items-0"
        return {
            f"{prefix}-id":           str(item.pk),
            f"{prefix}-purchase":     str(item.purchase.pk),
            f"{prefix}-product":      str(item.product.pk),
            f"{prefix}-quantity":     str(quantity if quantity is not None else item.quantity),
            f"{prefix}-unit_price":   str(unit_price if unit_price is not None else item.unit_price),
            f"{prefix}-notes":        "",
            f"{prefix}-manual_total": "",
            f"{prefix}-DELETE":       "on" if delete else "",
        }

    def _inline_new_row(self, product, quantity, unit_price, prefix_idx=1):
        prefix = f"items-{prefix_idx}"
        return {
            f"{prefix}-id":           "",
            f"{prefix}-purchase":     "",
            f"{prefix}-product":      str(product.pk),
            f"{prefix}-quantity":     str(quantity),
            f"{prefix}-unit_price":   str(unit_price),
            f"{prefix}-notes":        "",
            f"{prefix}-manual_total": "",
            f"{prefix}-DELETE":       "",
        }

    def setUp(self):
        super().setUp()
        self.purchase = _purchase(vendor=self.vendor)
        self.item     = _item(self.purchase, self.product, quantity=Decimal("10"))
        self.purchase.confirm()

    # ── Quantity increase ────────────────────────────────────────────────────

    def test_quantity_increase_creates_IN_movement(self):
        row = self._inline_row(self.item, quantity=Decimal("15"))
        _post_edit(
            self.client, self.purchase,
            items_data=[row],
            extra={"items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1"},
        )
        movements = _movements_for(self.purchase)
        in_mvs = movements.filter(movement_type=MovementType.IN)
        self.assertEqual(in_mvs.count(), 1)
        self.assertEqual(in_mvs.first().quantity, Decimal("5"))

    # ── Quantity decrease ────────────────────────────────────────────────────

    def test_quantity_decrease_creates_OUT_movement(self):
        row = self._inline_row(self.item, quantity=Decimal("6"))
        _post_edit(
            self.client, self.purchase,
            items_data=[row],
            extra={"items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1"},
        )
        movements = _movements_for(self.purchase)
        out_mvs = movements.filter(movement_type=MovementType.OUT)
        self.assertEqual(out_mvs.count(), 1)
        self.assertEqual(out_mvs.first().quantity, Decimal("4"))

    # ── No quantity change — no new movement ─────────────────────────────────

    def test_no_quantity_change_no_movement(self):
        row = self._inline_row(self.item)
        _post_edit(
            self.client, self.purchase,
            items_data=[row],
            extra={"items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1"},
        )
        self.assertEqual(_movements_for(self.purchase).count(), 0)

    # ── Price-only change — no stock movement ────────────────────────────────

    def test_price_change_only_no_movement(self):
        row = self._inline_row(self.item, unit_price=Decimal("9999"))
        _post_edit(
            self.client, self.purchase,
            items_data=[row],
            extra={"items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1"},
        )
        self.assertEqual(_movements_for(self.purchase).count(), 0)

    # ── Item deletion — OUT movement ─────────────────────────────────────────

    def test_item_deletion_creates_OUT_movement(self):
        row = self._inline_row(self.item, delete=True)
        _post_edit(
            self.client, self.purchase,
            items_data=[row],
            extra={"items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1"},
        )
        movements = _movements_for(self.purchase)
        out_mvs = movements.filter(movement_type=MovementType.OUT)
        self.assertEqual(out_mvs.count(), 1)
        self.assertEqual(out_mvs.first().quantity, Decimal("10"))

    # ── New item addition — IN movement ─────────────────────────────────────

    def test_new_item_addition_creates_IN_movement(self):
        product2 = _product("SYNC-P2", name="محصول دوم")
        existing_row = self._inline_row(self.item)
        new_row      = self._inline_new_row(product2, Decimal("5"), Decimal("200"), prefix_idx=1)
        data = {}
        data.update(existing_row)
        # re-key existing row to prefix 0, new to prefix 1
        all_rows_data = {
            "items-TOTAL_FORMS":   "2",
            "items-INITIAL_FORMS": "1",
        }
        all_rows_data.update(existing_row)
        all_rows_data.update(new_row)
        _post_edit(self.client, self.purchase, extra=all_rows_data)
        movements = _movements_for(self.purchase)
        in_mvs = movements.filter(
            movement_type=MovementType.IN,
            product=product2,
        )
        self.assertEqual(in_mvs.count(), 1)
        self.assertEqual(in_mvs.first().quantity, Decimal("5"))

    # ── Reference_id format ──────────────────────────────────────────────────

    def test_movement_reference_id_format(self):
        row = self._inline_row(self.item, quantity=Decimal("12"))
        _post_edit(
            self.client, self.purchase,
            items_data=[row],
            extra={"items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1"},
        )
        mv = _movements_for(self.purchase).first()
        self.assertIsNotNone(mv)
        self.assertEqual(mv.reference_id, f"edit-purchase-{self.purchase.pk}")
        self.assertEqual(mv.source_type, SourceType.PURCHASE)


# ---------------------------------------------------------------------------
# PENDING and CANCELLED purchases — no stock sync on save
# ---------------------------------------------------------------------------

class NonConfirmedEditNoSyncTest(AdminMixin):

    def test_pending_purchase_edit_no_movements(self):
        p    = _purchase(vendor=self.vendor)
        item = _item(p, self.product, quantity=Decimal("10"))
        row  = {
            "items-0-id":           str(item.pk),
            "items-0-purchase":     str(p.pk),
            "items-0-product":      str(self.product.pk),
            "items-0-quantity":     "20",
            "items-0-unit_price":   "1000",
            "items-0-notes":        "",
            "items-0-manual_total": "",
            "items-0-DELETE":       "",
        }
        _post_edit(self.client, p, extra={
            "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1", **row
        })
        ref = f"edit-purchase-{p.pk}"
        self.assertEqual(StockMovement.objects.filter(reference_id=ref).count(), 0)

    def test_cancelled_purchase_edit_no_movements(self):
        p    = _purchase(vendor=self.vendor)
        item = _item(p, self.product, quantity=Decimal("10"))
        p.confirm()
        p.cancel()
        row  = {
            "items-0-id":           str(item.pk),
            "items-0-purchase":     str(p.pk),
            "items-0-product":      str(self.product.pk),
            "items-0-quantity":     "20",
            "items-0-unit_price":   "1000",
            "items-0-notes":        "",
            "items-0-manual_total": "",
            "items-0-DELETE":       "",
        }
        _post_edit(self.client, p, extra={
            "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "1", **row
        })
        ref = f"edit-purchase-{p.pk}"
        self.assertEqual(StockMovement.objects.filter(reference_id=ref).count(), 0)
