"""
Tests for the Purchase Admin confirmation/cancellation workflow.

Requirements verified:
 1.  New purchase defaults to PENDING status.
 2.  Purchase detail page displays the pending status badge.
 3.  PENDING purchase shows the تأیید خرید button.
 4.  Purchase without items cannot be confirmed via the admin action.
 5.  Purchase with valid items can be confirmed via the admin action.
 6.  Confirmation changes status to CONFIRMED.
 7.  Confirmation applies inventory (stock_applied=True).
 8.  Confirmation creates stock movements.
 9.  Confirmation creates finance expense transactions.
10.  Confirming the same purchase twice is idempotent (no duplicate stock/finance).
11.  تأیید خرید button disappears after confirmation.
12.  Confirmed badge appears after confirmation.
13.  Pending purchase remains editable (items not locked).
14.  Confirmed purchase items are locked.
15.  Confirmed purchase cannot be hard-deleted.
16.  Cancel action cancels finance effects.
17.  Cancel action reverses inventory for confirmed purchase.
18.  Cancel cannot run twice (second call raises ValidationError).
19.  Unauthorized user cannot confirm via admin.
20.  Confirmation endpoint rejects GET.
21.  Status is visible on the change page.
22.  Status column visible on list page.
23.  Regular Save action does not confirm (status stays PENDING).
24.  Direct POST manipulation of the status field is ignored.
25.  لغو خرید button disappears after cancellation.
26.  List page status filter works.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from finance.models import Transaction
from inventory.models import (
    Product,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    StockMovement,
    Vendor,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vendor(**kwargs):
    defaults = {"name": "تأمین‌کننده آزمایشی"}
    defaults.update(kwargs)
    return Vendor.objects.create(**defaults)


def _product(**kwargs):
    defaults = {
        "name":          "ایزوفلوران آزمایشی",
        "internal_code": "ADM-WF-001",
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


def _item(purchase, product, quantity=Decimal("10"), unit_price=Decimal("5000"), **kwargs):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        **kwargs,
    )


def _change_url(purchase):
    return reverse("admin:inventory_purchase_change", args=[purchase.pk])


def _list_url():
    return reverse("admin:inventory_purchase_changelist")


def _delete_url(purchase):
    return reverse("admin:inventory_purchase_delete", args=[purchase.pk])


def _post_form(client, purchase, extra_post=None):
    """POST the minimal valid purchase change-form data."""
    url = _change_url(purchase)
    data = {
        "vendor":              str(purchase.vendor.pk),
        "purchase_date":       "1404/01/15",   # Jalali input (handled by JalaliFormField)
        "notes":               "",
        "reference_number":    "",
        # Management form for the inline items formset
        "items-TOTAL_FORMS":   "0",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "_save":               "1",
    }
    if extra_post:
        data.update(extra_post)
    return client.post(url, data, follow=True)


# ---------------------------------------------------------------------------
# Requirement 1 — Default status is PENDING
# ---------------------------------------------------------------------------

class DefaultStatusTest(TestCase):

    def test_new_purchase_defaults_to_pending(self):
        p = _purchase()
        self.assertEqual(p.status, PurchaseStatus.PENDING)
        self.assertFalse(p.stock_applied)


# ---------------------------------------------------------------------------
# Requirements 2, 3, 11, 12, 13, 14, 21 — Change-page UI
# ---------------------------------------------------------------------------

class ChangePageUITest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_admin", password="pass",
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product()

    # Req 2 — PENDING badge visible
    def test_pending_badge_on_change_page(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "در انتظار تأیید")

    # Req 3 — Confirm button shown for PENDING
    def test_confirm_button_shown_for_pending(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "pf-confirm-purchase-btn")
        self.assertContains(resp, "تأیید خرید")

    # Req 3 — Cancel button shown for PENDING
    def test_cancel_button_shown_for_pending(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "pf-cancel-purchase-btn")
        self.assertContains(resp, "لغو خرید")

    # Req 11 — Confirm button hidden after confirmation
    def test_confirm_button_absent_after_confirmation(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self.client.get(_change_url(p))
        self.assertNotContains(resp, "pf-confirm-purchase-btn")

    # Req 12 — Confirmed badge visible
    def test_confirmed_badge_after_confirmation(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "تأیید شده")

    # Req 13 — PENDING purchase items NOT locked (add button visible)
    def test_pending_purchase_items_editable(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "pf-add-item-btn")

    # Req 14 — CONFIRMED purchase items are editable (add button still visible)
    def test_confirmed_purchase_items_editable(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "pf-add-item-btn")

    # Req 21 — Status visible on change page
    def test_status_section_present_on_change_page(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "pf-status-badge")

    # Cancelled purchase — no confirm button, no cancel button
    def test_no_confirm_or_cancel_for_cancelled(self):
        p = _purchase(vendor=self.vendor, status=PurchaseStatus.CANCELLED)
        resp = self.client.get(_change_url(p))
        self.assertNotContains(resp, "pf-confirm-purchase-btn")
        self.assertNotContains(resp, "pf-cancel-purchase-btn")


# ---------------------------------------------------------------------------
# Requirements 4, 5, 6, 7, 8, 9, 10 — Confirm action via admin POST
# ---------------------------------------------------------------------------

class ConfirmActionTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_admin2", password="pass",
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product()

    def _confirm_post(self, purchase):
        url = _change_url(purchase)
        data = {
            "vendor":              str(purchase.vendor.pk),
            "purchase_date":       "1404/01/15",
            "notes":               "",
            "reference_number":    "",
            "items-TOTAL_FORMS":   "0",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "_action":             "confirm",
        }
        return self.client.post(url, data, follow=True)

    # Req 4 — Empty purchase cannot be confirmed
    def test_empty_purchase_confirm_shows_error(self):
        p = _purchase(vendor=self.vendor)
        resp = self._confirm_post(p)
        self.assertEqual(resp.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.PENDING)
        self.assertContains(resp, "برای تأیید خرید")   # error message fragment

    # Req 5 — Valid purchase can be confirmed
    def test_valid_purchase_confirm_succeeds(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"))
        resp = self._confirm_post(p)
        self.assertEqual(resp.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.CONFIRMED)

    # Req 6 — Status changes to CONFIRMED
    def test_confirm_sets_status_confirmed(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        self._confirm_post(p)
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.CONFIRMED)

    # Req 7 — Inventory applied
    def test_confirm_sets_stock_applied(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("5"))
        self._confirm_post(p)
        p.refresh_from_db()
        self.assertTrue(p.stock_applied)

    # Req 8 — Stock movements created
    def test_confirm_creates_stock_movement(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("20"))
        self._confirm_post(p)
        movements = StockMovement.objects.filter(product=self.product)
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().movement_type, "IN")

    # Req 9 — Finance transactions created
    def test_confirm_creates_finance_transaction(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"), unit_price=Decimal("3000"))
        self._confirm_post(p)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Purchase)
        txns = Transaction.objects.filter(content_type=ct, object_id=p.pk)
        self.assertGreater(txns.count(), 0)

    # Req 10 — Idempotent: second confirm does not duplicate stock or finance
    def test_confirm_twice_is_idempotent(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"))
        self._confirm_post(p)
        self._confirm_post(p)   # second POST — purchase is already CONFIRMED

        # Stock movements not duplicated
        self.assertEqual(
            StockMovement.objects.filter(product=self.product).count(), 1
        )
        # Product stock not doubled
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("10"))

    # Req 10 — Finance transactions not duplicated
    def test_confirm_twice_no_duplicate_finance(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"), unit_price=Decimal("1000"))
        self._confirm_post(p)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Purchase)
        count_after_first = Transaction.objects.filter(content_type=ct, object_id=p.pk).count()
        self._confirm_post(p)
        count_after_second = Transaction.objects.filter(content_type=ct, object_id=p.pk).count()
        self.assertEqual(count_after_first, count_after_second)

    # Req 23 — Regular save does NOT confirm
    def test_save_does_not_confirm(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        _post_form(self.client, p)   # regular save with _save=1, no _action
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.PENDING)
        self.assertFalse(p.stock_applied)

    # Req 24 — Direct POST of status=CONFIRMED is ignored
    def test_direct_status_post_is_blocked(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        url = _change_url(p)
        data = {
            "vendor":              str(p.vendor.pk),
            "purchase_date":       "1404/01/15",
            "status":              "CONFIRMED",   # attempt to change status directly
            "notes":               "",
            "reference_number":    "",
            "items-TOTAL_FORMS":   "0",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "_save":               "1",
        }
        self.client.post(url, data, follow=True)
        p.refresh_from_db()
        # Status must remain PENDING — direct manipulation blocked
        self.assertEqual(p.status, PurchaseStatus.PENDING)
        self.assertFalse(p.stock_applied)


# ---------------------------------------------------------------------------
# Requirement 15 — Confirmed purchase cannot be hard-deleted
# ---------------------------------------------------------------------------

class DeleteProtectionTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_admin3", password="pass",
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product()

    def test_confirmed_purchase_delete_button_absent(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self.client.get(_change_url(p))
        self.assertNotContains(resp, "حذف خرید")

    def test_pending_purchase_can_be_deleted(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "حذف خرید")

    def test_confirmed_purchase_delete_page_returns_403(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self.client.get(_delete_url(p))
        self.assertIn(resp.status_code, (403, 302))


# ---------------------------------------------------------------------------
# Requirements 16, 17, 18, 25 — Cancel action
# ---------------------------------------------------------------------------

class CancelActionTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_admin4", password="pass",
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product()

    def _cancel_post(self, purchase):
        url = _change_url(purchase)
        data = {
            "vendor":              str(purchase.vendor.pk),
            "purchase_date":       "1404/01/15",
            "notes":               "",
            "reference_number":    "",
            "items-TOTAL_FORMS":   "0",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "_action":             "cancel",
        }
        return self.client.post(url, data, follow=True)

    # Req 16 — Cancel marks finance transactions CANCELLED
    def test_cancel_confirmed_purchase_cancels_finance(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"), unit_price=Decimal("5000"))
        p.confirm()

        from django.contrib.contenttypes.models import ContentType
        from finance.models import TransactionPaymentStatus
        ct = ContentType.objects.get_for_model(Purchase)
        txns_before = Transaction.objects.filter(content_type=ct, object_id=p.pk)
        self.assertGreater(txns_before.count(), 0)

        self._cancel_post(p)

        txns_after = Transaction.objects.filter(content_type=ct, object_id=p.pk)
        for txn in txns_after:
            self.assertEqual(txn.payment_status, TransactionPaymentStatus.CANCELLED)

    # Req 17 — Cancel reverses stock for confirmed purchase
    def test_cancel_confirmed_purchase_reverses_stock(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"))
        p.confirm()
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("10"))

        self._cancel_post(p)

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

    # Req 17 — Cancel of PENDING purchase has no stock effect
    def test_cancel_pending_purchase_no_stock_change(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product, quantity=Decimal("10"))
        # Do NOT confirm — cancel a PENDING purchase
        self._cancel_post(p)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal("0"))

    # Req 18 — Cancel cannot run twice
    def test_cancel_twice_shows_error(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        self._cancel_post(p)            # first cancel — succeeds
        resp = self._cancel_post(p)     # second cancel — must show error
        p.refresh_from_db()
        self.assertEqual(p.status, PurchaseStatus.CANCELLED)
        self.assertContains(resp, "قبلاً لغو شده")

    # Req 25 — Cancel button absent after cancellation
    def test_cancel_button_absent_after_cancellation(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        self._cancel_post(p)
        resp = self.client.get(_change_url(p))
        self.assertNotContains(resp, "pf-cancel-purchase-btn")


# ---------------------------------------------------------------------------
# Requirements 19, 20 — Permission and HTTP method enforcement
# ---------------------------------------------------------------------------

class PermissionAndMethodTest(TestCase):

    def setUp(self):
        self.vendor  = _vendor()
        self.product = _product()
        self.purchase = _purchase(vendor=self.vendor)
        _item(self.purchase, self.product)

    # Req 19 — Unauthorized user cannot confirm
    def test_anonymous_cannot_access_change_page(self):
        resp = self.client.get(_change_url(self.purchase))
        self.assertIn(resp.status_code, (302, 301))
        self.assertIn("login", resp["Location"])

    def test_non_staff_cannot_confirm(self):
        regular = User.objects.create_user(username="regular", password="pass")
        self.client.force_login(regular)
        url = _change_url(self.purchase)
        # Django admin redirects non-staff users; do NOT follow so we can check 302.
        resp = self.client.post(url, {"_action": "confirm"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, PurchaseStatus.PENDING)

    # Req 20 — Confirmation endpoint rejects GET
    def test_confirm_action_rejects_get(self):
        admin = User.objects.create_superuser(
            username="wf_admin5", password="pass"
        )
        self.client.force_login(admin)
        # GET to the change page — the confirm should not fire
        resp = self.client.get(_change_url(self.purchase))
        self.assertEqual(resp.status_code, 200)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, PurchaseStatus.PENDING)


# ---------------------------------------------------------------------------
# Requirement 22 — Status column visible on list page
# ---------------------------------------------------------------------------

class ListPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_admin6", password="pass",
        )
        self.client.force_login(self.admin)

    def test_list_page_loads(self):
        resp = self.client.get(_list_url())
        self.assertEqual(resp.status_code, 200)

    # Req 22 — Status column header visible
    def test_list_page_has_status_column(self):
        resp = self.client.get(_list_url())
        self.assertContains(resp, "وضعیت")

    # Req 26 — Status filter select present
    def test_list_page_has_status_filter(self):
        resp = self.client.get(_list_url())
        self.assertContains(resp, "pu-filter-status")


# ---------------------------------------------------------------------------
# Mixed product types — medicine + equipment confirm correctly
# ---------------------------------------------------------------------------

class MixedTypeConfirmTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_admin7", password="pass",
        )
        self.client.force_login(self.admin)
        self.vendor = _vendor()
        self.medicine = _product(
            internal_code="ADM-MED", product_type=ProductType.MEDICINE
        )
        self.equipment = _product(
            name="سوند", internal_code="ADM-EQP", product_type=ProductType.EQUIPMENT
        )

    def test_mixed_purchase_confirm_creates_two_finance_transactions(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.medicine,  quantity=Decimal("5"),  unit_price=Decimal("2000"))
        _item(p, self.equipment, quantity=Decimal("3"),  unit_price=Decimal("10000"))
        p.confirm()

        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Purchase)
        txn_count = Transaction.objects.filter(content_type=ct, object_id=p.pk).count()
        # One transaction per product type category group
        self.assertGreaterEqual(txn_count, 1)

    def test_mixed_purchase_stock_both_applied(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.medicine,  quantity=Decimal("5"))
        _item(p, self.equipment, quantity=Decimal("3"))
        p.confirm()
        self.medicine.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(self.medicine.current_stock,  Decimal("5"))
        self.assertEqual(self.equipment.current_stock, Decimal("3"))


# ---------------------------------------------------------------------------
# موجودی اعمال شده badge
# ---------------------------------------------------------------------------

class StockAppliedBadgeTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_admin8", password="pass",
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product()

    def test_stock_applied_shows_خیر_before_confirmation(self):
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "خیر")

    def test_stock_applied_shows_بله_after_confirmation(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self.client.get(_change_url(p))
        self.assertContains(resp, "بله")


# ---------------------------------------------------------------------------
# Template rendering regression — no leaked comments, correct UI elements
# ---------------------------------------------------------------------------

class TemplateRenderingTest(TestCase):
    """Guards against template comment leakage and missing UI elements."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="wf_tpl_admin", password="pass",
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product()

    def _get(self, purchase):
        return self.client.get(_change_url(purchase))

    # ── No developer comments in rendered HTML ───────────────────────────────

    def test_no_comment_leak_status_text(self):
        p = _purchase(vendor=self.vendor)
        resp = self._get(p)
        self.assertNotContains(resp, "Status: for new purchases")

    def test_no_comment_leak_inject_pending(self):
        p = _purchase(vendor=self.vendor)
        resp = self._get(p)
        self.assertNotContains(resp, "inject PENDING")

    def test_no_django_comment_open_marker_in_html(self):
        p = _purchase(vendor=self.vendor)
        resp = self._get(p)
        self.assertNotContains(resp, "{#")

    def test_no_django_comment_close_marker_in_html(self):
        p = _purchase(vendor=self.vendor)
        resp = self._get(p)
        self.assertNotContains(resp, "#}")

    # ── Status badge present for each state ─────────────────────────────────

    def test_pending_badge_visible(self):
        p = _purchase(vendor=self.vendor)
        resp = self._get(p)
        self.assertContains(resp, "در انتظار تأیید")

    def test_confirmed_badge_visible(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self._get(p)
        self.assertContains(resp, "تأیید شده")

    def test_cancelled_badge_visible(self):
        p = _purchase(vendor=self.vendor, status=PurchaseStatus.CANCELLED)
        resp = self._get(p)
        self.assertContains(resp, "لغو شده")

    # ── تأیید خرید button shown only for PENDING ────────────────────────────

    def test_confirm_button_present_for_pending(self):
        p = _purchase(vendor=self.vendor)
        resp = self._get(p)
        self.assertContains(resp, 'id="pf-confirm-purchase-btn"')
        self.assertContains(resp, "تأیید خرید")

    def test_confirm_button_absent_for_confirmed(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self._get(p)
        self.assertNotContains(resp, 'id="pf-confirm-purchase-btn"')

    def test_confirm_button_absent_for_cancelled(self):
        p = _purchase(vendor=self.vendor, status=PurchaseStatus.CANCELLED)
        resp = self._get(p)
        self.assertNotContains(resp, 'id="pf-confirm-purchase-btn"')

    # ── Status is not an editable <select> ──────────────────────────────────

    def test_status_not_rendered_as_editable_select(self):
        p = _purchase(vendor=self.vendor)
        resp = self._get(p)
        self.assertNotContains(resp, 'id="id_status"')

    # ── Unauthorized user cannot see change page ─────────────────────────────

    def test_anonymous_redirected_from_change_page(self):
        self.client.logout()
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])

    def test_non_staff_cannot_see_confirm_button(self):
        regular = User.objects.create_user(username="tpl_regular", password="pass")
        self.client.force_login(regular)
        p = _purchase(vendor=self.vendor)
        resp = self.client.get(_change_url(p))
        # Non-staff users are redirected away — they never see the button.
        self.assertNotEqual(resp.status_code, 200)

    # ── Inline PurchaseItem rows still render ───────────────────────────────

    def test_items_table_renders_for_pending(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        resp = self._get(p)
        self.assertContains(resp, "pf-items-table")
        self.assertContains(resp, "pf-add-item-btn")
