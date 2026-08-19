"""Filter and sort tests for ProductViewSet and PurchaseViewSet (CLI-58)."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import (
    Product,
    ProductCategory,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)

User = get_user_model()
PRODUCTS_URL  = '/api/v2/inventory/products/'
PURCHASES_URL = '/api/v2/inventory/purchases/'


def _user():
    return User.objects.create_user(username=f'pf_{User.objects.count()}', password='x')


def _category(name='Cat'):
    return ProductCategory.objects.create(name=name)


def _vendor(name='Vendor'):
    return Vendor.objects.create(name=name)


def _product(name='Prod', purchase_price=Decimal('1000'), category=None,
             current_stock_override=None, product_type=ProductType.MEDICINE):
    import random
    uid = random.randint(100000, 999999)
    p = Product.objects.create(
        name=name,
        internal_code=f'C-{uid}',
        product_type=product_type,
        unit='عدد',
        purchase_price=purchase_price,
        category=category,
    )
    if current_stock_override is not None:
        # Use update to bypass validation
        Product.objects.filter(pk=p.pk).update(current_stock=current_stock_override)
        p.refresh_from_db()
    return p


class ProductFilterTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.vendor = _vendor('تامین‌کننده آلفا')
        self.cat    = _category('داروهای عمومی')

    # ── Filter by product_type ────────────────────────────────────

    def test_filter_product_type_medicine(self):
        _product('دارو A', product_type=ProductType.MEDICINE)
        _product('تجهیز A', product_type=ProductType.EQUIPMENT)
        resp = self.client.get(PRODUCTS_URL, {'product_type': 'medicine', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        types = [r['product_type'] for r in resp.data['results']]
        self.assertTrue(all(t == 'medicine' for t in types))

    # ── Filter by category ────────────────────────────────────────

    def test_filter_by_category(self):
        p1 = _product('دارو B', category=self.cat)
        p2 = _product('دارو C')
        resp = self.client.get(PRODUCTS_URL, {'category': self.cat.id, 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p1.id, ids)
        self.assertNotIn(p2.id, ids)

    # ── Filter by vendor ──────────────────────────────────────────

    def test_filter_by_vendor(self):
        p_with = _product('دارو D')
        p_without = _product('دارو E')
        ProductVendor.objects.create(
            product=p_with, vendor=self.vendor,
            unit_price=Decimal('1000'), is_active=True,
        )
        resp = self.client.get(PRODUCTS_URL, {'vendor': self.vendor.id, 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p_with.id, ids)
        self.assertNotIn(p_without.id, ids)

    # ── Filter by price range ─────────────────────────────────────

    def test_filter_price_min(self):
        p_cheap = _product('ارزان', purchase_price=Decimal('100'))
        p_mid   = _product('متوسط', purchase_price=Decimal('500'))
        p_exp   = _product('گران',  purchase_price=Decimal('1000'))
        resp = self.client.get(PRODUCTS_URL, {'price_min': '400', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        prices = [Decimal(r['purchase_price']) for r in resp.data['results']]
        self.assertTrue(all(pr >= 400 for pr in prices))

    def test_filter_price_max(self):
        p_cheap = _product('ارزان2', purchase_price=Decimal('100'))
        p_exp   = _product('گران2',  purchase_price=Decimal('900'))
        resp = self.client.get(PRODUCTS_URL, {'price_max': '200', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        prices = [Decimal(r['purchase_price']) for r in resp.data['results']]
        self.assertTrue(all(pr <= 200 for pr in prices))

    # ── Filter by stock range ─────────────────────────────────────

    def test_filter_stock_min(self):
        p_low  = _product('کم‌موجودی', current_stock_override=Decimal('2'))
        p_high = _product('پرموجودی',  current_stock_override=Decimal('50'))
        resp = self.client.get(PRODUCTS_URL, {'stock_min': '10', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p_high.id, ids)
        self.assertNotIn(p_low.id, ids)

    def test_filter_stock_max(self):
        p_low  = _product('کم2', current_stock_override=Decimal('2'))
        p_high = _product('زیاد2', current_stock_override=Decimal('50'))
        resp = self.client.get(PRODUCTS_URL, {'stock_max': '5', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p_low.id, ids)
        self.assertNotIn(p_high.id, ids)

    # ── Filter by low_stock / out_of_stock ────────────────────────

    def test_filter_out_of_stock(self):
        p_empty = _product('تمام شده', current_stock_override=Decimal('0'))
        p_full  = _product('موجود',    current_stock_override=Decimal('10'))
        resp = self.client.get(PRODUCTS_URL, {'out_of_stock': 'true', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p_empty.id, ids)
        self.assertNotIn(p_full.id, ids)

    # ── Sorting ───────────────────────────────────────────────────

    def test_sort_by_purchase_price_asc(self):
        _product('ارزان3', purchase_price=Decimal('100'))
        _product('گران3',  purchase_price=Decimal('800'))
        resp = self.client.get(PRODUCTS_URL, {'ordering': 'purchase_price', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        prices = [Decimal(r['purchase_price']) for r in resp.data['results']]
        self.assertEqual(prices, sorted(prices))

    def test_sort_by_purchase_price_desc(self):
        _product('ارزان4', purchase_price=Decimal('100'))
        _product('گران4',  purchase_price=Decimal('800'))
        resp = self.client.get(PRODUCTS_URL, {'ordering': '-purchase_price', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        prices = [Decimal(r['purchase_price']) for r in resp.data['results']]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_sort_by_name(self):
        _product('آلفا')
        _product('بتا')
        resp = self.client.get(PRODUCTS_URL, {'ordering': 'name', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        # Just verify it doesn't 400
        self.assertIn('results', resp.data)

    def test_invalid_ordering_is_ignored_safely(self):
        # DRF OrderingFilter silently ignores fields not in ordering_fields — no crash
        resp = self.client.get(PRODUCTS_URL, {'ordering': 'injected_field'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    # ── Combined search + filter ──────────────────────────────────

    def test_search_and_filter_together(self):
        p1 = _product('اسید آسکوربیک', purchase_price=Decimal('200'))
        p2 = _product('اسید سیتریک',  purchase_price=Decimal('800'))
        resp = self.client.get(PRODUCTS_URL, {
            'search': 'اسید', 'price_max': '300', 'is_active': 'all',
        })
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(p1.id, ids)
        self.assertNotIn(p2.id, ids)


class PurchaseOrderingTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.v1 = _vendor('آلفا تامین')
        self.v2 = _vendor('بتا تامین')
        Purchase.objects.create(vendor=self.v1, status=PurchaseStatus.CONFIRMED)
        Purchase.objects.create(vendor=self.v2, status=PurchaseStatus.PENDING)

    def test_sort_by_purchase_date(self):
        resp = self.client.get(PURCHASES_URL, {'ordering': 'purchase_date'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_sort_by_vendor_name(self):
        resp = self.client.get(PURCHASES_URL, {'ordering': 'vendor__name'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_sort_by_status_desc(self):
        resp = self.client.get(PURCHASES_URL, {'ordering': '-status'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_invalid_ordering_is_ignored_safely(self):
        resp = self.client.get(PURCHASES_URL, {'ordering': '__raw_sql'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    def test_filter_and_sort_together(self):
        resp = self.client.get(PURCHASES_URL, {
            'status': 'CONFIRMED', 'ordering': '-purchase_date',
        })
        self.assertEqual(resp.status_code, 200)
        for r in resp.data['results']:
            self.assertEqual(r['status'], 'CONFIRMED')


class PurchaseJalaliDateFilterTest(APITestCase):
    """CLI-70: the purchase date filter accepts Jalali (and still Gregorian).

    Reference: Jalali 1405/04/03 == Gregorian 2026-06-24, so
    1405/04/01 == 2026-06-22.
    """

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.vendor = _vendor('تامین‌کننده')
        self.early = Purchase.objects.create(
            vendor=self.vendor, status=PurchaseStatus.PENDING,
            purchase_date=timezone.make_aware(datetime.datetime(2026, 6, 20, 12, 0)),
        )
        self.late = Purchase.objects.create(
            vendor=self.vendor, status=PurchaseStatus.PENDING,
            purchase_date=timezone.make_aware(datetime.datetime(2026, 6, 24, 12, 0)),
        )

    def _ids(self, resp):
        return [r['id'] for r in resp.data['results']]

    def test_jalali_date_from_filters(self):
        # date_from = 1405/04/01 (= 2026-06-22) → only the 06-24 purchase
        resp = self.client.get(PURCHASES_URL, {'date_from': '1405/04/01'})
        self.assertEqual(resp.status_code, 200)
        ids = self._ids(resp)
        self.assertIn(self.late.id, ids)
        self.assertNotIn(self.early.id, ids)

    def test_persian_digits_date_from(self):
        resp = self.client.get(PURCHASES_URL, {'date_from': '۱۴۰۵/۰۴/۰۱'})
        self.assertEqual(resp.status_code, 200)
        ids = self._ids(resp)
        self.assertIn(self.late.id, ids)
        self.assertNotIn(self.early.id, ids)

    def test_gregorian_date_from_still_works(self):
        # Back-compat: existing Gregorian ISO param resolves identically.
        resp = self.client.get(PURCHASES_URL, {'date_from': '2026-06-22'})
        self.assertEqual(resp.status_code, 200)
        ids = self._ids(resp)
        self.assertIn(self.late.id, ids)
        self.assertNotIn(self.early.id, ids)

    def test_invalid_jalali_date_returns_400(self):
        resp = self.client.get(PURCHASES_URL, {'date_from': '1405/13/40'})
        self.assertEqual(resp.status_code, 400)


class ProductDefaultOrderingTest(APITestCase):
    """CLI-68: the product list defaults to ascending internal_code.

    Products are created with names in the REVERSE order of their internal
    codes, so a name-sort and a code-sort yield different sequences — proving
    the default is genuinely by internal_code, not by name or insertion order.
    """

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        # name آلفا < دلتا < زتا (alphabetical) maps to codes 003, 002, 001
        Product.objects.create(
            name='زتا', internal_code='DEMO-MED-001',
            product_type=ProductType.MEDICINE, unit='عدد',
            purchase_price=Decimal('100'),
        )
        Product.objects.create(
            name='دلتا', internal_code='DEMO-MED-002',
            product_type=ProductType.MEDICINE, unit='عدد',
            purchase_price=Decimal('100'),
        )
        Product.objects.create(
            name='آلفا', internal_code='DEMO-MED-003',
            product_type=ProductType.MEDICINE, unit='عدد',
            purchase_price=Decimal('100'),
        )

    def test_default_ordering_is_internal_code_ascending(self):
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        codes = [r['internal_code'] for r in resp.data['results']]
        self.assertEqual(
            codes, ['DEMO-MED-001', 'DEMO-MED-002', 'DEMO-MED-003']
        )

    def test_default_ordering_is_not_by_name(self):
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        codes = [r['internal_code'] for r in resp.data['results']]
        names = [r['name'] for r in resp.data['results']]
        # A name-sort would put آلفا (code 003) first; code-sort puts 001 first.
        self.assertEqual(codes[0], 'DEMO-MED-001')
        self.assertNotEqual(names, sorted(names))

    def test_explicit_ordering_by_name_still_works(self):
        resp = self.client.get(PRODUCTS_URL, {'ordering': 'name', 'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        names = [r['name'] for r in resp.data['results']]
        self.assertEqual(names, sorted(names))

    def test_explicit_ordering_by_internal_code_descending(self):
        resp = self.client.get(
            PRODUCTS_URL, {'ordering': '-internal_code', 'is_active': 'all'}
        )
        self.assertEqual(resp.status_code, 200)
        codes = [r['internal_code'] for r in resp.data['results']]
        self.assertEqual(
            codes, ['DEMO-MED-003', 'DEMO-MED-002', 'DEMO-MED-001']
        )

    def test_default_ordering_is_natural_for_numeric_codes(self):
        # Bare-integer codes must sort numerically (1,2,3,10,24), NOT
        # lexically (1,10,2,24,3).
        Product.objects.all().delete()
        for code in ['10', '2', '24', '1', '3']:
            Product.objects.create(
                name=f'P-{code}', internal_code=code,
                product_type=ProductType.MEDICINE, unit='عدد',
                purchase_price=Decimal('100'),
            )
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        codes = [r['internal_code'] for r in resp.data['results']]
        self.assertEqual(codes, ['1', '2', '3', '10', '24'])

    def test_default_ordering_mixes_numeric_then_prefixed(self):
        # Mirrors the real data: bare integers come first in numeric order,
        # then the longer prefixed codes — never 1, 2, 24, 25, 3.
        Product.objects.all().delete()
        for code in ['DEMO-EQP-002', '3', '24', '1', '2', 'DEMO-EQP-004']:
            Product.objects.create(
                name=f'P-{code}', internal_code=code,
                product_type=ProductType.MEDICINE, unit='عدد',
                purchase_price=Decimal('100'),
            )
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'all'})
        self.assertEqual(resp.status_code, 200)
        codes = [r['internal_code'] for r in resp.data['results']]
        self.assertEqual(
            codes, ['1', '2', '3', '24', 'DEMO-EQP-002', 'DEMO-EQP-004']
        )
