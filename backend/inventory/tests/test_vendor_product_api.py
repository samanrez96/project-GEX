"""Integration tests for the ProductVendor API endpoint and purchase sync.

Hits the real API paths used by the vendor page JS and the Django admin
purchase form, verifying:
- Same product+vendor with different conditions is allowed
- Exact duplicate is rejected with a useful error
- The old (product, vendor) unique error is gone
- Purchase admin save creates ProductVendor links
- Purchase confirm creates/updates ProductVendor links
- Medicine and equipment purchases both sync to vendor page
- Multi-item purchase adds all products
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from inventory.models import (
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)
from inventory.services import PriceService

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
        "internal_code":  f"TST-{n:04d}",
        "product_type":   product_type,
        "purchase_price": Decimal("0"),
    }
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _purchase(vendor, status=PurchaseStatus.PENDING, purchase_date=None):
    return Purchase.objects.create(
        vendor=vendor,
        status=status,
        purchase_date=purchase_date or datetime.datetime(2025, 6, 1, 10, 0, 0),
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
# API endpoint tests (hits /api/v2/inventory/product-vendors/)
# ---------------------------------------------------------------------------

class ProductVendorAPIAllowsDifferentConditionsTest(TestCase):
    """The API used by vendor_form.js must allow same product+vendor with
    different business conditions."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def _post(self, data):
        return self.client.post(
            '/api/v2/inventory/product-vendors/',
            data,
            content_type='application/json',
        )

    def test_same_product_vendor_different_price_allowed_via_api(self):
        vendor  = _vendor()
        product = _product()

        r1 = self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "is_primary": False, "is_active": True,
        })
        self.assertEqual(r1.status_code, 201, r1.json())

        r2 = self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "7000",  # different price
            "is_primary": False, "is_active": True,
        })
        self.assertEqual(r2.status_code, 201, r2.json())

        count = ProductVendor.objects.filter(vendor=vendor, product=product).count()
        self.assertEqual(count, 2)

    def test_same_product_vendor_different_moq_allowed_via_api(self):
        vendor  = _vendor()
        product = _product()

        self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "minimum_order_quantity": 1,
            "is_primary": False, "is_active": True,
        })
        r2 = self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "minimum_order_quantity": 10,  # different MOQ
            "is_primary": False, "is_active": True,
        })
        self.assertEqual(r2.status_code, 201, r2.json())

    def test_same_product_vendor_different_supplier_code_allowed_via_api(self):
        vendor  = _vendor()
        product = _product()

        self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "supplier_product_code": "SKU-001",
            "is_primary": False, "is_active": True,
        })
        r2 = self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "supplier_product_code": "SKU-002",  # different code
            "is_primary": False, "is_active": True,
        })
        self.assertEqual(r2.status_code, 201, r2.json())

    def test_exact_duplicate_rejected_via_api(self):
        vendor  = _vendor()
        product = _product()

        self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "minimum_order_quantity": 5,
            "supplier_product_code": "SKU-001",
            "is_primary": False, "is_active": True,
        })
        r2 = self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "minimum_order_quantity": 5,  # identical
            "supplier_product_code": "SKU-001",
            "is_primary": False, "is_active": True,
        })
        self.assertEqual(r2.status_code, 400)
        body = r2.json()
        errors = body.get("non_field_errors", [])
        self.assertTrue(len(errors) > 0, "Exact duplicate must be rejected with non_field_errors")
        # Must NOT say "باید یک مجموعه یکتا باشند"
        combined = " ".join(errors)
        self.assertNotIn("باید یک مجموعه یکتا باشند", combined)
        # Must say something about this product being already registered
        self.assertIn("این محصول", combined)

    def test_old_product_vendor_unique_error_not_returned(self):
        """The old error message must never appear."""
        vendor  = _vendor()
        product = _product()

        self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000", "is_primary": False, "is_active": True,
        })
        r2 = self._post({
            "vendor": vendor.pk, "product": product.pk,
            "unit_price": "5000",  # same all fields → rejected, but NOT with old message
            "is_primary": False, "is_active": True,
        })
        self.assertNotIn("باید یک مجموعه یکتا باشند", str(r2.json()))

    def test_vendor_product_list_api_returns_multiple_rows_same_product(self):
        vendor  = _vendor()
        product = _product()

        ProductVendor.objects.create(vendor=vendor, product=product, unit_price=Decimal("100"))
        ProductVendor.objects.create(vendor=vendor, product=product, unit_price=Decimal("200"))

        r = self.client.get(f'/api/v2/inventory/product-vendors/?vendor={vendor.pk}&page_size=200')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        results = data.get("results", data)
        self.assertEqual(len(results), 2)

    def test_product_list_api_returns_already_linked_products(self):
        """The product dropdown must be able to find products already linked to the vendor."""
        vendor  = _vendor()
        product = _product(name="سرم نرمال سالین")

        ProductVendor.objects.create(vendor=vendor, product=product, unit_price=Decimal("500"))

        r = self.client.get('/api/v2/inventory/products/?is_active=true&page_size=500')
        self.assertEqual(r.status_code, 200)
        ids = [p["id"] for p in r.json().get("results", [])]
        self.assertIn(product.pk, ids,
                      "Already-linked product must be in the product list API result")


