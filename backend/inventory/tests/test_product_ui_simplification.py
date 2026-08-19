"""Product list UI simplification tests.

Updated requirements (unified table):
- Product list shows ONE unified table for all products (no separate داروها/تجهیزات sections)
- Columns: کد داخلی، نام محصول، نوع، تعداد، قیمت، وضعیت موجودی
- Category filter/column is NOT shown on product list
- Vendor column is NOT shown on product list table
- sale_price / barcode / unit / active status columns NOT shown
- Product type filter IS available (for filtering, not separate sections)
- Stock status (موجود/کم‌موجودی/ناموجود) IS shown (as a column via JS)
- Sort by current_stock IS available (موجودی column is requested)
- Search, price filter, type filter, and sort controls still present
- Top-level add-product button still present
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from inventory.models import Product, ProductCategory, ProductType, ProductVendor, Vendor

User = get_user_model()
PRODUCT_LIST_URL = '/admin/inventory/product/'
PRODUCTS_API_URL = '/api/v2/inventory/products/'


def _make_admin(username='ui_simp_admin'):
    return User.objects.create_superuser(username=username, password='pass')


class ProductListUnifiedTableTest(TestCase):
    """Product list page shows ONE unified table, not separate داروها/تجهیزات sections."""

    def setUp(self):
        self.client.force_login(_make_admin())

    def _get(self):
        return self.client.get(PRODUCT_LIST_URL)

    def test_unified_table_tbody_present(self):
        """The single unified table body must be present."""
        self.assertContains(self._get(), 'pl-tbody')

    def test_unified_table_id_present(self):
        """The single table with id='pl-table' must be present."""
        self.assertContains(self._get(), 'pl-table')

    def test_no_separate_medicine_tbody(self):
        """The old separate medicine tbody (pl-med-tbody) must NOT appear."""
        self.assertNotContains(self._get(), 'pl-med-tbody')

    def test_no_separate_equipment_tbody(self):
        """The old separate equipment tbody (pl-eqp-tbody) must NOT appear."""
        self.assertNotContains(self._get(), 'pl-eqp-tbody')

    def test_no_separate_medicine_section_title(self):
        """The old 'داروها' section header must NOT appear."""
        self.assertNotContains(self._get(), 'داروها')

    def test_no_separate_medicine_pagination(self):
        """The old separate medicine pagination (pl-med-pagination) must NOT appear."""
        self.assertNotContains(self._get(), 'pl-med-pagination')

    def test_no_separate_equipment_pagination(self):
        """The old separate equipment pagination (pl-eqp-pagination) must NOT appear."""
        self.assertNotContains(self._get(), 'pl-eqp-pagination')

    def test_single_pagination_container_present(self):
        """The unified pagination container must be present."""
        self.assertContains(self._get(), 'pl-pagination')

    def test_product_type_filter_present(self):
        """A product type filter dropdown must be present for unified filtering."""
        self.assertContains(self._get(), 'pl-filter-type')

    def test_product_type_filter_has_medicine_option(self):
        """The type filter must offer 'medicine' as an option."""
        self.assertContains(self._get(), 'value="medicine"')

    def test_product_type_filter_has_equipment_option(self):
        """The type filter must offer 'equipment' as an option."""
        self.assertContains(self._get(), 'value="equipment"')

    def test_stats_row_present(self):
        """The summary stats row must be present."""
        self.assertContains(self._get(), 'pl-stats-row')


class ProductListRemovedFiltersTest(TestCase):
    """Removed filter controls must not appear on the product list page."""

    def setUp(self):
        self.client.force_login(_make_admin('ui_filt_admin'))

    def _get(self):
        return self.client.get(PRODUCT_LIST_URL)

    def test_category_filter_not_present(self):
        self.assertNotContains(self._get(), 'pl-filter-category')

    def test_category_dropdown_text_not_present(self):
        self.assertNotContains(self._get(), 'همه دسته‌ها')

    def test_category_filter_dot_not_present(self):
        self.assertNotContains(self._get(), 'pl-dot-cat')

    def test_vendor_filter_not_present(self):
        self.assertNotContains(self._get(), 'pl-filter-vendor')

    def test_active_status_filter_dot_not_present(self):
        self.assertNotContains(self._get(), 'pl-dot-active')


class ProductListRemovedColumnsTest(TestCase):
    """Removed table column identifiers must not appear in the product list page."""

    def setUp(self):
        self.client.force_login(_make_admin('ui_col_admin'))

    def _get(self):
        return self.client.get(PRODUCT_LIST_URL)

    def test_vendor_column_header_not_present(self):
        """The old 'آخرین تامین‌کننده' column header must not appear."""
        self.assertNotContains(self._get(), 'آخرین تامین‌کننده')

    def test_vendor_placeholder_class_not_present(self):
        """The old pl-vendor-ph CSS class must not appear in rendered HTML."""
        self.assertNotContains(self._get(), 'pl-vendor-ph')

    def test_sale_price_column_not_present(self):
        """'قیمت فروش' column header must not appear in the product list HTML."""
        self.assertNotContains(self._get(), 'قیمت فروش')

    def test_unit_column_not_present(self):
        """'واحد' column header must not appear in the product list HTML."""
        # There should be no <th>واحد</th> in the unified table
        self.assertNotContains(self._get(), '<th>واحد</th>')

    def test_old_stock_css_class_not_present(self):
        """The old pl-stock--low / pl-stock--empty CSS classes must not appear."""
        html = self._get().content.decode()
        self.assertNotIn('pl-stock--low',  html)
        self.assertNotIn('pl-stock--empty', html)


class ProductListSortOptionsTest(TestCase):
    """Sort dropdown must expose useful sort options and NOT expose removed ones."""

    def setUp(self):
        self.client.force_login(_make_admin('ui_sort_admin'))

    def _get(self):
        return self.client.get(PRODUCT_LIST_URL)

    def test_sort_option_name_present(self):
        """Sort by name must be available."""
        self.assertContains(self._get(), 'value="name"')

    def test_sort_option_internal_code_present(self):
        """Sort by internal_code must be available."""
        self.assertContains(self._get(), 'value="internal_code"')

    def test_sort_option_purchase_price_present(self):
        """Sort by purchase_price must be available."""
        self.assertContains(self._get(), 'value="purchase_price"')

    def test_sort_option_current_stock_present(self):
        """Sort by current_stock (موجودی) must be available — تعداد is a required column."""
        self.assertContains(self._get(), 'value="current_stock"')

    def test_sort_option_category_not_present(self):
        """value='category__name' sort option must not appear."""
        self.assertNotContains(self._get(), 'category__name')

    def test_sort_option_sale_price_not_present(self):
        """value='sale_price' sort option must not appear."""
        self.assertNotContains(self._get(), 'value="sale_price"')


class ProductListStillPresentTest(TestCase):
    """Search, price filter, sort, and add button must still work."""

    def setUp(self):
        self.client.force_login(_make_admin('ui_keep_admin'))

    def _get(self):
        return self.client.get(PRODUCT_LIST_URL)

    def test_search_input_still_present(self):
        self.assertContains(self._get(), 'pl-search')

    def test_search_data_attribute_present(self):
        self.assertContains(self._get(), 'data-global-search')

    def test_price_min_filter_still_present(self):
        self.assertContains(self._get(), 'pl-filter-price-min')

    def test_price_max_filter_still_present(self):
        self.assertContains(self._get(), 'pl-filter-price-max')

    def test_price_filter_dot_still_present(self):
        self.assertContains(self._get(), 'pl-dot-price')

    def test_sort_by_control_still_present(self):
        self.assertContains(self._get(), 'pl-sort-by')

    def test_sort_dir_control_still_present(self):
        self.assertContains(self._get(), 'pl-sort-dir')

    def test_add_product_button_still_present(self):
        self.assertContains(self._get(), 'pl-add-btn')

    def test_clear_filters_button_still_present(self):
        self.assertContains(self._get(), 'pl-clear-filters')


class ProductListBackendFiltersStillWorkTest(TestCase):
    """Backend API filters (category, vendor, stock) remain functional even though
    some are hidden from the UI. This ensures backend services and reports are intact."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='ui_api_user', password='x')
        from rest_framework.test import APIClient
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_category_filter_still_works_via_api(self):
        """Backend category filter must still be functional."""
        cat = ProductCategory.objects.create(name='Test Cat')
        p = Product.objects.create(
            name='Cat Product', internal_code='CAT-001',
            product_type=ProductType.MEDICINE, unit='عدد',
            purchase_price=Decimal('100'), category=cat,
        )
        resp = self.api.get(PRODUCTS_API_URL, {'category': cat.id, 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p.id, ids)

    def test_vendor_filter_still_works_via_api(self):
        """Backend vendor filter must still be functional."""
        v = Vendor.objects.create(name='Test Vendor')
        p = Product.objects.create(
            name='Vendor Product', internal_code='VEN-001',
            product_type=ProductType.EQUIPMENT, unit='عدد',
            purchase_price=Decimal('200'),
        )
        ProductVendor.objects.create(product=p, vendor=v, unit_price=Decimal('200'), is_active=True)
        resp = self.api.get(PRODUCTS_API_URL, {'vendor': v.id, 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p.id, ids)

    def test_stock_filter_still_works_via_api(self):
        """Backend out_of_stock filter must still be functional."""
        p = Product.objects.create(
            name='Empty Product', internal_code='EMP-001',
            product_type=ProductType.MEDICINE, unit='عدد',
            purchase_price=Decimal('50'),
        )
        Product.objects.filter(pk=p.pk).update(current_stock=Decimal('0'))
        resp = self.api.get(PRODUCTS_API_URL, {'out_of_stock': 'true', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p.id, ids)

    def test_product_type_filter_works_via_api(self):
        """API product_type filter returns only medicines or only equipment."""
        m = Product.objects.create(
            name='A Medicine', internal_code='MED-T-01',
            product_type=ProductType.MEDICINE, unit='ml',
            purchase_price=Decimal('100'),
        )
        e = Product.objects.create(
            name='An Equipment', internal_code='EQP-T-01',
            product_type=ProductType.EQUIPMENT, unit='عدد',
            purchase_price=Decimal('200'),
        )
        resp = self.api.get(PRODUCTS_API_URL, {'product_type': 'medicine', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        types = [r['product_type'] for r in resp.data['results']]
        self.assertTrue(all(t == 'medicine' for t in types))
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(m.id, ids)
        self.assertNotIn(e.id, ids)
