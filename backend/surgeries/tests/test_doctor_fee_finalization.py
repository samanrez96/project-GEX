"""Phase 7 tests: Doctor rate lookup, fee snapshot, and Finance expense
creation at Surgery finalization (status=COMPLETED).
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from contacts.models import Doctor, DoctorSpecialty, DoctorSurgeryRate
from contacts.services import DoctorRateService
from finance.models import CenterCommissionIncome, DoctorFeeExpense, IncomeStatus
from finance.models import Transaction, TransactionType
from payroll.models import CommissionTransaction
from surgeries.models import Patient, SurgeryHistory, SurgeryStatus, SurgeryType
from surgeries.services import SurgeryFinanceService

User = get_user_model()
HISTORY_URL = '/api/v2/surgeries/history/'

_counter = [0]


def _specialty():
    _counter[0] += 1
    obj, _ = DoctorSpecialty.objects.get_or_create(name=f'تخصص فاز۷ {_counter[0]}')
    return obj


def _doctor(**kwargs):
    _counter[0] += 1
    defaults = {
        'full_name': f'دکتر فاز۷ {_counter[0]}',
        'specialty': _specialty(),
        'phone_number': f'0912{str(_counter[0]).zfill(7)}',
    }
    defaults.update(kwargs)
    return Doctor.objects.create(**defaults)


def _surgery_type(**kwargs):
    _counter[0] += 1
    defaults = {
        'name': f'نوع عمل فاز۷ {_counter[0]}',
        'code': f'p7_op_{_counter[0]}',
        'base_rate': Decimal('1000000'),
    }
    defaults.update(kwargs)
    return SurgeryType.objects.create(**defaults)


def _patient(**kwargs):
    _counter[0] += 1
    defaults = {
        'full_name': f'بیمار فاز۷ {_counter[0]}',
        'case_code': f'P7-CASE-{_counter[0]:04d}',
        'phone_number': f'0913{str(_counter[0]).zfill(7)}',
    }
    defaults.update(kwargs)
    return Patient.objects.create(**defaults)


def _surgery(doctor=None, surgery_type=None, status_=SurgeryStatus.PLANNED, **kwargs):
    defaults = {
        'patient': _patient(),
        'surgery_type': surgery_type or _surgery_type(),
        'clinical_doctor': doctor,
        'amount': Decimal('5000000'),
        'status': status_,
        'surgery_date': datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    }
    defaults.update(kwargs)
    return SurgeryHistory.objects.create(**defaults)


# ---------------------------------------------------------------------------
# DoctorRateService — exact rate lookup
# ---------------------------------------------------------------------------

class DoctorRateServiceTest(TestCase):

    def test_exact_rate_returned(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('750000'))
        self.assertEqual(DoctorRateService.get_rate(doctor, st), Decimal('750000'))

    def test_missing_rate_returns_none(self):
        doctor = _doctor()
        st = _surgery_type()
        self.assertIsNone(DoctorRateService.get_rate(doctor, st))

    def test_rate_is_specific_to_doctor_and_surgery_type_pair(self):
        doctor1 = _doctor()
        doctor2 = _doctor()
        st1 = _surgery_type()
        st2 = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor1, surgery_type=st1, rate=Decimal('100000'))
        DoctorSurgeryRate.objects.create(doctor=doctor1, surgery_type=st2, rate=Decimal('200000'))
        DoctorSurgeryRate.objects.create(doctor=doctor2, surgery_type=st1, rate=Decimal('300000'))
        self.assertEqual(DoctorRateService.get_rate(doctor1, st1), Decimal('100000'))
        self.assertEqual(DoctorRateService.get_rate(doctor1, st2), Decimal('200000'))
        self.assertEqual(DoctorRateService.get_rate(doctor2, st1), Decimal('300000'))

    def test_none_doctor_or_surgery_type_returns_none(self):
        self.assertIsNone(DoctorRateService.get_rate(None, _surgery_type()))
        self.assertIsNone(DoctorRateService.get_rate(_doctor(), None))


# ---------------------------------------------------------------------------
# Missing-rate finalization validation (blocks)
# ---------------------------------------------------------------------------

class MissingRateFinalizationValidationTest(TestCase):

    def test_service_raises_when_rate_missing(self):
        doctor = _doctor()
        st = _surgery_type()
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        with self.assertRaises(ValidationError):
            SurgeryFinanceService.sync_doctor_fee_expense(surgery)
        self.assertFalse(DoctorFeeExpense.objects.filter(surgery=surgery).exists())

    def test_model_clean_raises_when_rate_missing(self):
        doctor = _doctor()
        st = _surgery_type()
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        with self.assertRaises(ValidationError):
            surgery.clean()

    def test_clean_passes_when_rate_exists(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('100000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        surgery.clean()  # must not raise

    def test_no_doctor_assigned_does_not_block(self):
        st = _surgery_type()
        surgery = _surgery(doctor=None, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)  # must not raise
        self.assertFalse(DoctorFeeExpense.objects.filter(surgery=surgery).exists())

    def test_non_completed_status_does_not_require_rate(self):
        doctor = _doctor()
        st = _surgery_type()
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.PLANNED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)  # must not raise
        surgery.clean()  # must not raise


# ---------------------------------------------------------------------------
# Doctor fee snapshot + Finance expense creation/update
# ---------------------------------------------------------------------------

class DoctorFeeSnapshotAndExpenseTest(TestCase):

    def test_snapshot_created_on_finalization(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('900000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        fee = DoctorFeeExpense.objects.get(surgery=surgery)
        self.assertEqual(fee.amount, Decimal('900000'))
        self.assertEqual(fee.doctor_id, doctor.pk)
        self.assertEqual(fee.surgery_type_id, st.pk)
        self.assertEqual(fee.status, IncomeStatus.CONFIRMED)

    def test_exactly_one_finance_expense_created(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('500000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        fee = DoctorFeeExpense.objects.get(surgery=surgery)
        expenses = Transaction.objects.filter(
            transaction_type=TransactionType.EXPENSE,
            content_type__model='doctorfeeexpense',
            object_id=fee.pk,
        )
        self.assertEqual(expenses.count(), 1)
        self.assertEqual(expenses.first().amount, Decimal('500000'))

    def test_expense_updates_if_snapshot_amount_changes_directly(self):
        # Snapshot amount itself is never recomputed by the sync service,
        # but the mirrored Transaction must still stay in sync if the
        # snapshot row is edited directly (e.g. a correction) — same
        # convention as CenterCommissionIncome/Transaction sync.
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('500000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        fee = DoctorFeeExpense.objects.get(surgery=surgery)
        fee.amount = Decimal('650000')
        fee.save(update_fields=['amount', 'updated_at'])

        tx = Transaction.objects.get(content_type__model='doctorfeeexpense', object_id=fee.pk)
        self.assertEqual(tx.amount, Decimal('650000'))


# ---------------------------------------------------------------------------
# Idempotency: repeated saves / API requests
# ---------------------------------------------------------------------------

class DoctorFeeIdempotencyTest(TestCase):

    def test_repeated_service_call_creates_exactly_one_snapshot(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('400000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)

        SurgeryFinanceService.sync_doctor_fee_expense(surgery)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        self.assertEqual(DoctorFeeExpense.objects.filter(surgery=surgery).count(), 1)

    def test_repeated_save_does_not_duplicate_expense_transaction(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('400000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)

        SurgeryFinanceService.sync_doctor_fee_expense(surgery)
        surgery.description = 'به‌روزرسانی جزئی'
        surgery.save()
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        fee = DoctorFeeExpense.objects.get(surgery=surgery)
        expenses = Transaction.objects.filter(content_type__model='doctorfeeexpense', object_id=fee.pk)
        self.assertEqual(expenses.count(), 1)


# ---------------------------------------------------------------------------
# Finalized historical-rate preservation + future Surgery uses updated rate
# ---------------------------------------------------------------------------

class HistoricalRatePreservationTest(TestCase):

    def test_rate_change_after_finalization_does_not_alter_snapshot(self):
        doctor = _doctor()
        st = _surgery_type()
        rate_row = DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('500000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        rate_row.rate = Decimal('999999')
        rate_row.save(update_fields=['rate', 'updated_at'])

        # Re-sync (simulating another save of the already-completed surgery)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        fee = DoctorFeeExpense.objects.get(surgery=surgery)
        self.assertEqual(fee.amount, Decimal('500000'))  # unchanged — frozen at finalization

    def test_future_surgery_uses_updated_rate(self):
        doctor = _doctor()
        st = _surgery_type()
        rate_row = DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('500000'))
        surgery1 = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery1)

        rate_row.rate = Decimal('700000')
        rate_row.save(update_fields=['rate', 'updated_at'])

        surgery2 = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery2)

        fee1 = DoctorFeeExpense.objects.get(surgery=surgery1)
        fee2 = DoctorFeeExpense.objects.get(surgery=surgery2)
        self.assertEqual(fee1.amount, Decimal('500000'))
        self.assertEqual(fee2.amount, Decimal('700000'))


# ---------------------------------------------------------------------------
# Surgery cancellation behavior
# ---------------------------------------------------------------------------

class SurgeryCancellationBehaviorTest(TestCase):

    def test_cancelling_finalized_surgery_cancels_fee_and_transaction(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('300000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        surgery.status = SurgeryStatus.CANCELLED
        surgery.save()
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        fee = DoctorFeeExpense.objects.get(surgery=surgery)
        self.assertEqual(fee.status, IncomeStatus.CANCELLED)
        tx = Transaction.objects.get(content_type__model='doctorfeeexpense', object_id=fee.pk)
        from finance.models import TransactionPaymentStatus
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.CANCELLED)

    def test_cancelling_before_finalization_creates_no_fee(self):
        doctor = _doctor()
        st = _surgery_type()
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.CANCELLED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)  # must not raise
        self.assertFalse(DoctorFeeExpense.objects.filter(surgery=surgery).exists())


# ---------------------------------------------------------------------------
# Center commission non-regression + no Payroll record created
# ---------------------------------------------------------------------------

class CrossFeatureNonRegressionTest(TestCase):

    def test_center_commission_unaffected_by_doctor_fee_sync(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('200000'))
        surgery = _surgery(
            doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED,
            center_commission_percent=Decimal('20'),
        )
        SurgeryFinanceService.sync_center_commission_income(surgery)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        income = CenterCommissionIncome.objects.get(surgery=surgery)
        self.assertEqual(income.amount, Decimal('1000000'))  # 20% of 5,000,000
        self.assertEqual(income.status, IncomeStatus.CONFIRMED)

    def test_no_employee_payroll_record_created(self):
        doctor = _doctor()
        st = _surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doctor, surgery_type=st, rate=Decimal('200000'))
        surgery = _surgery(doctor=doctor, surgery_type=st, status_=SurgeryStatus.COMPLETED)
        SurgeryFinanceService.sync_doctor_fee_expense(surgery)

        self.assertEqual(CommissionTransaction.objects.filter(surgery=surgery).count(), 0)


# ---------------------------------------------------------------------------
# API-level: SurgeryHistoryViewSet create/update
# ---------------------------------------------------------------------------

class SurgeryHistoryDoctorFeeAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('p7apitest', 'p7@test.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.patient = _patient()
        self.surgery_type = _surgery_type()
        self.doctor = _doctor()

    def _post(self, **overrides):
        payload = {
            'patient': self.patient.pk,
            'surgery_type': self.surgery_type.pk,
            'clinical_doctor': self.doctor.pk,
            'amount': '5000000',
            'surgery_date': '2025-06-01T10:00:00Z',
            'status': 'COMPLETED',
        }
        payload.update(overrides)
        return self.client.post(HISTORY_URL, payload, format='json')

    def test_post_completed_without_rate_returns_400(self):
        res = self._post()
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SurgeryHistory.objects.filter(patient=self.patient).exists())

    def test_post_completed_with_rate_creates_fee_and_expense(self):
        DoctorSurgeryRate.objects.create(doctor=self.doctor, surgery_type=self.surgery_type, rate=Decimal('450000'))
        res = self._post()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        sh = SurgeryHistory.objects.get(pk=res.data['id'])
        fee = DoctorFeeExpense.objects.get(surgery=sh)
        self.assertEqual(fee.amount, Decimal('450000'))
        expenses = Transaction.objects.filter(content_type__model='doctorfeeexpense', object_id=fee.pk)
        self.assertEqual(expenses.count(), 1)

    def test_repeated_patch_does_not_duplicate_expense(self):
        DoctorSurgeryRate.objects.create(doctor=self.doctor, surgery_type=self.surgery_type, rate=Decimal('450000'))
        res = self._post()
        sh_pk = res.data['id']

        for _ in range(3):
            patch_res = self.client.patch(f'{HISTORY_URL}{sh_pk}/', {'description': 'به‌روزرسانی'}, format='json')
            self.assertEqual(patch_res.status_code, status.HTTP_200_OK)

        sh = SurgeryHistory.objects.get(pk=sh_pk)
        fee = DoctorFeeExpense.objects.get(surgery=sh)
        self.assertEqual(
            Transaction.objects.filter(content_type__model='doctorfeeexpense', object_id=fee.pk).count(), 1,
        )

    def test_planned_surgery_without_rate_succeeds(self):
        res = self._post(status='PLANNED')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        sh = SurgeryHistory.objects.get(pk=res.data['id'])
        self.assertFalse(DoctorFeeExpense.objects.filter(surgery=sh).exists())
