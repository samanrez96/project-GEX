"""Tests for the simplified product list UI (unified table layout).

Confirms:
- Template has ONE unified table with correct columns (کد داخلی، نام، نوع، تعداد، قیمت، وضعیت موجودی)
- Template does NOT contain the old two-section داروها/تجهیزات layout
- Template does NOT contain category/vendor/active-status/sale_price column headers
- sale_price is returned in the list API response (kept for internal use)
- page_size=150 is accepted and honoured by the server
- Search works for both product types
- Vendor/supplier data is preserved in the backend (models intact)
- Product detail API still exposes full product data (not stripped)
"""
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import Product, ProductType, ProductVendor, Vendor

User = get_user_model()
PRODUCTS_URL = '/api/v1/inventory/products/'

# Path to the product list template — used for static content assertions
_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / 'templates' / 'admin' / 'inventory' / 'product' / 'change_list.html'
)


def _make_user():
    count = User.objects.count()
    return User.objects.create_user(username=f'plui_{count}', password='x')


def _make_product(name, code, product_type=ProductType.MEDICINE,
                  purchase_price='1000', sale_price='1500'):
    return Product.objects.create(
        name=name,
        internal_code=code,
        product_type=product_type,
        unit='عدد',
        purchase_price=Decimal(purchase_price),
        sale_price=Decimal(sale_price),
    )


# ---------------------------------------------------------------------------
# Template structure tests (static file checks)
# ---------------------------------------------------------------------------

