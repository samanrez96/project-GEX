"""Targeted regression tests for the Product hard-delete (purge) workflow.

Covers:
  - basic purge: Product + StockMovement + SurgeryUsedItem +
    SurgeryConsumptionItem + ProductVendor rows removed; unrelated
    Surgery/Product records untouched.
  - multi-item Purchase: surviving item/Purchase total/Finance expense
    recalculated; the deleted product's line disappears.
  - single-item Purchase: emptied Purchase is cancelled and its Finance
    expense cancelled through the existing convention, not deleted.
  - Surgery cost/profit: consumed-item cost recalculates automatically
    (live query) once the row is gone; center commission (independent of
    consumed-item cost) is untouched.
  - permissions: superuser only, at both the admin view and the DRF
    purge action; forged IDs 404; GET cannot execute deletion.
  - rollback: a forced failure mid-purge leaves every row untouched.
  - idempotency: a second purge attempt safely 404s.
  - UI/API regressions: Product/Purchase/Surgery pages and the Product
    Excel export keep working after a purge.
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import Transaction, TransactionPaymentStatus, TransactionType
from inventory.models import (
    MovementType,
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    SourceType,
    StockMovement,
    Vendor,
)
from inventory.services import ProductPurgeService, StockService
from surgeries.models import (
    Patient,
    Surgery,
    SurgeryConsumptionItem,
    SurgeryHistory,
    SurgeryType,
    SurgeryUsedItem,
)

User = get_user_model()

_ctr = [0]


def _product(stock=Decimal('0'), **kwargs):
    _ctr[0] += 1
    defaults = {
        'name': f'محصول حذفی {_ctr[0]}',
        'internal_code': f'PURGE-{_ctr[0]:05d}',
        'product_type': ProductType.MEDICINE,
        'unit': 'عدد',
    }
    defaults.update(kwargs)
    p = Product.objects.create(**defaults)
    if stock:
        StockService.create_movement(
            product=p, quantity=Decimal(str(stock)),
            movement_type=MovementType.IN, source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id='initial-stock-test', description='موجودی اولیه تست',
        )
        p.refresh_from_db()
    return p


def _vendor(**kwargs):
    _ctr[0] += 1
    defaults = {'name': f'فروشنده حذفی {_ctr[0]}'}
    defaults.update(kwargs)
    return Vendor.objects.create(**defaults)


def _surgery_type():
    _ctr[0] += 1
    return SurgeryType.objects.create(
        name=f'نوع عمل حذفی {_ctr[0]}', code=f'purge_{_ctr[0]}', base_rate=Decimal('1000000'),
    )


def _patient():
    _ctr[0] += 1
    return Patient.objects.create(
        full_name=f'بیمار حذفی {_ctr[0]}', case_code=f'PURGE-CASE-{_ctr[0]:05d}',
        phone_number='09120000000',
    )


def _surgery_history(**kwargs):
    defaults = dict(
        patient=_patient(), surgery_type=_surgery_type(), amount=Decimal('3000000'),
        surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    )
    defaults.update(kwargs)
    return SurgeryHistory.objects.create(**defaults)


def _purchase(vendor=None, **kwargs):
    if vendor is None:
        vendor = _vendor()
    defaults = {'vendor': vendor, 'purchase_date': timezone.now()}
    defaults.update(kwargs)
    return Purchase.objects.create(**defaults)


def _item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('1000')):
    return PurchaseItem.objects.create(
        purchase=purchase, product=product, quantity=quantity, unit_price=unit_price,
    )


def _expense_transactions(purchase):
    ct = ContentType.objects.get_for_model(purchase)
    return Transaction.objects.filter(
        content_type=ct, object_id=purchase.pk, transaction_type=TransactionType.EXPENSE,
    )


def _superuser(name='purge_superuser'):
    return User.objects.create_superuser(name, f'{name}@example.com', 'pass12345')


def _staff_admin(name='purge_staff_admin'):
    """Staff user in the broad 'admin' business group — NOT is_superuser.
    Must be rejected by every purge path (is_main_administrator only)."""
    user = User.objects.create_user(name, f'{name}@example.com', 'pass12345', is_staff=True)
    group, _ = Group.objects.get_or_create(name='admin')
    user.groups.add(group)
    return user


# ---------------------------------------------------------------------------
# Basic purge: dependent rows removed, unrelated rows untouched
# ---------------------------------------------------------------------------

class ProductPurgeBasicTest(TestCase):
    def test_purge_deletes_product_and_all_dependents(self):
        product = _product(stock=Decimal('10'))
        vendor = _vendor()
        ProductVendor.objects.create(product=product, vendor=vendor, unit_price=Decimal('500'))

        surgery = _surgery_history()
        SurgeryUsedItem.objects.create(surgery=surgery, product=product, quantity=Decimal('2'))

        legacy_surgery = Surgery.objects.create(patient_name='بیمار قدیمی', surgery_date=timezone.now())
        SurgeryConsumptionItem.objects.create(
            surgery=legacy_surgery, product=product, quantity=Decimal('1'),
        )

        movement_count_before = StockMovement.objects.filter(product=product).count()
        self.assertGreater(movement_count_before, 0)

        superuser = _superuser()
        summary = ProductPurgeService.purge(product, superuser)

        self.assertFalse(Product.objects.filter(pk=summary['id']).exists())
        self.assertEqual(StockMovement.objects.filter(product_id=summary['id']).count(), 0)
        self.assertEqual(SurgeryUsedItem.objects.filter(product_id=summary['id']).count(), 0)
        self.assertEqual(SurgeryConsumptionItem.objects.filter(product_id=summary['id']).count(), 0)
        self.assertEqual(ProductVendor.objects.filter(product_id=summary['id']).count(), 0)

        self.assertEqual(summary['surgery_used_items_deleted'], 1)
        self.assertEqual(summary['surgery_consumption_items_deleted'], 1)
        self.assertEqual(summary['stock_movements_deleted'], movement_count_before)
        self.assertEqual(summary['product_vendors_deleted'], 1)

        # Parent Surgery/SurgeryHistory rows survive.
        self.assertTrue(SurgeryHistory.objects.filter(pk=surgery.pk).exists())
        self.assertTrue(Surgery.objects.filter(pk=legacy_surgery.pk).exists())

    def test_purge_preserves_unrelated_records(self):
        target = _product(stock=Decimal('5'))
        other = _product(stock=Decimal('5'))
        surgery = _surgery_history()
        SurgeryUsedItem.objects.create(surgery=surgery, product=target, quantity=Decimal('1'))
        other_item = SurgeryUsedItem.objects.create(surgery=surgery, product=other, quantity=Decimal('1'))

        ProductPurgeService.purge(target, _superuser())

        self.assertTrue(Product.objects.filter(pk=other.pk).exists())
        self.assertTrue(SurgeryUsedItem.objects.filter(pk=other_item.pk).exists())
        self.assertEqual(StockMovement.objects.filter(product=other).count(), 1)


# ---------------------------------------------------------------------------
# Multi-item Purchase: survives, recalculated
# ---------------------------------------------------------------------------

class ProductPurgeMultiItemPurchaseTest(TestCase):
    def test_multi_item_purchase_recalculated_after_purge(self):
        product_a = _product(product_type=ProductType.MEDICINE)
        product_b = _product(product_type=ProductType.MEDICINE)
        purchase = _purchase()
        _item(purchase, product_a, quantity=Decimal('1'), unit_price=Decimal('300'))
        _item(purchase, product_b, quantity=Decimal('1'), unit_price=Decimal('700'))
        purchase.confirm()
        purchase.refresh_from_db()

        expenses = _expense_transactions(purchase)
        self.assertEqual(expenses.count(), 1)
        self.assertEqual(expenses.first().amount, Decimal('1000'))

        ProductPurgeService.purge(product_a, _superuser())

        purchase.refresh_from_db()
        self.assertTrue(Purchase.objects.filter(pk=purchase.pk).exists())
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)
        remaining_items = list(purchase.items.all())
        self.assertEqual(len(remaining_items), 1)
        self.assertEqual(remaining_items[0].product_id, product_b.pk)
        new_total = sum((i.effective_total for i in remaining_items), Decimal('0'))
        self.assertEqual(new_total, Decimal('700'))

        expenses = _expense_transactions(purchase)
        active_expenses = expenses.exclude(payment_status=TransactionPaymentStatus.CANCELLED)
        self.assertEqual(active_expenses.count(), 1)
        self.assertEqual(active_expenses.first().amount, Decimal('700'))
        # No duplicate expense created.
        self.assertEqual(expenses.count(), 1)

    def test_vanished_category_expense_is_cancelled_when_other_category_survives(self):
        medicine = _product(product_type=ProductType.MEDICINE)
        equipment = _product(product_type=ProductType.EQUIPMENT)
        purchase = _purchase()
        _item(purchase, medicine, quantity=Decimal('1'), unit_price=Decimal('400'))
        _item(purchase, equipment, quantity=Decimal('1'), unit_price=Decimal('600'))
        purchase.confirm()
        purchase.refresh_from_db()

        self.assertEqual(_expense_transactions(purchase).count(), 2)

        ProductPurgeService.purge(medicine, _superuser())

        expenses = _expense_transactions(purchase)
        self.assertEqual(expenses.count(), 2)
        medicine_expense = expenses.get(category__name='هزینه دارو')
        equipment_expense = expenses.get(category__name='هزینه تجهیزات')
        self.assertEqual(medicine_expense.payment_status, TransactionPaymentStatus.CANCELLED)
        self.assertNotEqual(equipment_expense.payment_status, TransactionPaymentStatus.CANCELLED)
        self.assertEqual(equipment_expense.amount, Decimal('600'))


# ---------------------------------------------------------------------------
# Single-item Purchase: emptied -> cancelled, not left dangling
# ---------------------------------------------------------------------------

class ProductPurgeSingleItemPurchaseTest(TestCase):
    def test_single_item_confirmed_purchase_is_cancelled_after_purge(self):
        product = _product()
        purchase = _purchase()
        _item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('500'))
        purchase.confirm()
        purchase.refresh_from_db()
        self.assertTrue(purchase.stock_applied)

        movements_before = StockMovement.objects.filter(
            source_type=SourceType.PURCHASE, reference_id=f'purchase-{purchase.pk}',
        ).count()
        self.assertEqual(movements_before, 1)

        summary = ProductPurgeService.purge(product, _superuser())

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CANCELLED)
        self.assertEqual(purchase.items.count(), 0)
        self.assertIn(purchase.pk, summary['purchases_cancelled'])

        expenses = _expense_transactions(purchase)
        self.assertTrue(expenses.exists())
        self.assertTrue(all(e.payment_status == TransactionPaymentStatus.CANCELLED for e in expenses))

        # No stale IN movement referencing the deleted product's purchase left behind.
        self.assertEqual(StockMovement.objects.filter(product_id=product.pk).count(), 0)

    def test_single_item_pending_purchase_is_cancelled_after_purge(self):
        product = _product()
        purchase = _purchase()
        _item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('500'))
        self.assertEqual(purchase.status, PurchaseStatus.PENDING)

        summary = ProductPurgeService.purge(product, _superuser())

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CANCELLED)
        self.assertIn(purchase.pk, summary['purchases_cancelled'])


# ---------------------------------------------------------------------------
# Surgery cost/profit recalculation
# ---------------------------------------------------------------------------

class ProductPurgeSurgeryCostTest(APITestCase):
    PROFIT_URL = '/api/v2/surgeries/reports/profit/'

    def test_consumed_item_cost_and_center_income_after_purge(self):
        from finance.models import CenterCommissionIncome
        from surgeries.services import SurgeryFinanceService

        kept = _product(stock=Decimal('50'))
        removed = _product(stock=Decimal('50'))
        surgery = _surgery_history(
            amount=Decimal('1000000'), center_commission_percent=Decimal('10'),
        )
        SurgeryFinanceService.sync_center_commission_income(surgery)
        income_before = CenterCommissionIncome.objects.get(surgery=surgery).amount
        self.assertEqual(income_before, Decimal('100000'))  # independent of consumed items

        SurgeryUsedItem.objects.create(surgery=surgery, product=kept, quantity=Decimal('2'))
        SurgeryUsedItem.objects.create(surgery=surgery, product=removed, quantity=Decimal('3'))

        superuser = _superuser()
        self.client.force_authenticate(superuser)
        resp = self.client.get(self.PROFIT_URL, {'patient_id': surgery.patient_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        ProductPurgeService.purge(removed, superuser)

        # Removed item disappears; kept item remains.
        self.assertEqual(SurgeryUsedItem.objects.filter(surgery=surgery).count(), 1)
        self.assertTrue(SurgeryUsedItem.objects.filter(surgery=surgery, product=kept).exists())

        # Center income is untouched — it never derived from consumed items.
        income_after = CenterCommissionIncome.objects.get(surgery=surgery).amount
        self.assertEqual(income_after, income_before)

        # Profit report still loads and no longer errors on the missing product.
        resp = self.client.get(self.PROFIT_URL, {'patient_id': surgery.patient_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class ProductPurgeApiPermissionTest(APITestCase):
    def setUp(self):
        self.product = _product()

    def _preview_url(self, pk):
        return f'/api/v2/inventory/products/{pk}/purge-preview/'

    def _purge_url(self, pk):
        return f'/api/v2/inventory/products/{pk}/purge/'

    def test_superuser_can_preview_and_purge(self):
        self.client.force_authenticate(_superuser())
        resp = self.client.get(self._preview_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['product']['internal_code'], self.product.internal_code)

        resp = self.client.post(
            self._purge_url(self.product.pk),
            {'confirmation_code': self.product.internal_code},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_staff_admin_group_cannot_purge(self):
        self.client.force_authenticate(_staff_admin())
        resp = self.client.get(self._preview_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(
            self._purge_url(self.product.pk),
            {'confirmation_code': self.product.internal_code},
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_wrong_confirmation_code_rejected(self):
        self.client.force_authenticate(_superuser())
        resp = self.client.post(self._purge_url(self.product.pk), {'confirmation_code': 'WRONG'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_forged_product_id_returns_404(self):
        self.client.force_authenticate(_superuser())
        resp = self.client.get(self._preview_url(999999))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.post(self._purge_url(999999), {'confirmation_code': 'X'})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_ordinary_destroy_is_always_blocked(self):
        self.client.force_authenticate(_superuser())
        resp = self.client.delete(f'/api/v2/inventory/products/{self.product.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_get_not_allowed_on_purge_action(self):
        self.client.force_authenticate(_superuser())
        resp = self.client.get(self._purge_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())


class ProductPurgeAdminViewTest(TestCase):
    def setUp(self):
        self.product = _product()

    def _purge_url(self, pk):
        return reverse('admin:inventory_product_purge', args=[pk])

    def _delete_url(self, pk):
        return reverse('admin:inventory_product_delete', args=[pk])

    def test_superuser_sees_preview_and_can_confirm(self):
        superuser = _superuser()
        self.client.force_login(superuser)

        resp = self.client.get(self._purge_url(self.product.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.product.internal_code)
        self.assertContains(resp, 'این عملیات دائمی است و تمام سوابق وابسته مشخص‌شده را حذف یا به‌روزرسانی می‌کند.')

        resp = self.client.post(
            self._purge_url(self.product.pk),
            {'confirmation_code': self.product.internal_code},
        )
        self.assertRedirects(resp, reverse('admin:inventory_product_changelist'))
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_default_delete_url_redirects_to_purge_flow(self):
        superuser = _superuser()
        self.client.force_login(superuser)
        resp = self.client.get(self._delete_url(self.product.pk))
        self.assertRedirects(resp, self._purge_url(self.product.pk))

    def test_staff_admin_cannot_reach_purge_view(self):
        staff = _staff_admin()
        self.client.force_login(staff)
        resp = self.client.get(self._purge_url(self.product.pk))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_wrong_confirmation_code_does_not_delete(self):
        superuser = _superuser()
        self.client.force_login(superuser)
        resp = self.client.post(self._purge_url(self.product.pk), {'confirmation_code': 'nope'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

class ProductPurgeRollbackTest(TestCase):
    def test_failure_during_purchase_cancellation_rolls_back_everything(self):
        product = _product(stock=Decimal('5'))
        purchase = _purchase()
        item = _item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('500'))
        purchase.confirm()
        purchase.refresh_from_db()

        surgery = _surgery_history()
        used_item = SurgeryUsedItem.objects.create(surgery=surgery, product=product, quantity=Decimal('1'))

        movement_count_before = StockMovement.objects.filter(product=product).count()
        item_count_before = PurchaseItem.objects.filter(purchase=purchase).count()

        with patch.object(Purchase, 'cancel', side_effect=DjangoValidationError('forced failure')):
            with self.assertRaises(DjangoValidationError):
                ProductPurgeService.purge(product, _superuser())

        # Nothing committed: transaction.atomic rolled the whole call back.
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(SurgeryUsedItem.objects.filter(pk=used_item.pk).exists())
        self.assertEqual(StockMovement.objects.filter(product=product).count(), movement_count_before)
        self.assertEqual(PurchaseItem.objects.filter(purchase=purchase).count(), item_count_before)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class ProductPurgeIdempotencyTest(APITestCase):
    def test_second_purge_attempt_is_a_safe_404(self):
        product = _product()
        superuser = _superuser()
        self.client.force_authenticate(superuser)

        url = f'/api/v2/inventory/products/{product.pk}/purge/'
        resp = self.client.post(url, {'confirmation_code': product.internal_code})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(url, {'confirmation_code': product.internal_code})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# UI / API / report regressions after a purge
# ---------------------------------------------------------------------------

class ProductPurgePanelStabilityTest(APITestCase):
    def setUp(self):
        self.superuser = _superuser()
        self.client.force_authenticate(self.superuser)

        self.product = _product(stock=Decimal('10'))
        self.other_product = _product(stock=Decimal('10'))
        self.vendor = _vendor()
        ProductVendor.objects.create(product=self.product, vendor=self.vendor, unit_price=Decimal('100'))

        self.purchase = _purchase(vendor=self.vendor)
        _item(self.purchase, self.product, quantity=Decimal('1'), unit_price=Decimal('300'))
        _item(self.purchase, self.other_product, quantity=Decimal('1'), unit_price=Decimal('700'))
        self.purchase.confirm()

        self.surgery = _surgery_history()
        SurgeryUsedItem.objects.create(surgery=self.surgery, product=self.product, quantity=Decimal('1'))

        ProductPurgeService.purge(self.product, self.superuser)

    def test_product_list_loads_without_deleted_product(self):
        resp = self.client.get('/api/v2/inventory/products/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [row['id'] for row in resp.data['results']]
        self.assertNotIn(self.product.pk, ids)
        self.assertIn(self.other_product.pk, ids)

    def test_product_detail_404s_cleanly(self):
        resp = self.client.get(f'/api/v2/inventory/products/{self.product.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_purchase_detail_loads_with_remaining_item_only(self):
        resp = self.client.get(f'/api/v2/inventory/purchases/{self.purchase.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        product_ids = [i['product'] for i in resp.data['items']]
        self.assertNotIn(self.product.pk, product_ids)
        self.assertIn(self.other_product.pk, product_ids)

    def test_surgery_history_detail_loads(self):
        resp = self.client.get(f'/api/v2/surgeries/history/{self.surgery.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_stock_movement_list_loads(self):
        resp = self.client.get('/api/v2/inventory/stock-movements/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_product_excel_export_still_works(self):
        resp = self.client.get('/api/v2/inventory/products/', {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_purchase_excel_export_still_works(self):
        resp = self.client.get('/api/v2/inventory/purchases/', {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
