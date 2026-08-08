"""Regression tests for the "اقلام مصرفی" used-items workflow (CLI-71):
create/edit/delete a SurgeryUsedItem through the real admin API, each
correctly adjusting Product stock via a compensating StockMovement rather
than mutating the original one.

Covers the acceptance scenarios from the task:
  - consuming 3 units from stock 20 results in stock 17
  - consuming more than available stock fails without any partial record
  - editing 3 to 5 deducts only 2 more
  - editing 5 to 2 restores 3
  - changing Product restores the original Product and deducts the new one
  - deleting/reversing restores inventory
  - unrelated Surgery field edit leaves stock unchanged
  - one item produces one canonical (reconciled) movement effect
  - a repeated/retried update request does not double-deduct
  - a Product with zero stock cannot be consumed
  - an inactive Product already used on a surgery remains visible/editable
  - the standalone SurgeryUsedItemAdmin cannot mutate anything (forces the
    API/service path)
"""
import datetime
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import MovementType, Product, ProductType, SourceType, StockMovement
from surgeries.admin import SurgeryUsedItemAdmin
from surgeries.models import Patient, SurgeryHistory, SurgeryStatus, SurgeryType, SurgeryUsedItem

User = get_user_model()

USED_ITEMS_URL = '/api/v1/surgeries/used-items/'
HISTORY_URL    = '/api/v1/surgeries/history/'

_ctr = [0]


def _product(stock=Decimal('20'), is_active=True, **kwargs):
    _ctr[0] += 1
    defaults = {
        'name':          f'کالای مصرفی {_ctr[0]}',
        'internal_code': f'SUI-{_ctr[0]:05d}',
        'product_type':  ProductType.MEDICINE,
        'unit':          'عدد',
        'is_active':     is_active,
    }
    defaults.update(kwargs)
    p = Product.objects.create(**defaults)
    if stock:
        p._apply_stock_delta(Decimal(str(stock)))
        p.refresh_from_db()
    return p


def _surgery_type():
    _ctr[0] += 1
    return SurgeryType.objects.create(
        name=f'نوع عمل مصرفی {_ctr[0]}', code=f'sui_{_ctr[0]}', base_rate=Decimal('1000000'),
    )


def _patient():
    _ctr[0] += 1
    return Patient.objects.create(
        full_name=f'بیمار مصرفی {_ctr[0]}', case_code=f'SUI-CASE-{_ctr[0]:05d}', phone_number='09120000000',
    )


def _surgery(**kwargs):
    defaults = dict(
        patient=_patient(),
        surgery_type=_surgery_type(),
        amount=Decimal('3000000'),
        surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    )
    defaults.update(kwargs)
    return SurgeryHistory.objects.create(**defaults)


class SurgeryUsedItemApiTestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('sui_edit_admin', 'a@b.com', 'pass')
        self.client.force_authenticate(self.user)
        self.surgery = _surgery()

    def _create(self, product, quantity):
        return self.client.post(USED_ITEMS_URL, {
            'surgery': self.surgery.pk, 'product': product.pk, 'quantity': str(quantity),
        }, format='json')


class ConsumeReducesStockCorrectlyTest(SurgeryUsedItemApiTestBase):

    def test_consuming_3_from_20_results_in_17(self):
        product = _product(stock=Decimal('20'))
        resp = self._create(product, '3')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('17'))

        movement = StockMovement.objects.get(product=product, movement_type=MovementType.OUT)
        self.assertEqual(movement.quantity, Decimal('3'))
        self.assertEqual(movement.source_type, SourceType.SURGERY_CONSUMPTION)

    def test_consuming_more_than_available_fails_with_no_partial_record(self):
        product = _product(stock=Decimal('5'))
        resp = self._create(product, '8')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('5'))
        self.assertEqual(SurgeryUsedItem.objects.filter(product=product).count(), 0)
        self.assertEqual(StockMovement.objects.filter(product=product).count(), 0)

    def test_zero_stock_product_cannot_be_consumed(self):
        product = _product(stock=Decimal('0'))
        resp = self._create(product, '1')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('0'))

    def test_one_item_produces_exactly_one_movement(self):
        product = _product(stock=Decimal('20'))
        self._create(product, '3')
        self.assertEqual(
            StockMovement.objects.filter(product=product, movement_type=MovementType.OUT).count(), 1,
        )


