"""Tests: automatic income Transaction creation from surgery center commission.

Covers:
  - surgery creates center commission income Transaction
  - income is linked to CenterCommissionIncome via GFK
  - changing surgery amount updates income Transaction
  - changing center commission percent updates income Transaction
  - duplicate income records are not created
  - cancelling commission cancels income Transaction
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import (
    CenterCommissionIncome,
    FinanceCategory,
    IncomeStatus,
    Transaction,
    TransactionPaymentStatus,
    TransactionType,
)
from surgeries.models import Patient, SurgeryHistory, SurgeryType

User = get_user_model()

HISTORY_URL = '/api/v1/surgeries/history/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_patient():
    import uuid
    return Patient.objects.create(
        full_name='بیمار تست',
        case_code=uuid.uuid4().hex[:10],
    )


def make_surgery_type(name='جراحی عمومی'):
    obj, _ = SurgeryType.objects.get_or_create(
        name=name,
        defaults={'code': name[:6].lower().replace(' ', '_'), 'base_rate': Decimal('0')},
    )
    return obj


def make_surgery(patient=None, surgery_type=None, amount=Decimal('1000000'),
                 commission_percent=None, commission_amount=None):
    if patient is None:
        patient = make_patient()
    if surgery_type is None:
        surgery_type = make_surgery_type()
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        surgery_date=timezone.now(),
        amount=amount,
        center_commission_percent=commission_percent,
        center_commission_amount=commission_amount,
    )


def income_transaction_for(commission_income):
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(commission_income)
    return Transaction.objects.filter(
        content_type=ct,
        object_id=commission_income.pk,
        transaction_type=TransactionType.INCOME,
    )


# ---------------------------------------------------------------------------
# Model-level tests
# ---------------------------------------------------------------------------

class SurgeryIncomeTransactionTest(TestCase):

    def test_surgery_with_commission_creates_income_transaction(self):
        """A surgery with center commission must create an income Transaction."""
        surgery = make_surgery(commission_percent=Decimal('20'))
        from surgeries.services import SurgeryFinanceService
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci = CenterCommissionIncome.objects.get(surgery=surgery)
        txs = income_transaction_for(cci)
        self.assertEqual(txs.count(), 1)

        tx = txs.first()
        self.assertEqual(tx.transaction_type, TransactionType.INCOME)
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PAID)

    def test_income_linked_to_center_commission_income_via_gfk(self):
        """Income Transaction must be linked to CenterCommissionIncome via GFK."""
        from django.contrib.contenttypes.models import ContentType
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(commission_percent=Decimal('15'))
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci    = CenterCommissionIncome.objects.get(surgery=surgery)
        tx     = income_transaction_for(cci).first()
        cci_ct = ContentType.objects.get_for_model(cci)

        self.assertEqual(tx.content_type, cci_ct)
        self.assertEqual(tx.object_id, cci.pk)

    def test_income_uses_center_commission_income_category(self):
        """Income Transaction must use the seeded center commission category."""
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(commission_percent=Decimal('10'))
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci = CenterCommissionIncome.objects.get(surgery=surgery)
        tx  = income_transaction_for(cci).first()
        self.assertEqual(tx.category.name, 'کمیسیون مرکز از اعمال جراحی')
        self.assertEqual(tx.category.category_type, 'income')

    def test_income_amount_matches_commission(self):
        """Income Transaction amount must match CenterCommissionIncome amount."""
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(amount=Decimal('2000000'), commission_percent=Decimal('10'))
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci            = CenterCommissionIncome.objects.get(surgery=surgery)
        expected_amount = Decimal('2000000') * Decimal('10') / Decimal('100')
        self.assertEqual(cci.amount, expected_amount)

        tx = income_transaction_for(cci).first()
        self.assertEqual(tx.amount, expected_amount)

    def test_no_duplicate_income_transaction(self):
        """Calling sync multiple times must not create duplicate income Transactions."""
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(commission_percent=Decimal('20'))
        SurgeryFinanceService.sync_center_commission_income(surgery)
        SurgeryFinanceService.sync_center_commission_income(surgery)
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci = CenterCommissionIncome.objects.get(surgery=surgery)
        txs = income_transaction_for(cci)
        self.assertEqual(txs.count(), 1)

    def test_changing_surgery_amount_updates_income_transaction(self):
        """Updating surgery amount must update the income Transaction amount."""
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(amount=Decimal('1000000'), commission_percent=Decimal('10'))
        SurgeryFinanceService.sync_center_commission_income(surgery)

        # Update amount
        surgery.amount = Decimal('2000000')
        surgery.save()
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci = CenterCommissionIncome.objects.get(surgery=surgery)
        tx  = income_transaction_for(cci).first()
        self.assertEqual(cci.amount, Decimal('200000.00'))
        self.assertEqual(tx.amount, Decimal('200000.00'))

    def test_changing_commission_percent_updates_income_transaction(self):
        """Updating center_commission_percent must update the income Transaction."""
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(amount=Decimal('1000000'), commission_percent=Decimal('10'))
        SurgeryFinanceService.sync_center_commission_income(surgery)

        surgery.center_commission_percent = Decimal('20')
        surgery.save()
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci = CenterCommissionIncome.objects.get(surgery=surgery)
        tx  = income_transaction_for(cci).first()
        self.assertEqual(tx.amount, Decimal('200000.00'))

    def test_zero_commission_cancels_income_transaction(self):
        """Removing commission must cancel the income Transaction (not delete)."""
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(amount=Decimal('1000000'), commission_percent=Decimal('10'))
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci_before = CenterCommissionIncome.objects.get(surgery=surgery)
        self.assertEqual(income_transaction_for(cci_before).count(), 1)

        # Remove commission
        surgery.center_commission_percent = None
        surgery.center_commission_amount  = None
        surgery.save()
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci_after = CenterCommissionIncome.objects.get(surgery=surgery)
        self.assertEqual(cci_after.status, IncomeStatus.CANCELLED)

        tx = income_transaction_for(cci_after).first()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.CANCELLED)

    def test_fixed_commission_amount_creates_income_transaction(self):
        """center_commission_amount takes priority over percent."""
        from surgeries.services import SurgeryFinanceService

        surgery = make_surgery(
            amount=Decimal('1000000'),
            commission_percent=Decimal('10'),
            commission_amount=Decimal('50000'),
        )
        SurgeryFinanceService.sync_center_commission_income(surgery)

        cci = CenterCommissionIncome.objects.get(surgery=surgery)
        tx  = income_transaction_for(cci).first()
        # Fixed amount takes priority
        self.assertEqual(tx.amount, Decimal('50000.00'))

    def test_no_income_transaction_when_no_commission(self):
        """A surgery with no commission must not create any income Transaction."""
        surgery = make_surgery()  # no commission configured

        from surgeries.services import SurgeryFinanceService
        SurgeryFinanceService.sync_center_commission_income(surgery)

        total_txs = Transaction.objects.filter(
            transaction_type=TransactionType.INCOME,
            description__contains=f'عمل #{surgery.pk}',
        ).count()
        self.assertEqual(total_txs, 0)


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------

class SurgeryIncomeTransactionAPITest(APITestCase):

    def setUp(self):
        self.user         = User.objects.create_user(username='surg_user', password='pass')
        self.client.force_authenticate(user=self.user)
        self.surgery_type = make_surgery_type('لیزر')
        self.patient      = make_patient()

    def test_post_surgery_creates_income_transaction(self):
        """POST to surgery history with commission must create income Transaction."""
        payload = {
            'patient':                   self.patient.pk,
            'surgery_type':              self.surgery_type.pk,
            'surgery_date':              '2026-01-15T10:00:00Z',
            'amount':                    '1000000',
            'center_commission_percent': '10',
        }
        resp = self.client.post(HISTORY_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        surgery_pk = resp.data['id']
        surgery    = SurgeryHistory.objects.get(pk=surgery_pk)
        cci        = CenterCommissionIncome.objects.get(surgery=surgery)

        txs = income_transaction_for(cci)
        self.assertEqual(txs.count(), 1)
        self.assertEqual(txs.first().amount, Decimal('100000.00'))

    def test_patch_surgery_updates_income_transaction(self):
        """PATCH to update commission percent must update the income Transaction."""
        payload = {
            'patient':                   self.patient.pk,
            'surgery_type':              self.surgery_type.pk,
            'surgery_date':              '2026-01-15T10:00:00Z',
            'amount':                    '1000000',
            'center_commission_percent': '10',
        }
        create_resp = self.client.post(HISTORY_URL, payload, format='json')
        surgery_pk  = create_resp.data['id']

        update_resp = self.client.patch(
            f'{HISTORY_URL}{surgery_pk}/',
            {'center_commission_percent': '20'},
            format='json',
        )
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK)

        surgery = SurgeryHistory.objects.get(pk=surgery_pk)
        cci     = CenterCommissionIncome.objects.get(surgery=surgery)
        tx      = income_transaction_for(cci).first()
        self.assertEqual(tx.amount, Decimal('200000.00'))

    def test_unauthenticated_cannot_access_surgery(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(HISTORY_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