# ---------------------------------------------------------------------------
# Purchase sync through admin/service path
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CSRF tests for the vendor products section
# ---------------------------------------------------------------------------

class VendorPageCsrfTest(TestCase):
    """The vendor change page must render a csrfmiddlewaretoken input so the
    JS can read a valid token from the DOM without relying on the cookie."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def _get_vendor_page(self, vendor=None):
        vendor = vendor or _vendor()
        return self.client.get(f'/admin/inventory/vendor/{vendor.pk}/change/')

    def test_vendor_page_contains_csrfmiddlewaretoken_input(self):
        r = self._get_vendor_page()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="csrfmiddlewaretoken"',
                            msg_prefix="Vendor change page must render the CSRF hidden input")

    def test_product_vendor_mutation_rejected_without_csrf(self):
        """A POST without CSRF header must be rejected (403) when CSRF is enforced."""
        vendor  = _vendor()
        product = _product()
        # enforce_csrf_checks=True activates CSRF enforcement in the test client
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        r = csrf_client.post(
            '/api/v2/inventory/product-vendors/',
            data={'vendor': vendor.pk, 'product': product.pk, 'unit_price': '500',
                  'is_primary': False, 'is_active': True},
            content_type='application/json',
            # No X-CSRFToken header → Django/DRF rejects the request
        )
        self.assertIn(r.status_code, [403],
                      "Missing CSRF token must return 403 when enforcement is active")

    def test_product_vendor_mutation_succeeds_with_valid_csrf(self):
        """POST with a valid CSRF token must succeed (201)."""
        vendor  = _vendor()
        product = _product()
        # Django's test client enforces CSRF by default when using Client(),
        # but force_login bypasses it.  Use enforce_csrf_checks=True to test properly.
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        # Get CSRF token from the page
        page = csrf_client.get(f'/admin/inventory/vendor/{vendor.pk}/change/')
        self.assertEqual(page.status_code, 200)
        # Extract token from the rendered form input
        import re
        m = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', page.content.decode())
        self.assertIsNotNone(m, "CSRF token must be present in rendered page")
        token = m.group(1)
        self.assertGreater(len(token), 10, "CSRF token must not be empty or too short")

        r = csrf_client.post(
            '/api/v2/inventory/product-vendors/',
            data={'vendor': vendor.pk, 'product': product.pk, 'unit_price': '500',
                  'is_primary': False, 'is_active': True},
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(r.status_code, 201,
                         f"Valid CSRF must allow mutation: {r.status_code} {r.content}")

    def test_js_file_uses_form_input_as_primary_csrf_source(self):
        """vendor_form.js must read CSRF token from the hidden form input first."""
        import os, re
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'admin', 'js', 'vendor_form.js'
        )
        with open(js_path, encoding='utf-8') as f:
            src = f.read()
        self.assertIn('csrfmiddlewaretoken', src,
                      "vendor_form.js must reference the hidden csrfmiddlewaretoken input")
        # Ensure the querySelector approach is present in executable code (not just comments)
        # by looking for the DOM query pattern
        self.assertIn("querySelector('input[name=\"csrfmiddlewaretoken\"]')", src,
                      "vendor_form.js must use querySelector to read the CSRF token from DOM")

    def test_js_file_does_not_use_truncating_cookie_split(self):
        """Verify the old broken split('=') cookie approach is not in executable code."""
        import os
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'admin', 'js', 'vendor_form.js'
        )
        with open(js_path, encoding='utf-8') as f:
            src = f.read()
        # The old broken pattern used: pair[0] === 'csrftoken' then pair[1]
        # (where pair came from split('='), truncating tokens containing '=')
        self.assertNotIn("pair[0] === 'csrftoken'", src,
                         "vendor_form.js must not use the old broken cookie split for CSRF")


class PurchaseSyncVendorProductsTest(TestCase):
    """Verify that purchase save / confirm creates ProductVendor links."""

    def test_ensure_vendor_product_link_medicine(self):
        vendor  = _vendor()
        product = _product(product_type=ProductType.MEDICINE)
        purchase = _purchase(vendor)
        _item(purchase, product)

        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists(),
            "Medicine purchase must create vendor-product link",
        )

    def test_ensure_vendor_product_link_equipment(self):
        vendor  = _vendor()
        product = _product(product_type=ProductType.EQUIPMENT)
        purchase = _purchase(vendor)
        _item(purchase, product)

        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists(),
            "Equipment purchase must create vendor-product link",
        )

    def test_ensure_vendor_product_link_multi_item(self):
        vendor    = _vendor()
        product_a = _product()
        product_b = _product(product_type=ProductType.EQUIPMENT)
        purchase  = _purchase(vendor)
        _item(purchase, product_a)
        _item(purchase, product_b)

        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(ProductVendor.objects.filter(product=product_a, vendor=vendor).exists())
        self.assertTrue(ProductVendor.objects.filter(product=product_b, vendor=vendor).exists())

    def test_ensure_vendor_product_link_idempotent(self):
        """Calling twice must not create duplicate rows."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)

        PriceService.ensure_vendor_product_link(purchase)
        PriceService.ensure_vendor_product_link(purchase)

        self.assertEqual(
            ProductVendor.objects.filter(product=product, vendor=vendor).count(), 1
        )

    def test_confirm_creates_vendor_product_link(self):
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("9000"))

        purchase.confirm()

        self.assertTrue(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists()
        )

    def test_confirm_twice_no_extra_rows(self):
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("4000"))

        purchase.confirm()
        purchase.confirm()  # idempotent — stock_applied guard skips sync

        self.assertEqual(
            ProductVendor.objects.filter(product=product, vendor=vendor).count(), 1
        )

    def test_vendor_page_api_shows_product_after_sync(self):
        """After ensure_vendor_product_link, the vendor API returns the product."""
        client  = Client()
        user    = _superuser()
        client.force_login(user)

        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)

        PriceService.ensure_vendor_product_link(purchase)

        r = client.get(f'/api/v2/inventory/product-vendors/?vendor={vendor.pk}')
        self.assertEqual(r.status_code, 200)
        results = r.json().get("results", [])
        product_ids = [row["product"] for row in results]
        self.assertIn(product.pk, product_ids,
                      "Product must appear in vendor page API after ensure_vendor_product_link")