class EditQuantityAdjustsByDifferenceTest(SurgeryUsedItemApiTestBase):

    def test_editing_3_to_5_deducts_only_2_more(self):
        product = _product(stock=Decimal('20'))
        create_resp = self._create(product, '3')
        item_id = create_resp.data['id']
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('17'))

        resp = self.client.patch(f'{USED_ITEMS_URL}{item_id}/', {'quantity': '5'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('15'))  # 20 - 5, not 20 - 3 - 5

    def test_editing_5_to_2_restores_3(self):
        product = _product(stock=Decimal('20'))
        create_resp = self._create(product, '5')
        item_id = create_resp.data['id']
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('15'))

        resp = self.client.patch(f'{USED_ITEMS_URL}{item_id}/', {'quantity': '2'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('18'))  # 20 - 2

    def test_repeated_identical_patch_does_not_double_deduct(self):
        """Retrying the same PATCH (e.g. a network retry) must not deduct
        stock twice — the second call sees the already-updated stored
        quantity and computes a zero diff."""
        product = _product(stock=Decimal('20'))
        create_resp = self._create(product, '3')
        item_id = create_resp.data['id']

        resp1 = self.client.patch(f'{USED_ITEMS_URL}{item_id}/', {'quantity': '5'}, format='json')
        resp2 = self.client.patch(f'{USED_ITEMS_URL}{item_id}/', {'quantity': '5'}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('15'))  # 20 - 5, only once

    def test_unrelated_surgery_field_edit_leaves_stock_unchanged(self):
        product = _product(stock=Decimal('20'))
        self._create(product, '3')
        product.refresh_from_db()
        stock_after_create = product.current_stock

        resp = self.client.patch(f'{HISTORY_URL}{self.surgery.pk}/', {
            'description': 'یادداشت جدید بدون تغییر اقلام مصرفی',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, stock_after_create)


class EditProductRestoresOldAndDeductsNewTest(SurgeryUsedItemApiTestBase):

    def test_changing_product_restores_original_and_deducts_new(self):
        old_product = _product(stock=Decimal('20'))
        new_product = _product(stock=Decimal('30'))

        create_resp = self._create(old_product, '4')
        item_id = create_resp.data['id']
        old_product.refresh_from_db()
        self.assertEqual(old_product.current_stock, Decimal('16'))

        resp = self.client.patch(
            f'{USED_ITEMS_URL}{item_id}/', {'product': new_product.pk}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        old_product.refresh_from_db()
        new_product.refresh_from_db()
        self.assertEqual(old_product.current_stock, Decimal('20'))  # fully restored
        self.assertEqual(new_product.current_stock, Decimal('26'))  # 30 - 4

        # Both the original OUT and the compensating IN/RETURN remain —
        # the audit trail is never edited or deleted.
        self.assertEqual(
            StockMovement.objects.filter(product=old_product, movement_type=MovementType.OUT).count(), 1,
        )
        self.assertEqual(
            StockMovement.objects.filter(product=old_product, movement_type=MovementType.IN, source_type=SourceType.RETURN).count(), 1,
        )
        self.assertEqual(
            StockMovement.objects.filter(product=new_product, movement_type=MovementType.OUT).count(), 1,
        )

    def test_changing_product_to_one_with_insufficient_stock_rejected_and_rolled_back(self):
        old_product = _product(stock=Decimal('20'))
        new_product = _product(stock=Decimal('1'))

        create_resp = self._create(old_product, '4')
        item_id = create_resp.data['id']

        resp = self.client.patch(
            f'{USED_ITEMS_URL}{item_id}/', {'product': new_product.pk, 'quantity': '4'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        old_product.refresh_from_db()
        new_product.refresh_from_db()
        item = SurgeryUsedItem.objects.get(pk=item_id)
        # Nothing changed: old product still deducted, new product untouched,
        # and the row itself still points at the old product.
        self.assertEqual(old_product.current_stock, Decimal('16'))
        self.assertEqual(new_product.current_stock, Decimal('1'))
        self.assertEqual(item.product_id, old_product.pk)


class DeleteReversesConsumptionTest(SurgeryUsedItemApiTestBase):

    def test_delete_restores_inventory(self):
        product = _product(stock=Decimal('20'))
        create_resp = self._create(product, '6')
        item_id = create_resp.data['id']
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('14'))

        resp = self.client.delete(f'{USED_ITEMS_URL}{item_id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('20'))
        self.assertFalse(SurgeryUsedItem.objects.filter(pk=item_id).exists())

        # Audit trail preserved: original OUT + compensating IN both remain.
        self.assertEqual(
            StockMovement.objects.filter(product=product, movement_type=MovementType.OUT).count(), 1,
        )
        self.assertEqual(
            StockMovement.objects.filter(product=product, movement_type=MovementType.IN, source_type=SourceType.RETURN).count(), 1,
        )

    def test_repeated_delete_is_idempotent_404_not_double_reversed(self):
        product = _product(stock=Decimal('20'))
        create_resp = self._create(product, '6')
        item_id = create_resp.data['id']

        resp1 = self.client.delete(f'{USED_ITEMS_URL}{item_id}/')
        resp2 = self.client.delete(f'{USED_ITEMS_URL}{item_id}/')
        self.assertEqual(resp1.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(resp2.status_code, status.HTTP_404_NOT_FOUND)

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('20'))  # restored exactly once


class InactiveProductRemainsVisibleTest(SurgeryUsedItemApiTestBase):

    def test_inactive_historical_product_still_appears_on_existing_item(self):
        product = _product(stock=Decimal('20'))
        create_resp = self._create(product, '3')
        item_id = create_resp.data['id']

        product.refresh_from_db()
        product.is_active = False
        product.save(update_fields=['is_active'])

        list_resp = self.client.get(USED_ITEMS_URL, {'surgery': self.surgery.pk})
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        results = list_resp.data['results'] if 'results' in list_resp.data else list_resp.data
        matching = [r for r in results if r['id'] == item_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['product'], product.pk)
        self.assertEqual(matching[0]['product_name'], product.name)

        detail_resp = self.client.get(f'{USED_ITEMS_URL}{item_id}/')
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_resp.data['product'], product.pk)


class SurgeryUsedItemAdminIsViewOnlyTest(TestCase):
    """The standalone admin page must never be a second, independent path
    that can mutate stock — every write must go through the API/service."""

    def setUp(self):
        self.admin = SurgeryUsedItemAdmin(SurgeryUsedItem, AdminSite())

    def test_add_permission_denied(self):
        self.assertFalse(self.admin.has_add_permission(request=None))

    def test_change_permission_denied(self):
        self.assertFalse(self.admin.has_change_permission(request=None))

    def test_delete_permission_denied(self):
        self.assertFalse(self.admin.has_delete_permission(request=None))