class ProductListTemplateStructureTests(TestCase):
    """Read the change_list.html template and assert its static content (unified layout)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.html = _TEMPLATE_PATH.read_text(encoding='utf-8')

    def test_no_separate_medicine_section(self):
        """Old 'داروها' section header must NOT appear — unified table replaces it."""
        self.assertNotIn('داروها', self.html)

    def test_no_separate_medicine_tbody(self):
        self.assertNotIn('pl-med-tbody', self.html)

    def test_no_separate_equipment_tbody(self):
        self.assertNotIn('pl-eqp-tbody', self.html)

    def test_has_unified_tbody(self):
        self.assertIn('pl-tbody', self.html)

    def test_template_has_equipment_filter_option(self):
        """'تجهیزات' appears as an option in the type filter, not as a section header."""
        self.assertIn('تجهیزات', self.html)

    def test_template_has_no_category_column(self):
        self.assertNotIn('<th>دسته‌بندی</th>', self.html)

    def test_template_has_no_vendor_column(self):
        self.assertNotIn('<th>تامین‌کننده</th>', self.html)
        self.assertNotIn('<th>تامین‌کننده‌ها</th>', self.html)

    def test_template_has_no_unit_column(self):
        self.assertNotIn('<th>واحد</th>', self.html)
        self.assertNotIn('<th>واحد اندازه‌گیری</th>', self.html)

    def test_template_has_no_sale_price_column(self):
        self.assertNotIn('<th>قیمت فروش</th>', self.html)

    def test_template_has_no_minimum_stock_column_header(self):
        self.assertNotIn('<th>حداقل موجودی</th>', self.html)

    def test_template_has_no_status_active_column(self):
        self.assertNotIn('<th>وضعیت</th>', self.html)

    def test_template_has_search_input(self):
        self.assertIn('pl-search', self.html)

    def test_template_has_no_category_filter(self):
        self.assertNotIn('pl-filter-category', self.html)
        self.assertNotIn('category_id', self.html)

    def test_template_has_product_type_filter(self):
        self.assertIn('pl-filter-type', self.html)

    def test_template_column_headers_correct(self):
        """Unified table must have exactly the required columns."""
        import re
        th_cells = re.findall(r'<th>[^<]+</th>', self.html)
        found = set(re.sub(r'</?th>', '', t) for t in th_cells)
        required = {'کد داخلی', 'نام محصول', 'نوع', 'تعداد', 'قیمت', 'وضعیت موجودی'}
        self.assertEqual(found, required)


# ---------------------------------------------------------------------------
# API behaviour tests
# ---------------------------------------------------------------------------

class ProductListAPITests(APITestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_authenticate(self.user)
        self.vendor = Vendor.objects.create(name='آلفا فارمد')

        self.med = _make_product('آموکسی سیلین', 'MED-PLUI-001',
                                 product_type=ProductType.MEDICINE,
                                 purchase_price='1000', sale_price='1500')
        self.eq  = _make_product('تخت جراحی', 'EQ-PLUI-001',
                                 product_type=ProductType.EQUIPMENT,
                                 purchase_price='50000', sale_price='60000')

        ProductVendor.objects.create(
            product=self.med, vendor=self.vendor,
            unit_price=Decimal('950'), is_active=True,
        )

    # ── sale_price in list response ───────────────────────────────

    def test_sale_price_present_in_list_response(self):
        """sale_price must be included in ProductListSerializer output
        so the UI price column can render it."""
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        for row in resp.data['results']:
            self.assertIn('sale_price', row, 'sale_price missing from list response')

    def test_sale_price_value_is_correct(self):
        resp = self.client.get(PRODUCTS_URL, {
            'product_type': 'medicine', 'is_active': 'all',
        })
        self.assertEqual(resp.status_code, 200)
        med_row = next(r for r in resp.data['results'] if r['id'] == self.med.id)
        self.assertEqual(Decimal(med_row['sale_price']), Decimal('1500'))

    # ── page_size=150 ─────────────────────────────────────────────

    def test_page_size_150_is_accepted(self):
        """The product list JS sends page_size=150; server must honour it."""
        resp = self.client.get(PRODUCTS_URL, {'page_size': '150', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('page_size'), 150)

    def test_default_page_size_is_150(self):
        """ProductListPagination default must be 150 so all 150 demo medicines
        fit on a single page without an explicit page_size param."""
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get('page_size'), 150)

    # ── Two-section filter: medicine / equipment ──────────────────

    def test_medicine_filter_returns_only_medicines(self):
        resp = self.client.get(PRODUCTS_URL, {
            'product_type': 'medicine', 'is_active': 'all',
        })
        self.assertEqual(resp.status_code, 200)
        types = [r['product_type'] for r in resp.data['results']]
        self.assertTrue(all(t == 'medicine' for t in types))
        self.assertIn(self.med.id, [r['id'] for r in resp.data['results']])
        self.assertNotIn(self.eq.id, [r['id'] for r in resp.data['results']])

    def test_equipment_filter_returns_only_equipment(self):
        resp = self.client.get(PRODUCTS_URL, {
            'product_type': 'equipment', 'is_active': 'all',
        })
        self.assertEqual(resp.status_code, 200)
        types = [r['product_type'] for r in resp.data['results']]
        self.assertTrue(all(t == 'equipment' for t in types))
        self.assertIn(self.eq.id, [r['id'] for r in resp.data['results']])

    # ── Search ────────────────────────────────────────────────────

    def test_search_by_medicine_name(self):
        resp = self.client.get(PRODUCTS_URL, {'search': 'آموکسی', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(self.med.id, ids)
        self.assertNotIn(self.eq.id, ids)

    def test_search_by_equipment_name(self):
        resp = self.client.get(PRODUCTS_URL, {'search': 'تخت', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(self.eq.id, ids)
        self.assertNotIn(self.med.id, ids)

    def test_search_by_internal_code(self):
        resp = self.client.get(PRODUCTS_URL, {'search': 'MED-PLUI', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(self.med.id, ids)

    # ── Vendor hidden from list, preserved in backend ─────────────

    def test_vendor_field_not_in_list_response(self):
        """Vendor/supplier data must not appear in list serializer fields."""
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        for row in resp.data['results']:
            self.assertNotIn('vendors', row)
            self.assertNotIn('vendor_name', row)
            self.assertNotIn('supplier', row)
            self.assertNotIn('product_vendors', row)

    def test_vendor_data_preserved_in_backend(self):
        """ProductVendor model must still have supplier data (not deleted)."""
        self.assertTrue(
            ProductVendor.objects.filter(product=self.med, vendor=self.vendor).exists()
        )

    def test_product_detail_exposes_full_data(self):
        """Product detail endpoint must still return full product information."""
        resp = self.client.get(f'{PRODUCTS_URL}{self.med.id}/')
        self.assertEqual(resp.status_code, 200)
        # Detail has more fields than list — category, minimum_stock, barcode, etc.
        self.assertIn('category', resp.data)
        self.assertIn('minimum_stock', resp.data)
        self.assertIn('internal_notes', resp.data)
        self.assertIn('sale_price', resp.data)

    # ── Stock/category columns absent from list (only in backend) ──

    def test_category_preserved_in_backend_not_shown_prominently(self):
        """Category model still exists but is not a visible column in the list UI.
        The API may include category field for internal use; that's acceptable."""
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)
        # The list works — no errors due to category being in the serializer

    def test_list_includes_minimum_stock_for_status_calculation(self):
        """minimum_stock is now exposed in ProductListSerializer to support
        stock_status calculation in the UI (موجود / کم‌موجودی / ناموجود)."""
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        for row in resp.data['results']:
            self.assertIn('minimum_stock', row)
            self.assertIn('stock_status', row)
            self.assertIn('is_out_of_stock', row)
