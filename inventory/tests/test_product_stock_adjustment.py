"""Targeted tests for the موجودی فعلی (current-stock) admin adjustment feature.

Canonical architecture (see inventory/models.py Product.current_stock and
its _apply_stock_delta docstring): current_stock is a cached, editable=False
DecimalField, synchronized *exclusively* through StockMovement rows created
via StockService. This feature adds no second stock-calculation system —
StockService.adjust_to_quantity() is a new entry point that computes a
delta against the authoritative (locked, re-read) stock and delegates to
the existing StockService.create_movement(), exactly like Purchase/Surgery
consumption already do.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import MovementType, Product, ProductType, SourceType, StockMovement
from inventory.services import StockService

User = get_user_model()

_ctr = [0]


def _product(stock=Decimal('0'), **kwargs):
    _ctr[0] += 1
    defaults = {
        'name': f'محصول اصلاح موجودی {_ctr[0]}',
        'internal_code': f'ADJ-{_ctr[0]:05d}',
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


def _superuser(name='adj_superuser'):
    _ctr[0] += 1
    return User.objects.create_superuser(f'{name}_{_ctr[0]}', f'{name}{_ctr[0]}@example.com', 'pass12345')


def _staff_admin(name='adj_staff_admin'):
    """Staff user with ordinary Product view/change permission — NOT
    is_superuser. Must be rejected by the stock-adjustment gate
    (is_main_administrator only) while every other Product field stays
    editable."""
    from django.contrib.auth.models import Permission

    _ctr[0] += 1
    user = User.objects.create_user(f'{name}_{_ctr[0]}', f'{name}{_ctr[0]}@example.com', 'pass12345', is_staff=True)
    group, _ = Group.objects.get_or_create(name='admin')
    user.groups.add(group)
    for codename in ('view_product', 'change_product'):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _change_url(pk):
    return f'/admin/inventory/product/{pk}/change/'


def _edit_payload(product, **overrides):
    data = {
        'name': product.name,
        'internal_code': product.internal_code,
        'product_type': product.product_type,
        'unit': product.unit,
        'purchase_price': str(product.purchase_price),
        'minimum_stock': str(product.minimum_stock),
        'internal_notes': '',
        'product_vendors-TOTAL_FORMS': '0',
        'product_vendors-INITIAL_FORMS': '0',
        'product_vendors-MIN_NUM_FORMS': '0',
        'product_vendors-MAX_NUM_FORMS': '1000',
        'stock_movements-TOTAL_FORMS': '0',
        'stock_movements-INITIAL_FORMS': '0',
        'stock_movements-MIN_NUM_FORMS': '0',
        'stock_movements-MAX_NUM_FORMS': '1000',
        '_save': '1',
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# StockService.adjust_to_quantity — the canonical service, tested directly
# ---------------------------------------------------------------------------

class StockServiceAdjustToQuantityTest(TestCase):
    def test_increase_creates_one_in_movement(self):
        product = _product(stock=Decimal('100'))
        movement = StockService.adjust_to_quantity(
            product=product, desired_quantity=Decimal('130'), reason='اصلاح شمارش انبار',
        )
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('130'))
        self.assertEqual(movement.movement_type, MovementType.IN)
        self.assertEqual(movement.quantity, Decimal('30'))
        self.assertEqual(movement.source_type, SourceType.MANUAL_ADJUSTMENT)
        self.assertEqual(
            StockMovement.objects.filter(product=product, source_type=SourceType.MANUAL_ADJUSTMENT).count(),
            2,  # initial-stock movement from _product() + this one
        )

    def test_decrease_creates_one_out_movement(self):
        product = _product(stock=Decimal('100'))
        movement = StockService.adjust_to_quantity(
            product=product, desired_quantity=Decimal('85'), reason='کسری انبار',
        )
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('85'))
        self.assertEqual(movement.movement_type, MovementType.OUT)
        self.assertEqual(movement.quantity, Decimal('15'))

    def test_no_change_creates_no_movement(self):
        product = _product(stock=Decimal('100'))
        before = StockMovement.objects.filter(product=product).count()
        result = StockService.adjust_to_quantity(
            product=product, desired_quantity=Decimal('100'), reason='',
        )
        self.assertIsNone(result)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('100'))
        self.assertEqual(StockMovement.objects.filter(product=product).count(), before)

    def test_adjust_to_zero_creates_out_movement_for_full_amount(self):
        product = _product(stock=Decimal('20'))
        movement = StockService.adjust_to_quantity(
            product=product, desired_quantity=Decimal('0'), reason='مازاد کشف‌شده صفر شد',
        )
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('0'))
        self.assertEqual(movement.movement_type, MovementType.OUT)
        self.assertEqual(movement.quantity, Decimal('20'))

    def test_negative_desired_quantity_rejected(self):
        product = _product(stock=Decimal('10'))
        with self.assertRaises(ValidationError):
            StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('-1'), reason='x')
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('10'))

    def test_decimal_quantity_supported(self):
        product = _product(stock=Decimal('10.500'))
        movement = StockService.adjust_to_quantity(
            product=product, desired_quantity=Decimal('12.750'), reason='اصلاح اعشاری',
        )
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('12.750'))
        self.assertEqual(movement.quantity, Decimal('2.250'))

    def test_reason_and_user_are_folded_into_description(self):
        product = _product(stock=Decimal('5'))
        user = _superuser()
        movement = StockService.adjust_to_quantity(
            product=product, desired_quantity=Decimal('8'), reason='اصلاح شمارش انبار', user=user,
        )
        self.assertIn('اصلاح شمارش انبار', movement.description)
        self.assertIn(user.get_username(), movement.description)

    def test_blank_reason_with_user_uses_default_label_plus_username(self):
        """Without reason: اصلاح دستی موجودی — توسط <username>."""
        product = _product(stock=Decimal('5'))
        user = _superuser()
        movement = StockService.adjust_to_quantity(
            product=product, desired_quantity=Decimal('8'), reason='', user=user,
        )
        self.assertEqual(movement.description, f'اصلاح دستی موجودی — توسط {user.get_username()}')

    def test_blank_reason_without_user_uses_default_label_only(self):
        product = _product(stock=Decimal('5'))
        movement = StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('8'), reason='')
        self.assertEqual(movement.description, 'اصلاح دستی موجودی')

    def test_accepts_product_pk_as_well_as_instance(self):
        product = _product(stock=Decimal('4'))
        movement = StockService.adjust_to_quantity(product=product.pk, desired_quantity=Decimal('6'), reason='x')
        self.assertEqual(movement.product_id, product.pk)

    def test_does_not_create_finance_transaction(self):
        """Manual stock correction is not a Purchase/income/expense event."""
        from finance.models import Transaction
        product = _product(stock=Decimal('100'))
        before = Transaction.objects.count()
        StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('50'), reason='x')
        self.assertEqual(Transaction.objects.count(), before)


# ---------------------------------------------------------------------------
# Rollback / atomicity
# ---------------------------------------------------------------------------

class StockServiceAdjustRollbackTest(TestCase):
    def test_failure_inside_adjust_rolls_back_everything(self):
        product = _product(stock=Decimal('100'))
        before_movements = StockMovement.objects.filter(product=product).count()

        with patch(
            'inventory.services.StockService.create_movement',
            side_effect=RuntimeError('forced failure'),
        ):
            with self.assertRaises(RuntimeError):
                StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('130'), reason='x')

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('100'))
        self.assertEqual(StockMovement.objects.filter(product=product).count(), before_movements)

    def test_admin_save_rolls_back_product_metadata_when_adjustment_fails(self):
        """Product name change + stock adjustment must be all-or-nothing."""
        product = _product(stock=Decimal('100'), name='نام اصلی')
        superuser = _superuser()
        self.client = self.client_class()
        self.client.force_login(superuser)

        with patch(
            'inventory.services.StockService.adjust_to_quantity',
            side_effect=RuntimeError('forced failure'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(_change_url(product.pk), _edit_payload(
                    product,
                    name='نام تغییریافته',
                    desired_current_stock='130',
                    stock_adjustment_reason='اصلاح شمارش انبار',
                ))

        product.refresh_from_db()
        self.assertEqual(product.name, 'نام اصلی')
        self.assertEqual(product.current_stock, Decimal('100'))


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

class StockServiceAdjustConcurrencyTest(TestCase):
    def test_uses_latest_stock_not_stale_value(self):
        """Simulates a Purchase/Surgery consumption happening after the
        admin page was rendered but before the adjustment is saved —
        adjust_to_quantity must reconcile against the *current* DB value,
        not whatever was true when the caller first looked at it."""
        product = _product(stock=Decimal('100'))

        # The admin form was opened when stock was 100 (desired=130 means
        # "+30"). Before the user clicks Save, a concurrent event drops
        # stock to 70 (e.g. a Surgery consumed 30 units).
        StockService.create_movement(
            product=product, quantity=Decimal('30'),
            movement_type=MovementType.OUT, source_type=SourceType.SURGERY_CONSUMPTION,
            reference_id='surgery-history-999',
        )
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('70'))

        # adjust_to_quantity still reconciles to the caller's real target
        # (130) — the delta it records (+60) reflects the *true* current
        # stock (70), not the stale 100 the form was opened with.
        movement = StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('130'), reason='x')
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('130'))
        self.assertEqual(movement.quantity, Decimal('60'))


# ---------------------------------------------------------------------------
# ProductAdmin form — end-to-end via the change page
# ---------------------------------------------------------------------------

class ProductAdminStockAdjustmentFormTest(TestCase):
    def setUp(self):
        self.superuser = _superuser()
        self.client.force_login(self.superuser)

    def test_edit_page_prefills_real_current_stock(self):
        product = _product(stock=Decimal('222'))
        resp = self.client.get(_change_url(product.pk))
        self.assertContains(resp, 'id_desired_current_stock')
        self.assertContains(resp, 'value="222')

    def test_increase_via_form_creates_in_movement_and_updates_stock(self):
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='130', stock_adjustment_reason='اصلاح شمارش انبار',
        ))
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('130'))
        movement = StockMovement.objects.filter(
            product=product, source_type=SourceType.MANUAL_ADJUSTMENT, movement_type=MovementType.IN,
        ).exclude(reference_id='initial-stock-test').first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity, Decimal('30'))
        self.assertIn('اصلاح شمارش انبار', movement.description)

    def test_decrease_via_form_creates_out_movement(self):
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='85', stock_adjustment_reason='کسری انبار',
        ))
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('85'))
        movement = StockMovement.objects.filter(
            product=product, source_type=SourceType.MANUAL_ADJUSTMENT, movement_type=MovementType.OUT,
        ).first()
        self.assertEqual(movement.quantity, Decimal('15'))

    def test_unchanged_stock_creates_no_movement(self):
        product = _product(stock=Decimal('100'))
        before = StockMovement.objects.filter(product=product).count()
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='100', stock_adjustment_reason='',
        ))
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('100'))
        self.assertEqual(StockMovement.objects.filter(product=product).count(), before)

    def test_increase_without_reason_succeeds_with_default_description(self):
        """دلیل اصلاح موجودی is optional — a blank reason must not block
        the adjustment, and the movement gets a sensible default label."""
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='130', stock_adjustment_reason='',
        ))
        self.assertEqual(resp.status_code, 302)  # redirected on success, no validation error
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('130'))
        movement = StockMovement.objects.filter(
            product=product, source_type=SourceType.MANUAL_ADJUSTMENT, movement_type=MovementType.IN,
        ).exclude(reference_id='initial-stock-test').first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity, Decimal('30'))
        self.assertIn('اصلاح دستی موجودی', movement.description)

    def test_decrease_without_reason_succeeds_with_default_description(self):
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='85', stock_adjustment_reason='',
        ))
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('85'))
        movement = StockMovement.objects.filter(
            product=product, source_type=SourceType.MANUAL_ADJUSTMENT, movement_type=MovementType.OUT,
        ).first()
        self.assertIsNotNone(movement)
        self.assertIn('اصلاح دستی موجودی', movement.description)

    def test_reason_field_is_not_rendered_as_required(self):
        product = _product(stock=Decimal('100'))
        resp = self.client.get(_change_url(product.pk))
        content = resp.content.decode()
        reason_pos = content.index('id_stock_adjustment_reason')
        row_start = content.rfind('<div class="form-row', 0, reason_pos)
        row_end = content.index('</div>\n    \n        <div class="form-row', row_start)
        row_html = content[row_start:row_end]
        self.assertNotIn('class="required"', row_html)

    def test_negative_stock_rejected(self):
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='-5', stock_adjustment_reason='x',
        ))
        self.assertEqual(resp.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('100'))

    def test_invalid_text_stock_rejected(self):
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='abc', stock_adjustment_reason='x',
        ))
        self.assertEqual(resp.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('100'))

    def test_other_product_fields_still_editable_alongside_stock_adjustment(self):
        product = _product(stock=Decimal('100'), minimum_stock=Decimal('0'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, name='نام جدید', minimum_stock='7',
            desired_current_stock='100', stock_adjustment_reason='',
        ))
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.name, 'نام جدید')
        self.assertEqual(product.minimum_stock, Decimal('7'))


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class ProductAdminStockAdjustmentPermissionTest(TestCase):
    def test_normal_staff_admin_does_not_see_stock_adjustment_fields(self):
        staff = _staff_admin()
        self.client.force_login(staff)
        product = _product(stock=Decimal('100'))
        resp = self.client.get(_change_url(product.pk))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn('id_desired_current_stock', content)
        self.assertNotIn('id_stock_adjustment_reason', content)
        # Readonly admin fields render as a plain <div class="readonly">
        # inside a "field-<name>" row — they get no id="id_..." attribute
        # (that convention only applies to actual form inputs).
        self.assertContains(resp, 'field-current_stock_display')

    def test_forged_post_from_normal_staff_cannot_change_stock(self):
        staff = _staff_admin()
        self.client.force_login(staff)
        product = _product(stock=Decimal('100'))
        payload = _edit_payload(
            product, desired_current_stock='999999', stock_adjustment_reason='hack',
        )
        resp = self.client.post(_change_url(product.pk), payload)
        # The field doesn't exist on this user's form at all, so the
        # forged keys are simply ignored — other Product fields still save.
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('100'))
        self.assertFalse(
            StockMovement.objects.filter(product=product, quantity=Decimal('999899')).exists()
        )

    def test_normal_staff_admin_can_still_edit_other_product_fields(self):
        staff = _staff_admin()
        self.client.force_login(staff)
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(product, name='نام ویرایش‌شده'))
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.name, 'نام ویرایش‌شده')
        self.assertEqual(product.current_stock, Decimal('100'))

    def test_superuser_can_adjust_stock(self):
        self.client.force_login(_superuser())
        product = _product(stock=Decimal('100'))
        resp = self.client.post(_change_url(product.pk), _edit_payload(
            product, desired_current_stock='120', stock_adjustment_reason='بازرسی دوره‌ای',
        ))
        self.assertEqual(resp.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('120'))


# ---------------------------------------------------------------------------
# Regressions: Purchase / Surgery / detail / movement history / Excel export
# ---------------------------------------------------------------------------

class StockAdjustmentRegressionTest(APITestCase):
    def setUp(self):
        self.superuser = _superuser()
        self.client.force_authenticate(self.superuser)

    def test_purchase_confirm_inbound_movement_still_works(self):
        from inventory.models import Purchase, PurchaseItem, Vendor
        vendor = Vendor.objects.create(name='فروشنده تست اصلاح')
        product = _product(stock=Decimal('0'))
        purchase = Purchase.objects.create(vendor=vendor)
        PurchaseItem.objects.create(purchase=purchase, product=product, quantity=Decimal('10'), unit_price=Decimal('100'))
        purchase.confirm()
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('10'))

    def test_surgery_used_item_consumption_still_works(self):
        import datetime
        from surgeries.models import Patient, SurgeryHistory, SurgeryType, SurgeryUsedItem
        product = _product(stock=Decimal('20'))
        patient = Patient.objects.create(full_name='بیمار اصلاح', case_code='ADJ-CASE-1', phone_number='09120000000')
        stype = SurgeryType.objects.create(name='نوع اصلاح', code='adj_type', base_rate=Decimal('1000000'))
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype, amount=Decimal('1000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        item = SurgeryUsedItem.objects.create(surgery=surgery, product=product, quantity=Decimal('1'))
        from surgeries.services import SurgeryInventoryService
        SurgeryInventoryService.consume_product(item)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('19'))

    def test_product_detail_page_loads_after_adjustment(self):
        # Admin pages use session auth, not the DRF token force_authenticate()
        # set up in setUp() for the API-focused tests in this class.
        self.client.force_login(self.superuser)
        product = _product(stock=Decimal('100'))
        StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('130'), reason='x')
        resp = self.client.get(f'/admin/inventory/product/{product.pk}/detail/')
        self.assertEqual(resp.status_code, 200)

    def test_product_change_page_shows_movement_history_after_adjustment(self):
        self.client.force_login(self.superuser)
        product = _product(stock=Decimal('100'))
        StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('130'), reason='بازرسی')
        resp = self.client.get(_change_url(product.pk))
        self.assertContains(resp, 'بازرسی')

    def test_product_excel_export_reflects_new_stock(self):
        product = _product(stock=Decimal('100'), name='محصول اکسل اصلاح')
        StockService.adjust_to_quantity(product=product, desired_quantity=Decimal('130'), reason='x')
        resp = self.client.get('/api/v1/inventory/products/', {'export': 'excel', 'search': product.internal_code})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_product_serializer_current_stock_remains_read_only(self):
        """Ordinary Product PATCH must never bypass the ledger."""
        product = _product(stock=Decimal('100'))
        resp = self.client.patch(f'/api/v1/inventory/products/{product.pk}/', {'current_stock': '999'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal('100'))
