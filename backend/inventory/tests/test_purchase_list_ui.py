"""
Focused tests for the Purchase list page (/admin/inventory/purchase/).

Covers:
 - pu-th-actions header class is absent (عملیات column removed).
 - No pu-cell-actions cell in the JS source.
 - Status column renders correctly for all three statuses via the API.
 - Status rendering uses Purchase.status (not stock_applied).
 - Empty-state colspan matches final column count (8).
 - Loading-state skeleton matches final column count (8).
 - Row navigation to Purchase change page is intact.
 - Status filter works for all three statuses.
"""

import os
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import (
    Product,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)

User = get_user_model()

EXPECTED_COLUMNS = 8  # #, محصول, تأمین‌کننده, تاریخ, اقلام, مبلغ تک, مبلغ کل, وضعیت

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_JS_PATH = os.path.join(
    _PROJECT_ROOT, "static", "admin", "js", "purchase_list.js"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vendor(**kw):
    return Vendor.objects.create(name=kw.pop("name", "تأمین‌کننده تست"), **kw)


def _product(**kw):
    return Product.objects.create(
        name=kw.pop("name", "محصول تست"),
        internal_code=kw.pop("internal_code", "LST-001"),
        product_type=kw.pop("product_type", ProductType.MEDICINE),
        unit=kw.pop("unit", "ml"),
        **kw,
    )


def _purchase(vendor=None, **kw):
    return Purchase.objects.create(vendor=vendor or _vendor(), **kw)


def _item(purchase, product, qty=Decimal("5"), price=Decimal("1000")):
    return PurchaseItem.objects.create(
        purchase=purchase, product=product, quantity=qty, unit_price=price
    )


def _list_url():
    return reverse("admin:inventory_purchase_changelist")


def _js_src():
    with open(_JS_PATH, encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------

class ListUIBase(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="listui_admin", password="pass", email="x@y.com"
        )
        self.client.force_login(self.admin)
        self.vendor  = _vendor()
        self.product = _product()

    def _get(self):
        return self.client.get(_list_url())


# ---------------------------------------------------------------------------
# Template structure — class-name checks (avoids sidebar Persian text false
# positives; the word "عملیات" can appear in sidebar nav too)
# ---------------------------------------------------------------------------

class TemplateStructureTest(ListUIBase):

    def test_no_actions_column_header_class(self):
        """pu-th-actions class must be absent — the column is fully removed."""
        resp = self._get()
        self.assertNotContains(resp, 'pu-th-actions')

    def test_status_header_class_present(self):
        resp = self._get()
        self.assertContains(resp, 'pu-th-status')

    def test_no_stock_column_header_class(self):
        resp = self._get()
        self.assertNotContains(resp, 'pu-th-stock')

    def test_no_cancel_modal_html(self):
        resp = self._get()
        self.assertNotContains(resp, 'pu-modal-overlay')
        self.assertNotContains(resp, 'pu-modal-confirm-btn')

    def test_js_version_is_v3(self):
        resp = self._get()
        self.assertContains(resp, 'purchase_list.js?v=3')

    def test_css_version_is_v3(self):
        resp = self._get()
        self.assertContains(resp, 'purchase_list.css?v=3')

    def test_status_filter_option_pending(self):
        resp = self._get()
        self.assertContains(resp, 'value="PENDING"')

    def test_status_filter_option_confirmed(self):
        resp = self._get()
        self.assertContains(resp, 'value="CONFIRMED"')

    def test_status_filter_option_cancelled(self):
        resp = self._get()
        self.assertContains(resp, 'value="CANCELLED"')

    def test_add_purchase_button_present(self):
        resp = self._get()
        self.assertContains(resp, '/admin/inventory/purchase/add/')


# ---------------------------------------------------------------------------
# JavaScript source content (ASCII / class-name checks only)
# ---------------------------------------------------------------------------

class JSSourceTest(TestCase):

    def setUp(self):
        self.src = _js_src()

    def test_no_pu_cell_actions_class(self):
        self.assertNotIn('pu-cell-actions', self.src)

    def test_no_pu_action_btn_cancel_class(self):
        self.assertNotIn('pu-action-btn--cancel', self.src)

    def test_no_cancelPurchase_function(self):
        self.assertNotIn('cancelPurchase', self.src)

    def test_no_showModal_function(self):
        self.assertNotIn('showModal', self.src)

    def test_colspan_is_8(self):
        self.assertIn('colspan="8"', self.src)
        self.assertNotIn('colspan="9"', self.src)
        self.assertNotIn('colspan="10"', self.src)

    def test_skeleton_has_8_tds(self):
        import re
        # Find the loading-row template string
        match = re.search(
            r"return '<tr class=\"pu-loading-row\">'(.*?)'</tr>'",
            self.src,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "Could not find skeleton row string in JS")
        cell_count = match.group(1).count('<td>')
        self.assertEqual(
            cell_count, EXPECTED_COLUMNS,
            f"Expected {EXPECTED_COLUMNS} skeleton <td>s, found {cell_count}",
        )

    def test_statusBadge_class_pending(self):
        self.assertIn('pu-badge--pending', self.src)

    def test_statusBadge_class_confirmed(self):
        self.assertIn('pu-badge--confirmed', self.src)

    def test_statusBadge_class_cancelled(self):
        self.assertIn('pu-badge--cancelled', self.src)

    def test_statusBadge_uses_status_display_param(self):
        """statusBadge must use the status_display field from the API, not hardcoded text."""
        self.assertIn('status_display', self.src)

    def test_no_stock_applied_condition_in_statusBadge(self):
        """Status must not be derived from stock_applied."""
        self.assertNotIn('stock_applied', self.src)

    def test_statusBadge_raw_pending_check(self):
        self.assertIn("'PENDING'", self.src)

    def test_statusBadge_raw_confirmed_check(self):
        self.assertIn("'CONFIRMED'", self.src)

    def test_statusBadge_raw_cancelled_check(self):
        self.assertIn("'CANCELLED'", self.src)

    def test_row_click_navigates(self):
        self.assertIn('window.location.href = editUrl', self.src)

    def test_no_pu_cell_stock_in_row(self):
        self.assertNotIn('pu-cell-stock', self.src)


# ---------------------------------------------------------------------------
# API — verifies the serializer returns status and status_display correctly
# ---------------------------------------------------------------------------

class APIStatusFieldTest(ListUIBase):

    def _api(self, **params):
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f'/api/v2/inventory/purchases/?{qs}' if qs else '/api/v2/inventory/purchases/'
        return self.client.get(url, HTTP_ACCEPT='application/json')

    def test_api_returns_status_raw_value(self):
        p = _purchase(vendor=self.vendor)
        resp = self._api()
        results = resp.json().get('results', [])
        result = next(r for r in results if r['id'] == p.pk)
        self.assertIn(result['status'], ('PENDING', 'CONFIRMED', 'CANCELLED'))

    def test_api_returns_status_display_not_empty(self):
        _purchase(vendor=self.vendor)
        resp = self._api()
        results = resp.json().get('results', [])
        self.assertTrue(len(results) > 0)
        for r in results:
            self.assertIn('status_display', r)
            self.assertNotEqual(r['status_display'], '')

    def test_pending_status_raw_value(self):
        p = _purchase(vendor=self.vendor)
        resp = self._api()
        result = next(r for r in resp.json()['results'] if r['id'] == p.pk)
        self.assertEqual(result['status'], 'PENDING')

    def test_confirmed_status_raw_value(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        resp = self._api()
        result = next(r for r in resp.json()['results'] if r['id'] == p.pk)
        self.assertEqual(result['status'], 'CONFIRMED')

    def test_cancelled_status_raw_value(self):
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        p.cancel()
        resp = self._api()
        result = next(r for r in resp.json()['results'] if r['id'] == p.pk)
        self.assertEqual(result['status'], 'CANCELLED')

    def test_status_not_derived_from_stock_applied(self):
        """Status must be CANCELLED regardless of stock_applied value.
        After confirm+cancel, stock_applied stays True (reverse OUT movements were
        created but the field isn't reset); the displayed status must still be CANCELLED.
        """
        p = _purchase(vendor=self.vendor)
        _item(p, self.product)
        p.confirm()
        p.cancel()
        p.refresh_from_db()
        resp = self._api()
        result = next(r for r in resp.json()['results'] if r['id'] == p.pk)
        # status_display is driven by status field, not by stock_applied
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertNotEqual(result['status'], result.get('stock_applied'))

    def test_filter_status_pending(self):
        pending   = _purchase(vendor=self.vendor)
        confirmed = _purchase(vendor=self.vendor)
        _item(confirmed, self.product)
        confirmed.confirm()
        resp = self._api(status='PENDING')
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(pending.pk, ids)
        self.assertNotIn(confirmed.pk, ids)

    def test_filter_status_confirmed(self):
        pending   = _purchase(vendor=self.vendor)
        confirmed = _purchase(vendor=self.vendor)
        _item(confirmed, self.product)
        confirmed.confirm()
        resp = self._api(status='CONFIRMED')
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(confirmed.pk, ids)
        self.assertNotIn(pending.pk, ids)

    def test_filter_status_cancelled(self):
        cancelled = _purchase(vendor=self.vendor)
        _item(cancelled, self.product)
        cancelled.confirm()
        cancelled.cancel()
        pending = _purchase(vendor=self.vendor)
        resp = self._api(status='CANCELLED')
        ids = [r['id'] for r in resp.json()['results']]
        self.assertIn(cancelled.pk, ids)
        self.assertNotIn(pending.pk, ids)