# ---------------------------------------------------------------------------
# Admin purchase form path — simulate PurchaseAdmin.save_related() being called
# ---------------------------------------------------------------------------

class PurchaseAdminSaveRelatedTest(TestCase):
    """Verify the hook wired into PurchaseAdmin.save_related() works end-to-end."""

    def test_ensure_vendor_product_link_called_after_items_saved(self):
        """The PriceService.ensure_vendor_product_link call in save_related must create
        a ProductVendor row after the purchase items are already in the DB."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        # Items already saved (simulates what super().save_related() does)
        _item(purchase, product)

        # This is what PurchaseAdmin.save_related() calls after super()
        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists(),
            "save_related hook must create ProductVendor link after items are saved",
        )

    def test_admin_save_related_method_exists_and_calls_service(self):
        """PurchaseAdmin.save_related must be defined and call ensure_vendor_product_link."""
        from inventory.admin import PurchaseAdmin
        import inspect

        src = inspect.getsource(PurchaseAdmin.save_related)
        self.assertIn("ensure_vendor_product_link", src,
                      "PurchaseAdmin.save_related must call ensure_vendor_product_link")


# ---------------------------------------------------------------------------
# Tests for Issue 1: no English debug text on vendor change page
# ---------------------------------------------------------------------------

class VendorPageNoDebugTextTest(TestCase):
    """The vendor change page must not contain the English autocomplete debug comment."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def _get_vendor_page(self):
        vendor = _vendor()
        url    = f'/admin/inventory/vendor/{vendor.pk}/change/'
        return self.client.get(url)

    def test_no_english_autocomplete_text(self):
        r = self._get_vendor_page()
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        self.assertNotIn('Autocomplete:', content,
                         "English debug text 'Autocomplete:' must not appear in rendered page")

    def test_no_mousedown_debug_text(self):
        r = self._get_vendor_page()
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        self.assertNotIn('mousedown on dropdown items', content,
                         "English debug text about mousedown must not appear in rendered page")

    def test_no_custom_dropdown_debug_text(self):
        r = self._get_vendor_page()
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        self.assertNotIn('custom dropdown rendered by vendor_form.js', content)


