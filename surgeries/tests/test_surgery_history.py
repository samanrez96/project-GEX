"""Tests for SurgeryUsedItem inventory integration (CLI-36, extended CLI-71).

Covers:
  - Correct stock decrease on creation
  - OUT StockMovement created with correct fields
  - Insufficient stock rejected, no side-effects
  - Zero / negative quantity rejected
  - PATCHing only description creates no movement
  - PATCHing product/quantity now reconciles stock via a compensating
    movement (see test_surgery_used_item_edit_delete.py for the full
    create/update/delete + idempotency regression suite)
  - Atomic rollback: item not persisted when movement fails
  - API endpoints: create, insufficient stock, update, auth
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, GenderChoice, JobPosition
from inventory.models import MovementType, Product, ProductType, SourceType, StockMovement
from surgeries.models import Patient, SurgeryHistory, SurgeryStatus, SurgeryType, SurgeryUsedItem

User = get_user_model()

USED_ITEMS_URL = '/api/v1/surgeries/used-items/'

_counter = [0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _product(**kwargs):
    _counter[0] += 1
    defaults = {
        'name':          f'دارو {_counter[0]}',
        'internal_code': f'MED-{_counter[0]:04d}',
        'product_type':  ProductType.MEDICINE,
        'unit':          'ml',
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def _surgery_type(**kwargs):
    _counter[0] += 1
    defaults = {
        'name':      f'نوع عمل {_counter[0]}',
        'code':      f'op_{_counter[0]}',
        'base_rate': Decimal('1000000'),
    }
    defaults.update(kwargs)
    return SurgeryType.objects.create(**defaults)


def _patient(**kwargs):
    _counter[0] += 1
    defaults = {
        'full_name':    f'بیمار {_counter[0]}',
        'case_code':    f'CASE-{_counter[0]:04d}',
        'phone_number': f'091{str(_counter[0]).zfill(8)}',
    }
    defaults.update(kwargs)
    return Patient.objects.create(**defaults)


def _surgery_history(patient=None, surgery_type=None, **kwargs):
    if patient is None:
        patient = _patient()
    if surgery_type is None:
        surgery_type = _surgery_type()
    defaults = {
        'patient':      patient,
        'surgery_type': surgery_type,
        'amount':       Decimal('5000000'),
        'surgery_date': datetime.datetime(2025, 1, 15, 10, 0, tzinfo=datetime.timezone.utc),
    }
    defaults.update(kwargs)
    return SurgeryHistory.objects.create(**defaults)


def _used_item(surgery, product, quantity='10.000', **kwargs):
    return SurgeryUsedItem.objects.create(
        surgery=surgery,
        product=product,
        quantity=Decimal(quantity),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Model / service-level tests
# ---------------------------------------------------------------------------

class SurgeryUsedItemInventoryTest(TestCase):

    def setUp(self):
        self.product = _product()
        self.product._apply_stock_delta(Decimal('100'))  # seed stock
        self.surgery = _surgery_history()

    def test_create_used_item_decreases_product_stock(self):
        from surgeries.services import SurgeryInventoryService

        item = _used_item(self.surgery, self.product, quantity='20')
        SurgeryInventoryService.consume_product(item)

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('80'))

    def test_create_used_item_creates_out_stock_movement(self):
        from surgeries.services import SurgeryInventoryService

        item = _used_item(self.surgery, self.product, quantity='15')
        SurgeryInventoryService.consume_product(item)

        mv = StockMovement.objects.filter(
            product=self.product,
            movement_type=MovementType.OUT,
        ).latest('created_at')
        self.assertEqual(mv.source_type, SourceType.SURGERY_CONSUMPTION)
        self.assertEqual(mv.quantity, Decimal('15'))

    def test_movement_reference_id_contains_surgery_pk(self):
        from surgeries.services import SurgeryInventoryService

        item = _used_item(self.surgery, self.product, quantity='5')
        SurgeryInventoryService.consume_product(item)

        mv = StockMovement.objects.filter(
            product=self.product,
            movement_type=MovementType.OUT,
        ).latest('created_at')
        self.assertIn(str(self.surgery.pk), mv.reference_id)

    def test_insufficient_stock_raises_validation_error(self):
        from surgeries.services import SurgeryInventoryService

        item = _used_item(self.surgery, self.product, quantity='999')
        with self.assertRaises(ValidationError):
            SurgeryInventoryService.consume_product(item)

    def test_insufficient_stock_leaves_stock_unchanged(self):
        from surgeries.services import SurgeryInventoryService

        item = _used_item(self.surgery, self.product, quantity='999')
        try:
            SurgeryInventoryService.consume_product(item)
        except ValidationError:
            pass

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('100'))

    def test_quantity_zero_rejected_by_service(self):
        from django.core.exceptions import ValidationError as DjangoVE
        from surgeries.services import SurgeryInventoryService

        # Build item in-memory without going through clean() to test service alone
        item = SurgeryUsedItem(
            surgery=self.surgery,
            product=self.product,
            quantity=Decimal('0'),
        )
        with self.assertRaises((ValidationError, DjangoVE)):
            SurgeryInventoryService.consume_product(item)

    def test_atomic_rollback_item_not_saved_when_movement_fails(self):
        """If stock is insufficient, the item INSERT must be rolled back."""
        from django.db import transaction
        from django.core.exceptions import ValidationError as DjangoVE
        from rest_framework.exceptions import ValidationError as DRFVe
        from surgeries.services import SurgeryInventoryService

        item_count_before = SurgeryUsedItem.objects.count()
        movement_count_before = StockMovement.objects.count()

        # Simulate what perform_create() does: save item then call service
        try:
            with transaction.atomic():
                item = SurgeryUsedItem.objects.create(
                    surgery=self.surgery,
                    product=self.product,
                    quantity=Decimal('999'),  # more than 100 available
                )
                SurgeryInventoryService.consume_product(item)  # should raise
        except (ValidationError, DjangoVE):
            pass

        self.assertEqual(SurgeryUsedItem.objects.count(), item_count_before)
        self.assertEqual(StockMovement.objects.count(), movement_count_before)

    def test_movement_date_matches_surgery_date(self):
        from surgeries.services import SurgeryInventoryService

        item = _used_item(self.surgery, self.product, quantity='5')
        SurgeryInventoryService.consume_product(item)

        mv = StockMovement.objects.filter(
            product=self.product, movement_type=MovementType.OUT,
        ).latest('created_at')

        self.assertEqual(mv.movement_date, self.surgery.surgery_date)


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------

class SurgeryUsedItemAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('useditemtest', 'u@test.com', 'pass')
        self.client.force_authenticate(user=self.user)

        self.product = _product()
        self.product._apply_stock_delta(Decimal('100'))
        self.surgery = _surgery_history()

    def _post(self, quantity='10.000', product=None, **extra):
        product = product or self.product
        return self.client.post(USED_ITEMS_URL, {
            'surgery':  self.surgery.pk,
            'product':  product.pk,
            'quantity': quantity,
            **extra,
        }, format='json')

    def test_post_creates_item_and_decreases_stock(self):
        res = self._post(quantity='25')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('75'))

    def test_post_creates_out_stock_movement(self):
        self._post(quantity='30')
        mv = StockMovement.objects.filter(
            product=self.product, movement_type=MovementType.OUT,
        ).latest('created_at')
        self.assertEqual(mv.source_type, SourceType.SURGERY_CONSUMPTION)
        self.assertEqual(mv.quantity, Decimal('30'))

    def test_post_insufficient_stock_returns_400(self):
        res = self._post(quantity='999')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_insufficient_stock_stock_unchanged(self):
        self._post(quantity='999')
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('100'))

    def test_post_insufficient_stock_item_not_persisted(self):
        count_before = SurgeryUsedItem.objects.count()
        self._post(quantity='999')
        self.assertEqual(SurgeryUsedItem.objects.count(), count_before)

    def test_post_quantity_zero_returns_400(self):
        res = self._post(quantity='0')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_quantity_negative_returns_400(self):
        res = self._post(quantity='-5')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_description_returns_200_no_new_movement(self):
        self._post(quantity='10')
        item = SurgeryUsedItem.objects.latest('created_at')
        mv_count_before = StockMovement.objects.filter(movement_type=MovementType.OUT).count()

        res = self.client.patch(
            f'{USED_ITEMS_URL}{item.pk}/',
            {'description': 'توضیح جدید'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            StockMovement.objects.filter(movement_type=MovementType.OUT).count(),
            mv_count_before,
        )

    def test_patch_product_changes_it_and_reconciles_stock(self):
        """Changing product on PATCH restores the old product's stock and
        deducts the new product's stock (CLI-71 — was silently ignored)."""
        self._post(quantity='10')
        item = SurgeryUsedItem.objects.latest('created_at')
        original_product = self.product

        other = _product(internal_code='OTHER-001', name='محصول دیگر')
        other._apply_stock_delta(Decimal('50'))

        res = self.client.patch(
            f'{USED_ITEMS_URL}{item.pk}/',
            {'product': other.pk},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.product_id, other.pk)

        original_product.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(original_product.current_stock, Decimal('100'))  # fully restored
        self.assertEqual(other.current_stock, Decimal('40'))              # 50 - 10

    def test_patch_quantity_changes_it_and_deducts_only_the_difference(self):
        """Changing quantity on PATCH adjusts stock by the difference only
        (CLI-71 — was silently ignored)."""
        self._post(quantity='10')
        item = SurgeryUsedItem.objects.latest('created_at')

        res = self.client.patch(
            f'{USED_ITEMS_URL}{item.pk}/',
            {'quantity': '16'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal('16'))

        self.product.refresh_from_db()
        # 100 - 10 (initial) - 6 (the additional difference only)
        self.assertEqual(self.product.current_stock, Decimal('84'))

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self._post()
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
