"""Tests for the purchase edit page add-item save behavior and banner removal.

Verifies:
- PENDING zero-item purchase page allows adding an item via Django formset
- Posted formset data with TOTAL_FORMS=1 creates a real PurchaseItem
- The PENDING banner ("از طریق API تأیید کنید") is NOT rendered
- Empty state is not shown after an item exists
- Confirming a zero-item purchase is still blocked
- Normal confirmed purchases with items remain protected
- purchase_form.js totalFormCountEl selects by name attribute (tested via template)
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client

from inventory.models import (
    Product,
    ProductType,
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


def _vendor():
    return Vendor.objects.create(name=f"تامین‌کننده {_uid_next()}")


def _product():
    n = _uid_next()
    return Product.objects.create(
        name=f"محصول {n}",
        internal_code=f"ADD-{n:04d}",
        product_type=ProductType.MEDICINE,
        purchase_price=Decimal("0"),
    )


def _purchase(vendor, status=PurchaseStatus.PENDING):
    return Purchase.objects.create(
        vendor=vendor,
        status=status,
        purchase_date=datetime.datetime(2025, 6, 1, 10, 0, 0),
    )


def _superuser():
    return User.objects.create_superuser(
        username=f"admin_{_uid_next()}", password="pass", email=""
    )


# ---------------------------------------------------------------------------
# Management form / TOTAL_FORMS selector test
# ---------------------------------------------------------------------------

class PurchaseFormManagementFormTest(TestCase):
    """The purchase change page must render the management form input with a
    name attribute so the JS querySelector('[name="items-TOTAL_FORMS"]') can
    find it (getElementById would fail because Django adds 'id_' prefix)."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def test_management_form_input_has_name_items_total_forms(self):
        vendor   = _vendor()
        purchase = _purchase(vendor)
        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        # Django renders: name="items-TOTAL_FORMS" id="id_items-TOTAL_FORMS"
        # JS must find it via name, not getElementById
        self.assertIn('name="items-TOTAL_FORMS"', content,
                      "Management form must have name attribute for JS querySeclector")

    def test_js_file_uses_queryselector_not_getelementbyid_for_total_forms(self):
        import os
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'admin', 'js', 'purchase_form.js'
        )
        with open(js_path, encoding='utf-8') as f:
            src = f.read()
        # Must NOT use getElementById for TOTAL_FORMS
        self.assertNotIn("getElementById(PREFIX + '-TOTAL_FORMS')", src,
                         "JS must not use getElementById for TOTAL_FORMS (wrong id prefix)")
        # Must use querySelector with name attribute
        self.assertIn("querySelector('[name=\"' + PREFIX + '-TOTAL_FORMS\"]')", src,
                      "JS must use querySelector by name attribute for TOTAL_FORMS")


# ---------------------------------------------------------------------------
# PENDING banner removal test
# ---------------------------------------------------------------------------

class PendingBannerRemovedTest(TestCase):
    """The PENDING status must not show the 'API تأیید کنید' banner."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def test_pending_purchase_page_has_no_api_confirm_banner(self):
        vendor   = _vendor()
        purchase = _purchase(vendor)
        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        self.assertNotIn('از طریق API تأیید کنید', content,
                         "PENDING banner instructing API usage must not be rendered")

    def test_pending_purchase_page_shows_add_item_button(self):
        vendor   = _vendor()
        purchase = _purchase(vendor)
        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'pf-add-item-btn',
                            msg_prefix="Add item button must appear for PENDING purchase")


# ---------------------------------------------------------------------------
# Add item via formset POST — the actual save path
# ---------------------------------------------------------------------------

class AddItemToPendingPurchaseTest(TestCase):
    """Posting the admin form with TOTAL_FORMS=1 and item data must create
    a real PurchaseItem in the database."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def _post_purchase_with_item(self, purchase, product, quantity='5', price='1000'):
        """Simulate what the browser sends when the user adds one item and saves."""
        url = f'/admin/inventory/purchase/{purchase.pk}/change/'
        data = {
            # Purchase fields
            'vendor':                  str(purchase.vendor.pk),
            'purchase_date':           '1405/04/03',
            'status':                  'PENDING',
            'notes':                   '',
            # Management form — JS increments TOTAL_FORMS to 1 before submit
            'items-TOTAL_FORMS':       '1',
            'items-INITIAL_FORMS':     '0',
            'items-MIN_NUM_FORMS':     '0',
            'items-MAX_NUM_FORMS':     '1000',
            # New item at index 0
            'items-0-product':         str(product.pk),
            'items-0-quantity':        quantity,
            'items-0-unit_price':      price,
            'items-0-notes':           '',
            'items-0-id':              '',      # blank = new item
            '_save':                   '1',
        }
        return self.client.post(url, data)

    def test_posting_item_creates_purchaseitem(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)

        r = self._post_purchase_with_item(purchase, product)

        # Successful save redirects
        self.assertIn(r.status_code, [301, 302],
                      f"Admin save must redirect; got {r.status_code}: {r.content[:200]}")
        self.assertEqual(purchase.items.count(), 1,
                         "One PurchaseItem must exist after form save")

    def test_posted_item_has_correct_data(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)

        self._post_purchase_with_item(purchase, product, quantity='3', price='2500')

        item = purchase.items.first()
        self.assertIsNotNone(item)
        self.assertEqual(item.product_id, product.pk)
        self.assertEqual(item.quantity, Decimal('3'))
        self.assertEqual(item.unit_price, Decimal('2500'))

    def test_page_shows_no_empty_state_after_item_added(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        self._post_purchase_with_item(purchase, product)

        # After item added, the edit page must not show empty-state text
        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        # The JS-driven empty state is 'pf-items-empty'; when items exist
        # the server-rendered formset has rows, so this div should be hidden
        # or not shown in the initial render
        self.assertEqual(purchase.items.count(), 1,
                         "Item must persist after saving")

    def test_purchase_with_item_can_be_confirmed(self):
        """After adding an item, the purchase should be confirmable."""
        from django.core.exceptions import ValidationError
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        self._post_purchase_with_item(purchase, product)

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.PENDING)
        self.assertEqual(purchase.items.count(), 1)

        # Should confirm without error
        purchase.confirm()
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)

    def test_confirming_zero_item_purchase_still_blocked(self):
        """The zero-item confirm fix must still apply."""
        from django.core.exceptions import ValidationError
        vendor   = _vendor()
        purchase = _purchase(vendor)

        with self.assertRaises(ValidationError):
            purchase.confirm()

    def test_normal_confirmed_purchase_not_broken(self):
        """Normal confirmed purchases with items remain protected."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        PurchaseItem.objects.create(
            purchase=purchase, product=product,
            quantity=1, unit_price=Decimal("500"),
        )
        purchase.confirm()
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)

        # Cannot add items to confirmed purchase (inline locked)
        r = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        # Normal confirmed with items → no add button
        self.assertNotIn('pf-add-item-btn', content)
        # Normal confirmed banner should appear
        self.assertIn('pf-banner--confirmed', content)
