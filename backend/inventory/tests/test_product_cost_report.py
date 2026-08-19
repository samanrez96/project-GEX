"""Tests for CLI-51: Product Cost Report.

Covers:
  - Total cost calculation (qty × unit_price) for confirmed purchases
  - Date range filtering
  - product_type filter (medicine / equipment)
  - group_by=product (default)
  - group_by=vendor
  - group_by=product_vendor
  - vendor_id filter
  - Highest-cost row is first
  - Cancelled and pending purchases are excluded
  - Zero-item result returns empty results with 0 totals
  - Permission enforcement (admin, finance_user, inventory_user, unauthenticated)
  - Pagination: count, next, previous
  - Metadata block present in every response
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import Product, Purchase, PurchaseItem, PurchaseStatus, Vendor

User = get_user_model()

REPORT_URL = '/api/v1/inventory/reports/cost/'

_seq = [0]


def _next():
    _seq[0] += 1
    return _seq[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vendor(**kw):
    n = _next()
    d = {'name': f'تأمین‌کننده {n}', 'phone_number': f'021{n:07d}'}
    d.update(kw)
    return Vendor.objects.create(**d)


def _product(product_type='medicine', **kw):
    n = _next()
    d = {
        'name':          f'محصول {n}',
        'internal_code': f'PRD-{n:04d}',
        'product_type':  product_type,
        'unit':          'عدد',
        'purchase_price': Decimal('1000'),
        'sale_price':     Decimal('1500'),
    }
    d.update(kw)
    return Product.objects.create(**d)


def _purchase(vendor, purchase_date=None, status=PurchaseStatus.CONFIRMED):
    if purchase_date is None:
        purchase_date = datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc)
    return Purchase.objects.create(
        vendor=vendor,
        purchase_date=purchase_date,
        status=status,
    )


def _item(purchase, product, quantity, unit_price):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=Decimal(str(quantity)),
        unit_price=Decimal(str(unit_price)),
        unit=product.unit,
    )


def _user_in_group(username, group_name):
    user = User.objects.create_user(username=username, password='pass')
    grp, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(grp)
    return user


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------

class ProductCostReportBase(APITestCase):
    """Set up two vendors, two products, two purchases with items."""

    def setUp(self):
        self.superuser = User.objects.create_superuser('sa', 'sa@t.com', 'pass')

        self.vendor_a = _vendor()
        self.vendor_b = _vendor()

        self.medicine    = _product(product_type='medicine')
        self.equipment   = _product(product_type='equipment')

        # Jan purchase from vendor_a: medicine×10 @ 5000, equipment×5 @ 20000
        self.purchase_jan = _purchase(
            self.vendor_a,
            purchase_date=datetime.datetime(2025, 1, 15, tzinfo=datetime.timezone.utc),
        )
        self.item_med_jan  = _item(self.purchase_jan, self.medicine,  10, 5000)
        self.item_equip    = _item(self.purchase_jan, self.equipment,  5, 20000)
        # cost: medicine=50000, equipment=100000, total=150000

        # Jun purchase from vendor_b: medicine×20 @ 6000
        self.purchase_jun = _purchase(
            self.vendor_b,
            purchase_date=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc),
        )
        self.item_med_jun = _item(self.purchase_jun, self.medicine, 20, 6000)
        # cost: medicine=120000, total=120000

        self.client.force_authenticate(user=self.superuser)


# ---------------------------------------------------------------------------
# Total cost calculation
# ---------------------------------------------------------------------------

class ProductCostTotalTest(ProductCostReportBase):

    def test_grand_total_cost(self):
        # medicine: 10*5000 + 20*6000 = 50000+120000 = 170000
        # equipment: 5*20000 = 100000
        # grand total = 270000
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(res.data['metadata']['total_cost']),
            Decimal('270000'),
        )

    def test_grand_total_quantity(self):
        # 10+5+20 = 35
        res = self.client.get(REPORT_URL)
        self.assertEqual(
            Decimal(res.data['metadata']['total_quantity']),
            Decimal('35'),
        )

    def test_total_line_items(self):
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.data['metadata']['total_line_items'], 3)

    def test_results_sorted_by_total_cost_desc(self):
        res = self.client.get(REPORT_URL)
        costs = [Decimal(r['total_cost']) for r in res.data['results']]
        self.assertEqual(costs, sorted(costs, reverse=True))

    def test_highest_cost_product_is_first(self):
        # medicine total: 50000+120000=170000 > equipment: 100000
        res = self.client.get(REPORT_URL)
        first = res.data['results'][0]
        self.assertEqual(first['product_id'], self.medicine.pk)
        self.assertEqual(Decimal(first['total_cost']), Decimal('170000'))

    def test_per_product_totals(self):
        res = self.client.get(REPORT_URL)
        by_id = {r['product_id']: r for r in res.data['results']}
        self.assertEqual(Decimal(by_id[self.medicine.pk]['total_cost']),   Decimal('170000'))
        self.assertEqual(Decimal(by_id[self.equipment.pk]['total_cost']),  Decimal('100000'))
        self.assertEqual(Decimal(by_id[self.medicine.pk]['total_quantity']), Decimal('30'))
        self.assertEqual(Decimal(by_id[self.equipment.pk]['total_quantity']), Decimal('5'))

    def test_purchase_count_per_product(self):
        res = self.client.get(REPORT_URL)
        by_id = {r['product_id']: r for r in res.data['results']}
        # medicine appears in 2 purchase items
        self.assertEqual(by_id[self.medicine.pk]['purchase_count'], 2)
        self.assertEqual(by_id[self.equipment.pk]['purchase_count'], 1)


# ---------------------------------------------------------------------------
# Date range filter
# ---------------------------------------------------------------------------

class ProductCostDateFilterTest(ProductCostReportBase):

    def test_start_date_excludes_earlier_purchases(self):
        # Only Jun purchase (purchase_jun): medicine×20@6000 = 120000
        res = self.client.get(REPORT_URL, {'start_date': '2025-06-01'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('120000'))
        self.assertEqual(len(res.data['results']), 1)

    def test_end_date_excludes_later_purchases(self):
        # Only Jan purchase: 50000 + 100000 = 150000
        res = self.client.get(REPORT_URL, {'end_date': '2025-01-31'})
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('150000'))

    def test_date_range_both_bounds(self):
        res = self.client.get(REPORT_URL, {'start_date': '2025-01-01', 'end_date': '2025-01-31'})
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('150000'))

    def test_date_range_no_results(self):
        res = self.client.get(REPORT_URL, {'start_date': '2024-01-01', 'end_date': '2024-12-31'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('0'))
        self.assertEqual(res.data['count'], 0)
        self.assertEqual(res.data['results'], [])


# ---------------------------------------------------------------------------
# product_type filter
# ---------------------------------------------------------------------------

class ProductCostTypeFilterTest(ProductCostReportBase):

    def test_filter_medicine_only(self):
        res = self.client.get(REPORT_URL, {'product_type': 'medicine'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('170000'))
        # Only one product in results
        self.assertEqual(len(res.data['results']), 1)
        self.assertEqual(res.data['results'][0]['product_id'], self.medicine.pk)

    def test_filter_equipment_only(self):
        res = self.client.get(REPORT_URL, {'product_type': 'equipment'})
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('100000'))
        self.assertEqual(len(res.data['results']), 1)
        self.assertEqual(res.data['results'][0]['product_id'], self.equipment.pk)

    def test_no_type_filter_returns_all(self):
        res = self.client.get(REPORT_URL)
        self.assertEqual(len(res.data['results']), 2)

    def test_invalid_type_returns_all(self):
        res = self.client.get(REPORT_URL, {'product_type': 'other'})
        # Invalid type → no filter → all products
        self.assertEqual(len(res.data['results']), 2)

    def test_metadata_reflects_filter(self):
        res = self.client.get(REPORT_URL, {'product_type': 'medicine'})
        self.assertEqual(res.data['metadata']['product_type'], 'medicine')


# ---------------------------------------------------------------------------
# group_by=vendor
# ---------------------------------------------------------------------------

class ProductCostGroupByVendorTest(ProductCostReportBase):

    def test_group_by_vendor_returns_vendor_fields(self):
        res = self.client.get(REPORT_URL, {'group_by': 'vendor'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for row in res.data['results']:
            self.assertIn('vendor_id',   row)
            self.assertIn('vendor_name', row)

    def test_group_by_vendor_no_product_fields(self):
        res = self.client.get(REPORT_URL, {'group_by': 'vendor'})
        for row in res.data['results']:
            self.assertNotIn('product_id', row)

    def test_vendor_totals(self):
        res = self.client.get(REPORT_URL, {'group_by': 'vendor'})
        by_vendor = {r['vendor_id']: r for r in res.data['results']}
        # vendor_a: 50000+100000=150000
        self.assertEqual(Decimal(by_vendor[self.vendor_a.pk]['total_cost']), Decimal('150000'))
        # vendor_b: 120000
        self.assertEqual(Decimal(by_vendor[self.vendor_b.pk]['total_cost']), Decimal('120000'))

    def test_highest_cost_vendor_first(self):
        res = self.client.get(REPORT_URL, {'group_by': 'vendor'})
        self.assertEqual(res.data['results'][0]['vendor_id'], self.vendor_a.pk)


# ---------------------------------------------------------------------------
# group_by=product_vendor (most granular)
# ---------------------------------------------------------------------------

class ProductCostGroupByProductVendorTest(ProductCostReportBase):

    def test_group_by_product_vendor_returns_all_fields(self):
        res = self.client.get(REPORT_URL, {'group_by': 'product_vendor'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for row in res.data['results']:
            self.assertIn('product_id', row)
            self.assertIn('vendor_id',  row)

    def test_product_vendor_row_count(self):
        # (medicine, vendor_a), (equipment, vendor_a), (medicine, vendor_b) = 3 rows
        res = self.client.get(REPORT_URL, {'group_by': 'product_vendor'})
        self.assertEqual(res.data['count'], 3)

    def test_product_vendor_per_row_totals(self):
        res = self.client.get(REPORT_URL, {'group_by': 'product_vendor'})
        # find (medicine, vendor_a) row
        row = next(
            r for r in res.data['results']
            if r['product_id'] == self.medicine.pk and r['vendor_id'] == self.vendor_a.pk
        )
        self.assertEqual(Decimal(row['total_cost']), Decimal('50000'))


# ---------------------------------------------------------------------------
# vendor_id filter
# ---------------------------------------------------------------------------

class ProductCostVendorFilterTest(ProductCostReportBase):

    def test_vendor_id_limits_to_that_vendor(self):
        res = self.client.get(REPORT_URL, {'vendor_id': self.vendor_b.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('120000'))

    def test_vendor_id_nonexistent_returns_empty(self):
        res = self.client.get(REPORT_URL, {'vendor_id': 99999})
        self.assertEqual(Decimal(res.data['metadata']['total_cost']), Decimal('0'))
        self.assertEqual(res.data['count'], 0)


# ---------------------------------------------------------------------------
# Excluded statuses
# ---------------------------------------------------------------------------

class ProductCostExcludedStatusTest(ProductCostReportBase):

    def test_cancelled_purchases_excluded(self):
        vendor = _vendor()
        prod   = _product()
        cancelled_purchase = _purchase(vendor, status=PurchaseStatus.CANCELLED)
        _item(cancelled_purchase, prod, 100, 10000)

        res = self.client.get(REPORT_URL)
        # The new product should NOT appear in the cost report
        product_ids = [r.get('product_id') for r in res.data['results']]
        self.assertNotIn(prod.pk, product_ids)

    def test_pending_purchases_excluded(self):
        vendor = _vendor()
        prod   = _product()
        pending_purchase = _purchase(vendor, status=PurchaseStatus.PENDING)
        _item(pending_purchase, prod, 50, 8000)

        res = self.client.get(REPORT_URL)
        product_ids = [r.get('product_id') for r in res.data['results']]
        self.assertNotIn(prod.pk, product_ids)

    def test_product_with_no_purchases_absent(self):
        prod_no_purchase = _product()
        res = self.client.get(REPORT_URL)
        product_ids = [r.get('product_id') for r in res.data['results']]
        self.assertNotIn(prod_no_purchase.pk, product_ids)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class ProductCostPermissionsTest(ProductCostReportBase):

    def test_superuser_allowed(self):
        self.client.force_authenticate(user=self.superuser)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_finance_user_allowed(self):
        user = _user_in_group(f'finance_{_next()}', 'finance_user')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_admin_group_user_allowed(self):
        user = _user_in_group(f'admin_{_next()}', 'admin')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_inventory_user_forbidden(self):
        user = _user_in_group(f'inv_{_next()}', 'inventory_user')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_manager_forbidden(self):
        user = _user_in_group(f'empmgr_{_next()}', 'employee_manager')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Metadata block
# ---------------------------------------------------------------------------

class ProductCostMetadataTest(ProductCostReportBase):

    def test_metadata_fields_present(self):
        res = self.client.get(REPORT_URL)
        meta = res.data['metadata']
        for field in [
            'start_date', 'end_date', 'product_type', 'group_by',
            'vendor_id', 'total_cost', 'total_quantity', 'total_line_items',
        ]:
            self.assertIn(field, meta, msg=f'Missing metadata field: {field}')

    def test_metadata_defaults(self):
        res = self.client.get(REPORT_URL)
        meta = res.data['metadata']
        self.assertIsNone(meta['start_date'])
        self.assertIsNone(meta['end_date'])
        self.assertEqual(meta['product_type'], 'all')
        self.assertEqual(meta['group_by'], 'product')
        self.assertIsNone(meta['vendor_id'])

    def test_metadata_group_by_reflected(self):
        res = self.client.get(REPORT_URL, {'group_by': 'vendor'})
        self.assertEqual(res.data['metadata']['group_by'], 'vendor')

    def test_metadata_invalid_group_by_defaults_to_product(self):
        res = self.client.get(REPORT_URL, {'group_by': 'nonsense'})
        self.assertEqual(res.data['metadata']['group_by'], 'product')


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class ProductCostPaginationTest(ProductCostReportBase):

    def test_count_matches_total_rows(self):
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.data['count'], len(res.data['results']))

    def test_page_size_respected(self):
        res = self.client.get(REPORT_URL, {'page_size': '1'})
        self.assertEqual(len(res.data['results']), 1)
        self.assertEqual(res.data['count'], 2)
        self.assertIsNotNone(res.data['next'])
        self.assertIsNone(res.data['previous'])

    def test_second_page(self):
        res = self.client.get(REPORT_URL, {'page': '2', 'page_size': '1'})
        self.assertEqual(len(res.data['results']), 1)
        self.assertIsNone(res.data['next'])
        self.assertIsNotNone(res.data['previous'])

    def test_empty_result_no_next_or_previous(self):
        res = self.client.get(REPORT_URL, {'start_date': '2020-01-01', 'end_date': '2020-12-31'})
        self.assertIsNone(res.data['next'])
        self.assertIsNone(res.data['previous'])
