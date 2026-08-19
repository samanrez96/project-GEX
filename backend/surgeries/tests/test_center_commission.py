"""Tests for CLI-37: center commission calculation and finance income sync.

Covers:
  - Service-level: calculate_center_commission() logic
  - Service-level: sync_center_commission_income() create / update / cancel
  - API-level: POST creates income, PATCH updates income
  - Validation: percent > 100, negative amount, etc.
  - Idempotency: repeated saves produce exactly one income record
  - Priority: center_commission_amount overrides center_commission_percent
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import CenterCommissionIncome, IncomeStatus
from surgeries.models import Patient, SurgeryHistory, SurgeryStatus, SurgeryType
from surgeries.services import SurgeryFinanceService

User = get_user_model()

HISTORY_URL = '/api/v1/surgeries/history/'

_counter = [0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _surgery(amount='10000000', commission_percent=None, commission_amount=None, **kwargs):
    defaults = {
        'patient':      _patient(),
        'surgery_type': _surgery_type(),
        'amount':       Decimal(amount),
        'surgery_date': datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    }
    if commission_percent is not None:
        defaults['center_commission_percent'] = Decimal(str(commission_percent))
    if commission_amount is not None:
        defaults['center_commission_amount'] = Decimal(str(commission_amount))
    defaults.update(kwargs)
    return SurgeryHistory.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Unit tests — calculate_center_commission()
# ---------------------------------------------------------------------------

class CalculateCenterCommissionTest(TestCase):

    def test_amount_field_used_directly(self):
        s = _surgery(amount='10000000', commission_amount='800000')
        self.assertEqual(
            SurgeryFinanceService.calculate_center_commission(s),
            Decimal('800000'),
        )

    def test_percent_calculates_correctly(self):
        s = _surgery(amount='10000000', commission_percent='20')
        self.assertEqual(
            SurgeryFinanceService.calculate_center_commission(s),
            Decimal('2000000'),
        )

    def test_amount_takes_priority_over_percent(self):
        s = _surgery(amount='10000000', commission_percent='20', commission_amount='500000')
        self.assertEqual(
            SurgeryFinanceService.calculate_center_commission(s),
            Decimal('500000'),  # amount, NOT 20% of 10M
        )

    def test_no_commission_returns_zero(self):
        s = _surgery(amount='10000000')
        self.assertEqual(
            SurgeryFinanceService.calculate_center_commission(s),
            Decimal('0'),
        )

    def test_zero_percent_returns_zero(self):
        s = _surgery(amount='10000000', commission_percent='0')
        self.assertEqual(
            SurgeryFinanceService.calculate_center_commission(s),
            Decimal('0'),
        )

    def test_fractional_percent(self):
        s = _surgery(amount='10000000', commission_percent='15.5')
        self.assertEqual(
            SurgeryFinanceService.calculate_center_commission(s),
            Decimal('1550000'),
        )


# ---------------------------------------------------------------------------
# Unit tests — sync_center_commission_income()
# ---------------------------------------------------------------------------

class SyncCenterCommissionIncomeTest(TestCase):

    def test_creates_income_with_percent(self):
        s = _surgery(amount='10000000', commission_percent='20')
        SurgeryFinanceService.sync_center_commission_income(s)

        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.amount, Decimal('2000000'))
        self.assertEqual(income.status, IncomeStatus.CONFIRMED)

    def test_creates_income_with_amount(self):
        s = _surgery(amount='10000000', commission_amount='750000')
        SurgeryFinanceService.sync_center_commission_income(s)

        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.amount, Decimal('750000'))
        self.assertEqual(income.status, IncomeStatus.CONFIRMED)

    def test_no_commission_no_income_created(self):
        s = _surgery(amount='10000000')
        SurgeryFinanceService.sync_center_commission_income(s)
        self.assertFalse(CenterCommissionIncome.objects.filter(surgery=s).exists())

    def test_income_date_matches_surgery_date(self):
        s = _surgery(amount='10000000', commission_percent='10')
        SurgeryFinanceService.sync_center_commission_income(s)
        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.income_date, s.surgery_date)

    def test_idempotent_repeated_calls_no_duplicates(self):
        s = _surgery(amount='10000000', commission_percent='10')
        SurgeryFinanceService.sync_center_commission_income(s)
        SurgeryFinanceService.sync_center_commission_income(s)
        SurgeryFinanceService.sync_center_commission_income(s)
        self.assertEqual(CenterCommissionIncome.objects.filter(surgery=s).count(), 1)

    def test_update_surgery_amount_updates_income(self):
        s = _surgery(amount='10000000', commission_percent='20')
        SurgeryFinanceService.sync_center_commission_income(s)

        s.amount = Decimal('20000000')
        s.save()
        SurgeryFinanceService.sync_center_commission_income(s)

        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.amount, Decimal('4000000'))  # 20% of 20M

    def test_update_percent_updates_income(self):
        s = _surgery(amount='10000000', commission_percent='20')
        SurgeryFinanceService.sync_center_commission_income(s)

        s.center_commission_percent = Decimal('30')
        s.save()
        SurgeryFinanceService.sync_center_commission_income(s)

        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.amount, Decimal('3000000'))

    def test_update_amount_field_updates_income(self):
        s = _surgery(amount='10000000', commission_amount='500000')
        SurgeryFinanceService.sync_center_commission_income(s)

        s.center_commission_amount = Decimal('900000')
        s.save()
        SurgeryFinanceService.sync_center_commission_income(s)

        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.amount, Decimal('900000'))

    def test_removing_commission_cancels_existing_income(self):
        s = _surgery(amount='10000000', commission_percent='20')
        SurgeryFinanceService.sync_center_commission_income(s)

        # Remove commission
        s.center_commission_percent = None
        s.save()
        SurgeryFinanceService.sync_center_commission_income(s)

        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.status, IncomeStatus.CANCELLED)

    def test_no_duplicate_income_on_repeated_update(self):
        s = _surgery(amount='10000000', commission_percent='10')
        for _ in range(5):
            SurgeryFinanceService.sync_center_commission_income(s)
        self.assertEqual(CenterCommissionIncome.objects.filter(surgery=s).count(), 1)

    def test_cancelled_income_reactivated_when_commission_restored(self):
        s = _surgery(amount='10000000', commission_percent='10')
        SurgeryFinanceService.sync_center_commission_income(s)

        # Cancel
        s.center_commission_percent = None
        s.save()
        SurgeryFinanceService.sync_center_commission_income(s)
        income = CenterCommissionIncome.objects.get(surgery=s)
        self.assertEqual(income.status, IncomeStatus.CANCELLED)

        # Restore
        s.center_commission_percent = Decimal('15')
        s.save()
        SurgeryFinanceService.sync_center_commission_income(s)
        income.refresh_from_db()
        self.assertEqual(income.status, IncomeStatus.CONFIRMED)
        self.assertEqual(income.amount, Decimal('1500000'))


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class SurgeryHistoryCommissionAPITest(APITestCase):

    def setUp(self):
        self.user         = User.objects.create_superuser('cctest', 'cc@test.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.patient      = _patient()
        self.surgery_type = _surgery_type()

    def _post(self, amount='10000000', **kwargs):
        payload = {
            'patient':      self.patient.pk,
            'surgery_type': self.surgery_type.pk,
            'amount':       amount,
            'surgery_date': '2025-06-01T10:00:00Z',
        }
        payload.update(kwargs)
        return self.client.post(HISTORY_URL, payload, format='json')

    def test_post_with_percent_creates_income(self):
        res = self._post(amount='10000000', center_commission_percent='20')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        sh = SurgeryHistory.objects.get(pk=res.data['id'])
        income = CenterCommissionIncome.objects.get(surgery=sh)
        self.assertEqual(income.amount, Decimal('2000000'))
        self.assertEqual(income.status, IncomeStatus.CONFIRMED)

    def test_post_with_commission_amount_creates_income(self):
        res = self._post(amount='10000000', center_commission_amount='600000')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        sh = SurgeryHistory.objects.get(pk=res.data['id'])
        income = CenterCommissionIncome.objects.get(surgery=sh)
        self.assertEqual(income.amount, Decimal('600000'))

    def test_post_amount_overrides_percent(self):
        res = self._post(
            amount='10000000',
            center_commission_percent='20',
            center_commission_amount='300000',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        sh = SurgeryHistory.objects.get(pk=res.data['id'])
        income = CenterCommissionIncome.objects.get(surgery=sh)
        self.assertEqual(income.amount, Decimal('300000'))

    def test_post_no_commission_no_income(self):
        res = self._post()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        sh = SurgeryHistory.objects.get(pk=res.data['id'])
        self.assertFalse(CenterCommissionIncome.objects.filter(surgery=sh).exists())

    def test_post_invalid_percent_over_100_returns_400(self):
        res = self._post(center_commission_percent='110')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('center_commission_percent', res.data)

    def test_post_negative_commission_amount_returns_400(self):
        res = self._post(center_commission_amount='-1000')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('center_commission_amount', res.data)

    def test_patch_amount_updates_income(self):
        res = self._post(amount='10000000', center_commission_percent='20')
        sh_pk = res.data['id']

        patch_res = self.client.patch(
            f'{HISTORY_URL}{sh_pk}/',
            {'amount': '20000000'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)

        sh = SurgeryHistory.objects.get(pk=sh_pk)
        income = CenterCommissionIncome.objects.get(surgery=sh)
        self.assertEqual(income.amount, Decimal('4000000'))  # 20% of 20M

    def test_patch_percent_updates_income(self):
        res = self._post(amount='10000000', center_commission_percent='10')
        sh_pk = res.data['id']

        self.client.patch(
            f'{HISTORY_URL}{sh_pk}/',
            {'center_commission_percent': '25'},
            format='json',
        )
        sh = SurgeryHistory.objects.get(pk=sh_pk)
        income = CenterCommissionIncome.objects.get(surgery=sh)
        self.assertEqual(income.amount, Decimal('2500000'))

    def test_patch_removes_commission_cancels_income(self):
        res = self._post(amount='10000000', center_commission_percent='10')
        sh_pk = res.data['id']

        self.client.patch(
            f'{HISTORY_URL}{sh_pk}/',
            {'center_commission_percent': None},
            format='json',
        )
        sh = SurgeryHistory.objects.get(pk=sh_pk)
        income = CenterCommissionIncome.objects.get(surgery=sh)
        self.assertEqual(income.status, IncomeStatus.CANCELLED)

    def test_patch_repeated_does_not_create_duplicates(self):
        res = self._post(amount='10000000', center_commission_percent='10')
        sh_pk = res.data['id']

        for _ in range(4):
            self.client.patch(
                f'{HISTORY_URL}{sh_pk}/',
                {'description': 'تست'},
                format='json',
            )
        self.assertEqual(
            CenterCommissionIncome.objects.filter(surgery_id=sh_pk).count(),
            1,
        )

    def test_response_includes_commission_income_amount(self):
        res = self._post(amount='10000000', center_commission_percent='20')
        detail_res = self.client.get(f"{HISTORY_URL}{res.data['id']}/")
        self.assertIn('center_commission_income_amount', detail_res.data)
        self.assertEqual(
            Decimal(str(detail_res.data['center_commission_income_amount'])),
            Decimal('2000000'),
        )

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self._post()
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