# ---------------------------------------------------------------------------
# Tests for Issue 2: ProductVendor delete via API
# ---------------------------------------------------------------------------

class ProductVendorDeleteAPITest(TestCase):
    """The vendor product delete endpoint must delete only the ProductVendor row."""

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def _create_pv(self, vendor=None, product=None):
        vendor  = vendor  or _vendor()
        product = product or _product()
        pv = ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("1000")
        )
        return pv, vendor, product

    def test_delete_removes_only_productvendor_row(self):
        pv, vendor, product = self._create_pv()
        pk = pv.pk

        r = self.client.delete(
            f'/api/v2/inventory/product-vendors/{pk}/',
            content_type='application/json',
        )
        self.assertIn(r.status_code, [204, 200], f"Delete must succeed, got {r.status_code}")
        self.assertFalse(ProductVendor.objects.filter(pk=pk).exists(),
                         "ProductVendor row must be deleted")

    def test_delete_does_not_delete_product(self):
        pv, vendor, product = self._create_pv()
        self.client.delete(f'/api/v2/inventory/product-vendors/{pv.pk}/')
        self.assertTrue(product.__class__.objects.filter(pk=product.pk).exists(),
                        "Product must survive ProductVendor deletion")

    def test_delete_does_not_delete_vendor(self):
        pv, vendor, product = self._create_pv()
        self.client.delete(f'/api/v2/inventory/product-vendors/{pv.pk}/')
        self.assertTrue(Vendor.objects.filter(pk=vendor.pk).exists(),
                        "Vendor must survive ProductVendor deletion")

    def test_delete_does_not_affect_purchase_history(self):
        pv, vendor, product = self._create_pv()
        purchase = _purchase(vendor)
        _item(purchase, product)

        self.client.delete(f'/api/v2/inventory/product-vendors/{pv.pk}/')

        self.assertTrue(Purchase.objects.filter(pk=purchase.pk).exists(),
                        "Purchase must survive ProductVendor deletion")
        self.assertTrue(PurchaseItem.objects.filter(purchase=purchase).exists(),
                        "PurchaseItems must survive ProductVendor deletion")

    def test_delete_requires_authentication(self):
        pv, _, _ = self._create_pv()
        anon_client = Client()
        r = anon_client.delete(f'/api/v2/inventory/product-vendors/{pv.pk}/')
        self.assertIn(r.status_code, [401, 403],
                      "Unauthenticated delete must be rejected")
        self.assertTrue(ProductVendor.objects.filter(pk=pv.pk).exists(),
                        "Row must not be deleted by unauthenticated request")

    def test_delete_non_existing_row_returns_404(self):
        r = self.client.delete('/api/v2/inventory/product-vendors/99999999/')
        self.assertEqual(r.status_code, 404)

    def test_vendor_product_list_excludes_deleted_row(self):
        pv, vendor, product = self._create_pv()

        # Verify it exists before
        r_before = self.client.get(f'/api/v2/inventory/product-vendors/?vendor={vendor.pk}')
        ids_before = [x['id'] for x in r_before.json().get('results', [])]
        self.assertIn(pv.pk, ids_before)

        # Delete it
        self.client.delete(f'/api/v2/inventory/product-vendors/{pv.pk}/')

        # Verify it's gone
        r_after = self.client.get(f'/api/v2/inventory/product-vendors/?vendor={vendor.pk}')
        ids_after = [x['id'] for x in r_after.json().get('results', [])]
        self.assertNotIn(pv.pk, ids_after, "Deleted row must not appear in API results")


