"""Tests: Inventory stock report API.

Covers:
  - current stock report returns all products
  - low-stock products are detected correctly
  - out-of-stock products are detected correctly
  - inventory value is calculated correctly
  - medicine/equipment type filter works
  - category filter works
  - low_stock query param filters list
  - out_of_stock query param filters list
  - empty inventory returns safe zero values
  - permission / auth behavior
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import (
    Product,
    ProductCategory,
    ProductType,
    StockMovement,
    MovementType,
    SourceType,
)

User = get_user_model()

STOCK_REPORT_URL = '/api/v1/inventory/reports/stock/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_category(name='دارو', parent=None):
    obj, _ = ProductCategory.objects.get_or_create(name=name, parent=parent)
    return obj


def make_product(product_type=ProductType.MEDICINE, stock=Decimal('0'),
                 min_stock=Decimal('0'), purchase_price=Decimal('1000'), **kwargs):
    import uuid
    p = Product.objects.create(
        name=f'محصول {uuid.uuid4().hex[:6]}',
        internal_code=f'RPT-{uuid.uuid4().hex[:8]}',
        product_type=product_type,
        unit='عدد',
        minimum_stock=min_stock,
        purchase_price=purchase_price,
        **kwargs,
    )
    if stock > 0:
        StockMovement.objects.create(
            product=p,
            quantity=stock,
            movement_type=MovementType.IN,
            source_type=SourceType.MANUAL_ADJUSTMENT,
        )
        p.refresh_from_db()
    return p


# ---------------------------------------------------------------------------
# Model-level checks (direct)
# ---------------------------------------------------------------------------

class ProductStockPropertiesTest(TestCase):

    def test_is_low_stock_when_at_or_below_minimum(self):
        p = make_product(stock=Decimal('5'), min_stock=Decimal('5'))
        self.assertTrue(p.is_low_stock)

    def test_is_low_stock_false_when_above_minimum(self):
        p = make_product(stock=Decimal('10'), min_stock=Decimal('5'))
        self.assertFalse(p.is_low_stock)

    def test_is_low_stock_false_when_no_minimum_set(self):
        p = make_product(stock=Decimal('0'), min_stock=Decimal('0'))
        self.assertFalse(p.is_low_stock)  # minimum_stock=0 → no threshold

    def test_is_out_of_stock_when_zero(self):
        p = make_product(stock=Decimal('0'))
        self.assertTrue(p.is_out_of_stock)

    def test_is_not_out_of_stock_when_positive(self):
        p = make_product(stock=Decimal('1'))
        self.assertFalse(p.is_out_of_stock)


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------

class InventoryStockReportAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='rpt_user', password='pass')
        self.client.force_authenticate(user=self.user)

    # ── Auth ───────────────────────────────────────────────────────

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(STOCK_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── Basic response ─────────────────────────────────────────────

    def test_report_returns_200(self):
        resp = self.client.get(STOCK_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_response_has_summary_and_results(self):
        resp = self.client.get(STOCK_REPORT_URL)
        self.assertIn('summary', resp.data)
        self.assertIn('results', resp.data)

    def test_summary_has_required_fields(self):
        resp  = self.client.get(STOCK_REPORT_URL)
        summ  = resp.data['summary']
        for field in ('total_products', 'low_stock_count', 'out_of_stock_count',
                      'total_inventory_value'):
            self.assertIn(field, summ, f"Missing summary field: {field}")

    # ── Product list coverage ──────────────────────────────────────

    def test_all_products_appear_in_results(self):
        p1 = make_product(ProductType.MEDICINE)
        p2 = make_product(ProductType.EQUIPMENT)
        resp = self.client.get(STOCK_REPORT_URL)
        ids  = [r['id'] for r in resp.data['results']]
        self.assertIn(p1.pk, ids)
        self.assertIn(p2.pk, ids)

    def test_total_products_count(self):
        before = self.client.get(STOCK_REPORT_URL).data['summary']['total_products']
        make_product()
        make_product()
        after = self.client.get(STOCK_REPORT_URL).data['summary']['total_products']
        self.assertEqual(after, before + 2)

    # ── Low-stock detection ────────────────────────────────────────

    def test_low_stock_count_reflects_products_at_threshold(self):
        make_product(stock=Decimal('3'), min_stock=Decimal('5'))  # low
        make_product(stock=Decimal('10'), min_stock=Decimal('5')) # not low
        resp = self.client.get(STOCK_REPORT_URL)
        self.assertGreaterEqual(resp.data['summary']['low_stock_count'], 1)

    def test_low_stock_filter_param(self):
        p_low    = make_product(stock=Decimal('2'),  min_stock=Decimal('10'))
        p_normal = make_product(stock=Decimal('20'), min_stock=Decimal('10'))
        resp = self.client.get(STOCK_REPORT_URL, {'low_stock': 'true'})
        ids  = [r['id'] for r in resp.data['results']]
        self.assertIn(p_low.pk, ids)
        self.assertNotIn(p_normal.pk, ids)

    # ── Out-of-stock detection ─────────────────────────────────────

    def test_out_of_stock_count_reflects_empty_products(self):
        make_product(stock=Decimal('0'))  # out of stock
        resp = self.client.get(STOCK_REPORT_URL)
        self.assertGreaterEqual(resp.data['summary']['out_of_stock_count'], 1)

    def test_out_of_stock_filter_param(self):
        p_empty   = make_product(stock=Decimal('0'))
        p_stocked = make_product(stock=Decimal('5'))
        resp = self.client.get(STOCK_REPORT_URL, {'out_of_stock': 'true'})
        ids  = [r['id'] for r in resp.data['results']]
        self.assertIn(p_empty.pk, ids)
        self.assertNotIn(p_stocked.pk, ids)

    # ── Inventory value ────────────────────────────────────────────

    def test_inventory_value_is_stock_times_price(self):
        # Isolated test using product_type filter to avoid interference
        p = make_product(
            product_type=ProductType.EQUIPMENT,
            stock=Decimal('3'),
            purchase_price=Decimal('1000'),
        )
        resp  = self.client.get(STOCK_REPORT_URL, {'product_type': ProductType.EQUIPMENT})
        value = Decimal(str(resp.data['summary']['total_inventory_value']))
        # p contributes 3 × 1000 = 3000; there may be other equipment products
        self.assertGreaterEqual(value, Decimal('3000'))

    def test_product_row_inventory_value_field(self):
        p    = make_product(stock=Decimal('4'), purchase_price=Decimal('500'))
        resp = self.client.get(STOCK_REPORT_URL, {'product_type': p.product_type})
        row  = next((r for r in resp.data['results'] if r['id'] == p.pk), None)
        self.assertIsNotNone(row)
        self.assertEqual(Decimal(row['inventory_value']), Decimal('2000.00'))

    # ── Product type filter ────────────────────────────────────────

    def test_medicine_filter(self):
        med  = make_product(product_type=ProductType.MEDICINE)
        equip = make_product(product_type=ProductType.EQUIPMENT)
        resp = self.client.get(STOCK_REPORT_URL, {'product_type': 'medicine'})
        ids  = [r['id'] for r in resp.data['results']]
        self.assertIn(med.pk, ids)
        self.assertNotIn(equip.pk, ids)

    def test_equipment_filter(self):
        med   = make_product(product_type=ProductType.MEDICINE)
        equip = make_product(product_type=ProductType.EQUIPMENT)
        resp  = self.client.get(STOCK_REPORT_URL, {'product_type': 'equipment'})
        ids   = [r['id'] for r in resp.data['results']]
        self.assertIn(equip.pk, ids)
        self.assertNotIn(med.pk, ids)

    # ── Category filter ────────────────────────────────────────────

    def test_category_filter(self):
        cat1 = make_category('دسته ۱')
        cat2 = make_category('دسته ۲')
        p1   = make_product(product_type=ProductType.MEDICINE, category=cat1)
        p2   = make_product(product_type=ProductType.MEDICINE, category=cat2)
        resp = self.client.get(STOCK_REPORT_URL, {'category': cat1.pk})
        ids  = [r['id'] for r in resp.data['results']]
        self.assertIn(p1.pk, ids)
        self.assertNotIn(p2.pk, ids)

    # ── Empty inventory ────────────────────────────────────────────

    def test_empty_type_returns_zero_summary(self):
        """Filtering for a type with no products returns zero summary values."""
        # Use a unique product_type scenario: filter for a type, delete all products
        # (easiest: use a non-existent type string which returns no results)
        resp  = self.client.get(STOCK_REPORT_URL, {
            'product_type': 'medicine',
            'category': 999999,
        })
        summ = resp.data['summary']
        self.assertEqual(summ['total_products'],     0)
        self.assertEqual(summ['low_stock_count'],    0)
        self.assertEqual(summ['out_of_stock_count'], 0)
        self.assertEqual(Decimal(str(summ['total_inventory_value'])), Decimal('0'))
