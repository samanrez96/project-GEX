"""Admin page smoke tests for CLI-55 (RTL responsive).

Verifies that all custom-template inventory admin pages:
  - return HTTP 200 for a logged-in staff user
  - include the rtl_responsive.css stylesheet
  - redirect anonymous users
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from inventory.models import Product, ProductType, Purchase, PurchaseItem, PurchaseStatus, Vendor

User = get_user_model()

PRODUCT_LIST_URL  = '/admin/inventory/product/'
PURCHASE_LIST_URL = '/admin/inventory/purchase/'


class ProductAdminPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='inv_admin_ui', password='pass',
        )
        self.product = Product.objects.create(
            name='داروی آزمایشی',
            internal_code='T-001',
            product_type=ProductType.MEDICINE,
            unit='عدد',
            purchase_price=Decimal('1000'),
        )

    def test_product_list_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_product_list_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'rtl_responsive.css')

    def test_product_list_includes_product_list_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'product_list.css')

    def test_product_list_includes_global_search_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'global_search.js')

    def test_product_list_includes_table_pagination_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'table_pagination.js')

    def test_product_list_includes_table_filters_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'table_filters.js')

    def test_product_list_has_sort_controls(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'pl-sort-by')
        self.assertContains(resp, 'pl-sort-dir')

    def test_product_list_includes_form_validation_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'form_validation.css')

    def test_product_list_includes_form_errors_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'form_errors.js')

    def test_product_list_search_input_has_data_attribute(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'data-global-search')

    def test_product_list_redirects_anonymous(self):
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertIn(resp.status_code, (301, 302))

    def test_product_detail_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/product/{self.product.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_product_detail_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/product/{self.product.pk}/change/')
        self.assertContains(resp, 'rtl_responsive.css')

    def test_product_change_is_real_editable_form(self):
        """
        /change/ must now use Django's built-in change form (NOT the custom detail view).
        Verify the response is a real editable form, not the read-only detail template.
        """
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/product/{self.product.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Real change form has a <form> POST action
        self.assertIn('<form', content)
        self.assertIn('method="post"', content)
        # Real change form has name input field
        self.assertIn('name="name"', content)
        # Must NOT load the custom detail JS (that was the old broken behaviour)
        self.assertNotIn('product_detail.js', content)

    def test_product_custom_detail_page_still_works(self):
        """
        The custom read-only detail view at /detail/ must still use its own template.
        """
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/product/{self.product.pk}/detail/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'product_detail.css')
        self.assertContains(resp, 'product_detail.js')


class PurchaseAdminPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='pu_admin_ui', password='pass',
        )

    def test_purchase_list_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_purchase_list_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'rtl_responsive.css')

    def test_purchase_list_includes_purchase_list_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'purchase_list.css')

    def test_purchase_list_includes_global_search_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'global_search.js')

    def test_purchase_list_includes_table_pagination_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'table_pagination.js')

    def test_purchase_list_search_input_has_data_attribute(self):
        self.client.force_login(self.admin)
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'data-global-search')

    def test_purchase_list_redirects_anonymous(self):
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertIn(resp.status_code, (301, 302))

    # ── Add / edit form tests (CLI-71) ───────────────────────────

    def test_purchase_add_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/purchase/add/')
        self.assertEqual(resp.status_code, 200)

    def test_purchase_add_includes_purchase_form_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/purchase/add/')
        self.assertContains(resp, 'purchase_form.css')

    def test_purchase_add_includes_purchase_form_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/purchase/add/')
        self.assertContains(resp, 'purchase_form.js')

    def test_purchase_add_has_items_section(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/purchase/add/')
        self.assertContains(resp, 'pf-items-card')
        self.assertContains(resp, 'اقلام خرید')

    def test_purchase_add_has_vendor_field(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/purchase/add/')
        content = resp.content.decode()
        self.assertIn('id_vendor', content)

    def test_purchase_add_has_csrf_token(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/purchase/add/')
        self.assertContains(resp, 'csrfmiddlewaretoken')

    def test_purchase_add_redirects_anonymous(self):
        resp = self.client.get('/admin/inventory/purchase/add/')
        self.assertIn(resp.status_code, (301, 302))

    def test_purchase_change_returns_200(self):
        vendor = Vendor.objects.create(name='تامین‌کننده آزمایشی')
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.PENDING,
        )
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_purchase_change_includes_form_css(self):
        vendor = Vendor.objects.create(name='تامین‌کننده آزمایشی ۲')
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.PENDING,
        )
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertContains(resp, 'purchase_form.css')

    def test_purchase_change_confirmed_shows_banner(self):
        vendor = Vendor.objects.create(name='تامین‌کننده تأیید‌شده')
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.CONFIRMED,
            stock_applied=True,
        )
        product = Product.objects.create(
            name='محصول آزمایشی',
            internal_code='T-CONF-001',
            product_type=ProductType.MEDICINE,
            unit='عدد',
        )
        PurchaseItem.objects.create(purchase=purchase, product=product, quantity=1, unit_price=0)
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertContains(resp, 'pf-banner--confirmed')
        self.assertContains(resp, 'خرید تأیید شده')

    def test_purchase_change_has_management_form(self):
        """Django formset management form must be present for POST to work."""
        vendor = Vendor.objects.create(name='تامین‌کننده مدیریت')
        purchase = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.PENDING,
        )
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/purchase/{purchase.pk}/change/')
        self.assertContains(resp, 'TOTAL_FORMS')

    def test_purchase_add_post_creates_purchase(self):
        """Submitting the form with valid data creates a Purchase."""
        vendor = Vendor.objects.create(name='تامین‌کننده POST')
        self.client.force_login(self.admin)
        resp = self.client.post('/admin/inventory/purchase/add/', data={
            'vendor':                  str(vendor.pk),
            'reference_number':        'INV-TEST-001',
            'purchase_date':           '1405/04/03',
            'status':                  'PENDING',
            'notes':                   '',
            # Formset management form (no items)
            'items-TOTAL_FORMS':   '0',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            '_save':                   '1',
        })
        # Successful admin save redirects (302); re-render stays 200
        self.assertIn(resp.status_code, (301, 302))
        self.assertTrue(
            Purchase.objects.filter(reference_number='INV-TEST-001').exists()
        )


class VendorAdminPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='vnd_admin_ui', password='pass',
        )
        self.vendor = Vendor.objects.create(name='فروشنده آزمایشی')

    def test_vendor_list_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/vendor/')
        self.assertEqual(resp.status_code, 200)

    def test_vendor_list_redirects_anonymous(self):
        resp = self.client.get('/admin/inventory/vendor/')
        self.assertIn(resp.status_code, (301, 302))

    def test_vendor_add_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/vendor/add/')
        self.assertEqual(resp.status_code, 200)

    def test_vendor_add_includes_vendor_form_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/vendor/add/')
        self.assertContains(resp, 'vendor_form.css')

    def test_vendor_add_has_name_field(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/vendor/add/')
        self.assertContains(resp, 'id_name')

    def test_vendor_change_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/vendor/{self.vendor.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_vendor_change_includes_vendor_form_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/vendor/{self.vendor.pk}/change/')
        self.assertContains(resp, 'vendor_form.css')

    def test_vendor_change_includes_vendor_form_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/vendor/{self.vendor.pk}/change/')
        self.assertContains(resp, 'vendor_form.js')

    def test_vendor_change_has_products_section(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/vendor/{self.vendor.pk}/change/')
        self.assertContains(resp, 'vf-products-card')

    def test_vendor_change_injects_vendor_id(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/inventory/vendor/{self.vendor.pk}/change/')
        self.assertContains(resp, f'VF_VENDOR_ID = {self.vendor.pk}')

    def test_vendor_add_has_no_products_section(self):
        """Products section only shown in edit mode ({% if original %})."""
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/vendor/add/')
        content = resp.content.decode()
        self.assertNotIn('vf-products-card', content)
        self.assertNotIn('VF_VENDOR_ID', content)

    def test_vendor_add_redirects_anonymous(self):
        resp = self.client.get('/admin/inventory/vendor/add/')
        self.assertIn(resp.status_code, (301, 302))

    def test_vendor_add_post_creates_vendor(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/admin/inventory/vendor/add/', data={
            'name':             'فروشنده جدید',
            'phone_number':     '09121234567',
            'email':            '',
            'address':          '',
            'notes':            '',
            'is_active':        'on',
            'opening_balance':  '0',
            'current_balance':  '0',
            'tax_id':           '',
            'bank_account':     '',
            '_save':            '1',
            # VendorPhone inline management form (required since VendorPhoneInline added)
            'additional_phones-TOTAL_FORMS':   '0',
            'additional_phones-INITIAL_FORMS': '0',
            'additional_phones-MIN_NUM_FORMS':  '0',
            'additional_phones-MAX_NUM_FORMS':  '1000',
        })
        self.assertIn(resp.status_code, (301, 302))
        self.assertTrue(Vendor.objects.filter(name='فروشنده جدید').exists())