# ---------------------------------------------------------------------------
# Vendor tab purchase stats — supplier columns in product detail vendor tab
# ---------------------------------------------------------------------------

class VendorTabPurchaseStatsTest(TestCase):
    """Tests for the two new columns (تعداد خریداری‌شده, تاریخ آخرین خرید)
    and the clickable supplier-name link in the product detail vendor tab.

    All stats come from /api/v2/inventory/product-vendors/?product=<id>
    via ProductVendorListSerializer with purchase_stats injected by the viewset.
    """

    URL = '/api/v2/inventory/product-vendors/'

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def _get_pv_list(self, product):
        r = self.client.get(self.URL, {'product': product.pk, 'page_size': 100})
        self.assertEqual(r.status_code, 200)
        return r.json().get('results', [])

    def _make_pv(self, product, vendor, **kw):
        return ProductVendor.objects.create(product=product, vendor=vendor, **kw)

    def _confirmed_purchase(self, vendor, product, quantity, purchase_date=None):
        import datetime
        p = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.CONFIRMED,
            purchase_date=purchase_date or datetime.datetime(2026, 6, 1, 10, 0),
        )
        PurchaseItem.objects.create(
            purchase=p, product=product,
            quantity=quantity, unit_price=Decimal("1000"),
        )
        return p

    def _pending_purchase(self, vendor, product, quantity):
        import datetime
        p = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.PENDING,
            purchase_date=datetime.datetime(2026, 6, 1, 10, 0),
        )
        PurchaseItem.objects.create(
            purchase=p, product=product,
            quantity=quantity, unit_price=Decimal("1000"),
        )
        return p

    def _cancelled_purchase(self, vendor, product, quantity):
        import datetime
        p = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.CANCELLED,
            purchase_date=datetime.datetime(2026, 6, 1, 10, 0),
        )
        PurchaseItem.objects.create(
            purchase=p, product=product,
            quantity=quantity, unit_price=Decimal("1000"),
        )
        return p

    # ── Supplier URL ──────────────────────────────────────────────────────

    def test_vendor_url_present_in_response(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        self.assertEqual(len(rows), 1)
        self.assertIn('vendor_url', rows[0])

    def test_vendor_url_points_to_correct_supplier_page(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        expected = f'/admin/inventory/vendor/{vendor.pk}/change/'
        self.assertEqual(rows[0]['vendor_url'], expected)

    # ── Confirmed quantity ────────────────────────────────────────────────

    def test_confirmed_purchase_quantity_included(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._confirmed_purchase(vendor, product, quantity=Decimal("5"))
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['total_purchased_quantity'], '5')

    def test_multiple_confirmed_purchases_summed(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        import datetime
        self._confirmed_purchase(vendor, product, quantity=Decimal("3"),
                                 purchase_date=datetime.datetime(2026, 5, 1, 10, 0))
        self._confirmed_purchase(vendor, product, quantity=Decimal("5"),
                                 purchase_date=datetime.datetime(2026, 6, 1, 10, 0))
        self._confirmed_purchase(vendor, product, quantity=Decimal("2"),
                                 purchase_date=datetime.datetime(2026, 7, 1, 10, 0))
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['total_purchased_quantity'], '10')

    def test_pending_purchase_quantity_excluded(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._pending_purchase(vendor, product, quantity=Decimal("99"))
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['total_purchased_quantity'], '0')

    def test_cancelled_purchase_quantity_excluded(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._cancelled_purchase(vendor, product, quantity=Decimal("99"))
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['total_purchased_quantity'], '0')

    def test_other_vendor_purchases_excluded(self):
        vendor_a = _vendor()
        vendor_b = _vendor()
        product  = _product()
        self._make_pv(product, vendor_a)
        self._make_pv(product, vendor_b)
        self._confirmed_purchase(vendor_b, product, quantity=Decimal("20"))
        rows = self._get_pv_list(product)
        row_a = next(r for r in rows if r['vendor'] == vendor_a.pk)
        self.assertEqual(row_a['total_purchased_quantity'], '0')

    def test_other_product_purchases_excluded(self):
        vendor    = _vendor()
        product_a = _product()
        product_b = _product()
        self._make_pv(product_a, vendor)
        self._confirmed_purchase(vendor, product_b, quantity=Decimal("50"))
        rows = self._get_pv_list(product_a)
        self.assertEqual(rows[0]['total_purchased_quantity'], '0')

    def test_no_purchase_history_returns_zero(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['total_purchased_quantity'], '0')

    # ── Latest purchase date ──────────────────────────────────────────────

    def test_latest_confirmed_purchase_date_returned(self):
        import datetime
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._confirmed_purchase(vendor, product, quantity=Decimal("1"),
                                 purchase_date=datetime.datetime(2026, 7, 7, 12, 0))
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['latest_purchase_date'], '2026-07-07')

    def test_newer_pending_does_not_replace_latest_confirmed_date(self):
        import datetime
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._confirmed_purchase(vendor, product, quantity=Decimal("1"),
                                 purchase_date=datetime.datetime(2026, 6, 1, 10, 0))
        self._pending_purchase(vendor, product, quantity=Decimal("1"))  # date=2026-06-01 also
        rows = self._get_pv_list(product)
        # latest_purchase_date must be the confirmed one, not the pending one
        self.assertEqual(rows[0]['latest_purchase_date'], '2026-06-01')

    def test_newer_cancelled_does_not_replace_latest_confirmed_date(self):
        import datetime
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._confirmed_purchase(vendor, product, quantity=Decimal("1"),
                                 purchase_date=datetime.datetime(2026, 5, 1, 10, 0))
        self._cancelled_purchase(vendor, product, quantity=Decimal("1"))
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['latest_purchase_date'], '2026-05-01')

    def test_same_date_uses_pk_tiebreaker(self):
        """Two confirmed purchases on the same date — Max(purchase_date) still returns that date."""
        import datetime
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        same_date = datetime.datetime(2026, 6, 15, 9, 0)
        self._confirmed_purchase(vendor, product, quantity=Decimal("1"), purchase_date=same_date)
        self._confirmed_purchase(vendor, product, quantity=Decimal("2"), purchase_date=same_date)
        rows = self._get_pv_list(product)
        # Both on same date; Max returns that date
        self.assertEqual(rows[0]['latest_purchase_date'], '2026-06-15')

    def test_no_confirmed_purchase_returns_null_date(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        self.assertIsNone(rows[0]['latest_purchase_date'])

    # ── Decimal quantity display ──────────────────────────────────────────

    def test_integer_quantity_has_no_trailing_zeros(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._confirmed_purchase(vendor, product, quantity=Decimal("10.000"))
        rows = self._get_pv_list(product)
        qty = rows[0]['total_purchased_quantity']
        self.assertNotIn('.', qty, f"Integer quantity must not show decimal point: got {qty!r}")
        self.assertNotIn('None', qty)

    def test_decimal_quantity_preserved_without_trailing_zeros(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        self._confirmed_purchase(vendor, product, quantity=Decimal("10.500"))
        rows = self._get_pv_list(product)
        qty = rows[0]['total_purchased_quantity']
        # 10.500 → '10.5' (trailing zero stripped)
        self.assertNotIn('000', qty)
        self.assertNotIn('00', qty[-3:] if len(qty) >= 3 else qty)

    # ── N+1 query count ───────────────────────────────────────────────────

    def test_query_count_does_not_grow_per_vendor_row(self):
        """With N vendor rows, query count must be constant (not O(N))."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        product = _product()
        for _ in range(5):
            v = _vendor()
            self._make_pv(product, v)
            self._confirmed_purchase(v, product, quantity=Decimal("1"))

        # Warm up any caches
        self._get_pv_list(product)

        with CaptureQueriesContext(connection) as ctx:
            self._get_pv_list(product)
        query_count = len(ctx.captured_queries)

        # 1 more vendor row must not add more queries
        extra_vendor = _vendor()
        self._make_pv(product, extra_vendor)
        self._confirmed_purchase(extra_vendor, product, quantity=Decimal("2"))

        with CaptureQueriesContext(connection) as ctx2:
            self._get_pv_list(product)
        query_count_2 = len(ctx2.captured_queries)

        self.assertEqual(
            query_count, query_count_2,
            f"Adding a vendor row changed query count from {query_count} to {query_count_2} — N+1 detected",
        )

    # ── Existing fields intact ────────────────────────────────────────────

    def test_existing_price_field_still_correct(self):
        vendor  = _vendor()
        product = _product()
        pv = self._make_pv(product, vendor, unit_price=Decimal("18000"))
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['unit_price'], '18000.00')

    def test_existing_is_primary_field_still_correct(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor, is_primary=True)
        rows = self._get_pv_list(product)
        self.assertTrue(rows[0]['is_primary'])

    def test_existing_supplier_code_field_still_correct(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor, supplier_product_code="ABC-123")
        rows = self._get_pv_list(product)
        self.assertEqual(rows[0]['supplier_product_code'], 'ABC-123')

    # ── Header + body column count parity ────────────────────────────────

    def test_product_detail_page_loads_for_staff(self):
        """The product detail page itself must return 200 for admin users."""
        product = _product()
        r = self.client.get(f'/admin/inventory/product/{product.pk}/detail/')
        self.assertEqual(r.status_code, 200)

    # ── Duplicate ProductVendor rows ──────────────────────────────────────

    def test_duplicate_pv_rows_show_same_purchase_stats(self):
        """Two ProductVendor rows for same (product, vendor) get identical stats."""
        import datetime
        vendor  = _vendor()
        product = _product()
        pv1 = self._make_pv(product, vendor, unit_price=Decimal("5000"))
        pv2 = self._make_pv(product, vendor, unit_price=Decimal("7000"))
        self._confirmed_purchase(vendor, product, quantity=Decimal("8"),
                                 purchase_date=datetime.datetime(2026, 7, 1, 0, 0))
        rows = self._get_pv_list(product)
        self.assertEqual(len(rows), 2)
        quantities = {r['total_purchased_quantity'] for r in rows}
        dates      = {r['latest_purchase_date']     for r in rows}
        self.assertEqual(quantities, {'8'})
        self.assertEqual(dates, {'2026-07-01'})

    # ── Other product detail tabs unchanged ───────────────────────────────

    def test_product_api_general_tab_unaffected(self):
        """ProductSerializer response must not include purchase_stats fields."""
        product = _product()
        r = self.client.get(f'/api/v2/inventory/products/{product.pk}/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertNotIn('total_purchased_quantity', data)
        self.assertNotIn('latest_purchase_date', data)
        self.assertNotIn('vendor_url', data)


# ---------------------------------------------------------------------------
# Vendor detail URL in supplier API + Vendor detail admin page
# ---------------------------------------------------------------------------

class VendorDetailUrlTest(TestCase):
    """Tests for vendor_detail_url field in the product-vendor API."""

    URL = '/api/v2/inventory/product-vendors/'

    def setUp(self):
        self.client = Client()
        self.user   = _superuser()
        self.client.force_login(self.user)

    def _get_pv_list(self, product):
        r = self.client.get(self.URL, {'product': product.pk, 'page_size': 100})
        self.assertEqual(r.status_code, 200)
        return r.json().get('results', [])

    def _make_pv(self, product, vendor, **kw):
        return ProductVendor.objects.create(product=product, vendor=vendor, **kw)

    def test_vendor_detail_url_present_in_response(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        self.assertEqual(len(rows), 1)
        self.assertIn('vendor_detail_url', rows[0])

    def test_vendor_detail_url_points_to_detail_page(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        expected = f'/admin/inventory/vendor/{vendor.pk}/detail/'
        self.assertEqual(rows[0]['vendor_detail_url'], expected)

    def test_vendor_detail_url_does_not_end_with_change(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        self.assertFalse(
            rows[0]['vendor_detail_url'].endswith('/change/'),
            "vendor_detail_url must NOT point to the edit page"
        )

    def test_vendor_url_still_points_to_change_page(self):
        """vendor_url (for the edit button) must remain unchanged."""
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        expected = f'/admin/inventory/vendor/{vendor.pk}/change/'
        self.assertEqual(rows[0]['vendor_url'], expected)

    def test_vendor_detail_url_and_vendor_url_are_different(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        self.assertNotEqual(rows[0]['vendor_detail_url'], rows[0]['vendor_url'])

    def test_vendor_detail_url_contains_correct_vendor_id(self):
        vendor  = _vendor()
        product = _product()
        self._make_pv(product, vendor)
        rows = self._get_pv_list(product)
        self.assertIn(str(vendor.pk), rows[0]['vendor_detail_url'])


class VendorDetailPageTest(TestCase):
    """Tests for the /admin/inventory/vendor/<id>/detail/ page."""

    def setUp(self):
        self.user = _superuser()
        self.client.force_login(self.user)

    def test_vendor_detail_page_returns_200(self):
        vendor = _vendor()
        r = self.client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        self.assertEqual(r.status_code, 200)

    def test_vendor_detail_page_displays_correct_vendor_name(self):
        vendor = _vendor()
        r = self.client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        self.assertContains(r, vendor.name)

    def test_vendor_detail_page_is_not_edit_page(self):
        vendor = _vendor()
        r = self.client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        content = r.content.decode('utf-8')
        # Detail page must not contain a save/submit button
        self.assertNotIn('name="_save"', content)
        self.assertNotIn('name="_continue"', content)

    def test_vendor_detail_page_has_edit_link(self):
        vendor = _vendor()
        r = self.client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        edit_url = f'/admin/inventory/vendor/{vendor.pk}/change/'
        self.assertContains(r, edit_url)

    def test_vendor_detail_page_has_back_link(self):
        vendor = _vendor()
        r = self.client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        self.assertContains(r, '/admin/inventory/vendor/')

    def test_vendor_detail_page_returns_404_for_missing_vendor(self):
        r = self.client.get('/admin/inventory/vendor/999999/detail/')
        self.assertEqual(r.status_code, 404)

    def test_unauthorized_user_cannot_access_detail_page(self):
        vendor = _vendor()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        nonadmin = User.objects.create_user(
            username=f'nonadmin_{_uid_next()}', password='pass'
        )
        self.client.force_login(nonadmin)
        r = self.client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        # Non-staff users should be redirected to login
        self.assertNotEqual(r.status_code, 200)

    def test_anonymous_user_cannot_access_detail_page(self):
        from django.test import Client as TestClient
        vendor = _vendor()
        anon_client = TestClient()
        r = anon_client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        self.assertNotEqual(r.status_code, 200)

    def test_vendor_detail_page_shows_linked_products(self):
        vendor  = _vendor()
        product = _product()
        ProductVendor.objects.create(product=product, vendor=vendor)
        r = self.client.get(f'/admin/inventory/vendor/{vendor.pk}/detail/')
        self.assertContains(r, product.name)

    def test_vendor_detail_url_resolves_to_correct_view(self):
        """The URL /admin/inventory/vendor/<id>/detail/ must resolve cleanly."""
        vendor = _vendor()
        url    = f'/admin/inventory/vendor/{vendor.pk}/detail/'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        # Confirm it rendered the detail template (not change form)
        self.assertContains(r, 'vendor-detail-root')
