"""Validation message tests for inventory endpoints (CLI-60).

Verifies that API returns clear Persian validation messages for:
- negative purchase_price / sale_price
- duplicate internal_code
- negative unit_price on purchase items
- zero/negative quantity on purchase items
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import Product, ProductType, Purchase, PurchaseStatus, Vendor

User = get_user_model()
PRODUCTS_URL  = '/api/v1/inventory/products/'
PURCHASES_URL = '/api/v1/inventory/purchases/'
ITEMS_URL     = '/api/v1/inventory/purchase-items/'


def _user():
    return User.objects.create_user(username=f'vm_{User.objects.count()}', password='x')


def _product(name='Prod', price=Decimal('100')):
    import random
    uid = random.randint(100000, 999999)
    return Product.objects.create(
        name=name,
        internal_code=f'TEST-{uid}',
        product_type=ProductType.MEDICINE,
        unit='عدد',
        purchase_price=price,
    )


class ProductValidationTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)

    # ── purchase_price ────────────────────────────────────────────

    def test_negative_purchase_price_rejected(self):
        import random
        uid = random.randint(100000, 999999)
        resp = self.client.post(PRODUCTS_URL, {
            'name': 'داروی آزمایش',
            'internal_code': f'NEG-{uid}',
            'product_type': 'medicine',
            'unit': 'عدد',
            'purchase_price': '-100',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('purchase_price', resp.data)
        errors = str(resp.data['purchase_price'])
        self.assertIn('منفی', errors)

    def test_zero_purchase_price_is_allowed(self):
        import random
        uid = random.randint(100000, 999999)
        resp = self.client.post(PRODUCTS_URL, {
            'name': 'محصول رایگان',
            'internal_code': f'FREE-{uid}',
            'product_type': 'medicine',
            'unit': 'عدد',
            'purchase_price': '0',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    # ── sale_price ────────────────────────────────────────────────

    def test_negative_sale_price_rejected(self):
        import random
        uid = random.randint(100000, 999999)
        resp = self.client.post(PRODUCTS_URL, {
            'name': 'محصول فروش',
            'internal_code': f'SALE-{uid}',
            'product_type': 'medicine',
            'unit': 'عدد',
            'purchase_price': '100',
            'sale_price': '-50',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('sale_price', resp.data)
        errors = str(resp.data['sale_price'])
        self.assertIn('منفی', errors)

    # ── internal_code uniqueness ──────────────────────────────────

    def test_duplicate_internal_code_returns_persian_message(self):
        existing = _product('موجود', Decimal('100'))
        resp = self.client.post(PRODUCTS_URL, {
            'name': 'محصول دوم',
            'internal_code': existing.internal_code,
            'product_type': 'medicine',
            'unit': 'عدد',
            'purchase_price': '100',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('internal_code', resp.data)
        errors = str(resp.data['internal_code'])
        self.assertIn('قبلاً ثبت شده', errors)

    def test_unique_internal_code_is_accepted(self):
        import random
        uid = random.randint(100000, 999999)
        resp = self.client.post(PRODUCTS_URL, {
            'name': 'محصول جدید',
            'internal_code': f'UNIQ-{uid}',
            'product_type': 'medicine',
            'unit': 'عدد',
            'purchase_price': '200',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class PurchaseItemValidationTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        vendor   = Vendor.objects.create(name='تامین آزمایش')
        self.purchase = Purchase.objects.create(
            vendor=vendor, status=PurchaseStatus.PENDING,
        )
        self.product = _product()

    def test_negative_unit_price_rejected(self):
        resp = self.client.post(ITEMS_URL, {
            'purchase':   self.purchase.id,
            'product':    self.product.id,
            'quantity':   '5',
            'unit_price': '-10',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('unit_price', resp.data)
        errors = str(resp.data['unit_price'])
        self.assertIn('منفی', errors)

    def test_zero_quantity_rejected(self):
        resp = self.client.post(ITEMS_URL, {
            'purchase':   self.purchase.id,
            'product':    self.product.id,
            'quantity':   '0',
            'unit_price': '100',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity', resp.data)

    def test_valid_item_accepted(self):
        resp = self.client.post(ITEMS_URL, {
            'purchase':   self.purchase.id,
            'product':    self.product.id,
            'quantity':   '3',
            'unit_price': '50',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
