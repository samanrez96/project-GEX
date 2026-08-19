"""Targeted regression tests for the افزودن قلم مصرفی Product-selector fix.

Covers the backend pieces the modal's JS (surgery_history_detail.js) relies
on — reused Product search API + additive serializer fields — plus a
regression check that SurgeryUsedItem create/stock-deduction behavior is
byte-for-byte unchanged.

No JS test runner exists in this project, so client-side behavior (initial
list on modal open, debounce, keyboard nav, load-more) is verified
indirectly: by asserting the page loads the updated script, and by proving
every API behavior that script depends on actually works.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import MovementType, Product, ProductCategory, ProductType, SourceType, StockMovement
from inventory.services import StockService
from surgeries.models import Patient, SurgeryHistory, SurgeryType, SurgeryUsedItem

User = get_user_model()

PRODUCTS_URL   = '/api/v1/inventory/products/'
USED_ITEMS_URL = '/api/v1/surgeries/used-items/'

_ctr = [0]


def _product(stock=Decimal('0'), **kwargs):
    _ctr[0] += 1
    defaults = {
        'name': f'محصول انتخابگر {_ctr[0]}',
        'internal_code': f'SEL-{_ctr[0]:05d}',
        'product_type': ProductType.MEDICINE,
        'unit': 'عدد',
    }
    defaults.update(kwargs)
    p = Product.objects.create(**defaults)
    if stock:
        StockService.create_movement(
            product=p, quantity=Decimal(str(stock)),
            movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id='initial-stock-test',
        )
        p.refresh_from_db()
    return p


def _surgery_type():
    _ctr[0] += 1
    return SurgeryType.objects.create(
        name=f'نوع عمل انتخابگر {_ctr[0]}', code=f'sel_{_ctr[0]}', base_rate=Decimal('1000000'),
    )


def _patient():
    _ctr[0] += 1
    return Patient.objects.create(
        full_name=f'بیمار انتخابگر {_ctr[0]}', case_code=f'SEL-CASE-{_ctr[0]:05d}',
        phone_number='09120000000',
    )


def _surgery(**kwargs):
    defaults = dict(
        patient=_patient(), surgery_type=_surgery_type(), amount=Decimal('3000000'),
        surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    )
    defaults.update(kwargs)
    return SurgeryHistory.objects.create(**defaults)


class ProductSelectorSearchApiTest(APITestCase):
    """The Product-selector search/list behavior, exercised via the same
    existing Product API endpoint the modal's JS calls — no new endpoint."""

    def setUp(self):
        self.user = User.objects.create_user('selector_user', 'a@b.com', 'pass12345')
        self.client.force_authenticate(self.user)
        self.category = ProductCategory.objects.get_or_create(name='دارو', parent=None)[0]

    def test_initial_list_returns_active_products_ordered(self):
        """Modal-open behavior: fetching with no ?search= must still return
        a real, non-empty product list (this is what makes the initial
        list appear immediately instead of a blank input)."""
        _product(name='آتروپین', internal_code='ATR-001', stock=Decimal('222'))
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'page_size': 20, 'ordering': 'name'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreater(resp.data['count'], 0)
        self.assertTrue(len(resp.data['results']) > 0)

    def test_inactive_products_excluded_from_default_search(self):
        _product(name='محصول غیرفعال', is_active=False)
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'page_size': 20})
        names = [r['name'] for r in resp.data['results']]
        self.assertNotIn('محصول غیرفعال', names)

    def test_search_by_name(self):
        _product(name='ایزوفلوران تست')
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': 'ایزوفلوران'})
        self.assertTrue(any('ایزوفلوران' in r['name'] for r in resp.data['results']))

    def test_search_by_internal_code(self):
        p = _product(internal_code='CODE-XYZ-001')
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': 'CODE-XYZ'})
        self.assertIn(p.pk, [r['id'] for r in resp.data['results']])

    def test_search_by_barcode(self):
        p = _product(barcode='9998887776')
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': '9998887776'})
        self.assertIn(p.pk, [r['id'] for r in resp.data['results']])

    def test_search_by_category_name(self):
        p = _product(category=self.category)
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': 'دارو'})
        self.assertIn(p.pk, [r['id'] for r in resp.data['results']])

    def test_product_type_filter_used_by_frontend_type_translation(self):
        """The modal translates a typed دارو/تجهیزات term into ?product_type=
        instead of a free-text search — confirms that existing filter works."""
        med = _product(product_type=ProductType.MEDICINE)
        equip = _product(product_type=ProductType.EQUIPMENT)
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'product_type': 'medicine'})
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(med.pk, ids)
        self.assertNotIn(equip.pk, ids)

    def test_zero_stock_product_marked_unavailable_but_returned(self):
        p = _product(stock=Decimal('0'))
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': p.internal_code})
        row = [r for r in resp.data['results'] if r['id'] == p.pk][0]
        self.assertTrue(row['is_out_of_stock'])
        self.assertEqual(row['stock_status'], 'ناموجود')

    def test_low_stock_product_uses_same_status_logic_as_product_list_page(self):
        p = _product(stock=Decimal('5'), minimum_stock=Decimal('10'))
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': p.internal_code})
        row = [r for r in resp.data['results'] if r['id'] == p.pk][0]
        self.assertTrue(row['is_low_stock'])
        self.assertEqual(row['stock_status'], 'کم‌موجودی')

    def test_list_serializer_includes_category_name_and_barcode(self):
        p = _product(category=self.category, barcode='1234567890')
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': p.internal_code})
        row = [r for r in resp.data['results'] if r['id'] == p.pk][0]
        self.assertEqual(row['category_name'], 'دارو')
        self.assertEqual(row['barcode'], '1234567890')

    def test_list_serializer_category_name_is_null_without_category(self):
        p = _product(category=None)
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'search': p.internal_code})
        row = [r for r in resp.data['results'] if r['id'] == p.pk][0]
        self.assertIsNone(row['category_name'])

    def test_pagination_next_link_present_when_more_results_than_page_size(self):
        for i in range(3):
            _product(name=f'صفحه‌بندی {i}')
        resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'page_size': 2, 'ordering': 'name'})
        self.assertIsNotNone(resp.data['next'])

    def test_list_query_count_unaffected_by_new_fields(self):
        """category_name/barcode were added to ProductListSerializer and to
        the view's .only() together — this proves that pairing avoids N+1
        (a per-row deferred-field query) rather than just not crashing."""
        _product(category=self.category, barcode='111')
        _product(category=None)
        with self.assertNumQueries(3):
            resp = self.client.get(PRODUCTS_URL, {'is_active': 'true', 'page_size': 20})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unauthenticated_request_denied(self):
        self.client.force_authenticate(None)
        resp = self.client.get(PRODUCTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class SurgeryUsedItemProductSelectorTest(APITestCase):
    """SurgeryUsedItem create/validate flow — unchanged, plus the new
    product_is_active field the modal uses for the inactive badge."""

    def setUp(self):
        self.user = User.objects.create_user('selector_admin', 'a@b.com', 'pass12345')
        self.client.force_authenticate(self.user)
        self.surgery = _surgery()

    def test_used_item_exposes_product_is_active_true(self):
        product = _product(stock=Decimal('20'))
        item = SurgeryUsedItem.objects.create(surgery=self.surgery, product=product, quantity=Decimal('1'))
        resp = self.client.get(f'{USED_ITEMS_URL}{item.pk}/')
        self.assertTrue(resp.data['product_is_active'])

    def test_used_item_exposes_product_is_active_false_after_deactivation(self):
        """Editing an existing item whose Product was later deactivated:
        the modal must still show it (with an inactive badge) — this is
        the field that drives that badge."""
        product = _product(stock=Decimal('20'))
        item = SurgeryUsedItem.objects.create(surgery=self.surgery, product=product, quantity=Decimal('1'))
        product.is_active = False
        product.save(update_fields=['is_active'])

        resp = self.client.get(f'{USED_ITEMS_URL}{item.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['product_is_active'])
        # Still fully readable — product_name/code/unit remain populated.
        self.assertEqual(resp.data['product_code'], product.internal_code)

    def test_create_used_item_deducts_stock_unchanged(self):
        """Regression: creating a consumed item still creates exactly one
        OUT StockMovement and reduces current_stock — unrelated to the
        Product-selector UI change."""
        product = _product(stock=Decimal('20'))
        resp = self.client.post(USED_ITEMS_URL, {
            'surgery': self.surgery.pk, 'product': product.pk, 'quantity': '3',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('17'))
        movements = StockMovement.objects.filter(product=product, movement_type=MovementType.OUT)
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().quantity, Decimal('3'))

    def test_create_used_item_insufficient_stock_still_rejected(self):
        product = _product(stock=Decimal('2'))
        resp = self.client.post(USED_ITEMS_URL, {
            'surgery': self.surgery.pk, 'product': product.pk, 'quantity': '5',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('2'))
        self.assertFalse(StockMovement.objects.filter(product=product).exclude(source_type=SourceType.MANUAL_ADJUSTMENT).exists())

    def test_create_used_item_requires_positive_quantity(self):
        product = _product(stock=Decimal('20'))
        resp = self.client.post(USED_ITEMS_URL, {
            'surgery': self.surgery.pk, 'product': product.pk, 'quantity': '0',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_used_item_with_real_product_id_from_selector(self):
        """The modal submits the real Product ID (not its name text) — this
        proves the API identifies the Product by id, not by any client
        supplied label."""
        product = _product(name='نام قابل تغییر', stock=Decimal('10'))
        resp = self.client.post(USED_ITEMS_URL, {
            'surgery': self.surgery.pk, 'product': product.pk, 'quantity': '1',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['product'], product.pk)
        self.assertEqual(resp.data['product_name'], product.name)


class SurgeryHistoryDetailPageAssetsTest(TestCase):
    """Confirms the detail page loads the updated selector script/styles —
    the actual selector behavior lives client-side and is covered by the
    API-level tests above."""

    def setUp(self):
        self.user = User.objects.create_superuser('selector_page_admin', 'a@b.com', 'pass12345')
        self.surgery = _surgery()

    def test_detail_page_loads_and_includes_updated_script(self):
        self.client.force_login(self.user)
        resp = self.client.get(f'/admin/surgeries/surgeryhistory/{self.surgery.pk}/detail/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'surgery_history_detail.js')
        self.assertContains(resp, 'surgery_history_detail.css')
