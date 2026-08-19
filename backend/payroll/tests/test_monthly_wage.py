import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, GenderChoice, JobPosition
from payroll.models import MonthlyWage, PayrollTypeConfig

User = get_user_model()

WAGES_URL = '/api/v2/payroll/wages/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(name='پرستار'):
    pos, _ = JobPosition.objects.get_or_create(name=name, defaults={'is_active': True})
    return pos


_emp_counter = [0]


def make_employee(**kwargs):
    _emp_counter[0] += 1
    if 'job_position' not in kwargs:
        kwargs['job_position'] = make_position()
    defaults = {
        'full_name':               f'کارمند {_emp_counter[0]}',
        'national_id':             str(_emp_counter[0]).zfill(10),
        'gender':                  GenderChoice.MALE,
        'start_date':              datetime.date(2022, 1, 1),
        'personal_phone':          f'091{str(_emp_counter[0]).zfill(8)}',
        'emergency_contact_phone': '09120000000',
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_wage(employee, amount='5000000', start='2024-01-01', end=None, **kwargs):
    return MonthlyWage.objects.create(
        employee=employee,
        amount=Decimal(amount),
        start_date=datetime.date.fromisoformat(start),
        end_date=datetime.date.fromisoformat(end) if end else None,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class MonthlyWageModelTest(TestCase):

    def setUp(self):
        self.emp = make_employee()

    def test_create_wage_success(self):
        w = make_wage(self.emp)
        self.assertEqual(w.employee, self.emp)
        self.assertEqual(w.amount, Decimal('5000000'))
        self.assertTrue(w.is_active)

    def test_str(self):
        w = make_wage(self.emp, amount='3000000')
        self.assertIn('3,000,000', str(w))
        self.assertIn('ریال', str(w))

    def test_amount_immutability_raises_on_change(self):
        w = make_wage(self.emp)
        w.amount = Decimal('9000000')
        with self.assertRaises(ValueError):
            w.save()

    def test_amount_immutability_allows_other_field_update(self):
        w = make_wage(self.emp)
        w.notes = 'یادداشت جدید'
        w.save()  # should not raise
        w.refresh_from_db()
        self.assertEqual(w.notes, 'یادداشت جدید')

    def test_clean_raises_on_overlapping_active_wages(self):
        make_wage(self.emp, start='2024-01-01', end='2024-06-30')
        w2 = MonthlyWage(
            employee=self.emp,
            amount=Decimal('6000000'),
            start_date=datetime.date(2024, 3, 1),
            end_date=datetime.date(2024, 12, 31),
        )
        with self.assertRaises(ValidationError):
            w2.full_clean()

    def test_clean_allows_non_overlapping_wages(self):
        make_wage(self.emp, start='2024-01-01', end='2024-06-30')
        w2 = MonthlyWage(
            employee=self.emp,
            amount=Decimal('6000000'),
            start_date=datetime.date(2024, 7, 1),
        )
        w2.full_clean()  # should not raise

    def test_clean_raises_when_end_date_before_start_date(self):
        w = MonthlyWage(
            employee=self.emp,
            amount=Decimal('5000000'),
            start_date=datetime.date(2024, 6, 1),
            end_date=datetime.date(2024, 1, 1),
        )
        with self.assertRaises(ValidationError):
            w.full_clean()

    def test_clean_allows_open_ended_wage(self):
        w = MonthlyWage(
            employee=self.emp,
            amount=Decimal('5000000'),
            start_date=datetime.date(2024, 1, 1),
            end_date=None,
        )
        w.full_clean()  # should not raise

    def test_delete_raises_protected_error(self):
        w = make_wage(self.emp)
        with self.assertRaises(ProtectedError):
            w.delete()

    # ── Signal tests ─────────────────────────────────────────────────

    def test_signal_sets_has_monthly_wage_true_on_create(self):
        cfg = PayrollTypeConfig.objects.get(employee=self.emp)
        self.assertFalse(cfg.has_monthly_wage)
        make_wage(self.emp)
        cfg.refresh_from_db()
        self.assertTrue(cfg.has_monthly_wage)

    def test_signal_sets_has_monthly_wage_false_when_last_deactivated(self):
        w = make_wage(self.emp)
        w.is_active = False
        w.save()
        cfg = PayrollTypeConfig.objects.get(employee=self.emp)
        self.assertFalse(cfg.has_monthly_wage)

    def test_signal_keeps_flag_true_when_one_of_two_deactivated(self):
        emp2 = make_employee()
        w1 = make_wage(emp2, start='2024-01-01', end='2024-06-30')
        w1.is_active = False
        w1.save()
        w2 = make_wage(emp2, start='2024-07-01')
        cfg = PayrollTypeConfig.objects.get(employee=emp2)
        self.assertTrue(cfg.has_monthly_wage)

    # ── Period aggregate tests ────────────────────────────────────────

    def test_get_total_for_period_correct_sum(self):
        # Jalali 1402/10 ≈ Gregorian 2024-01
        emp2 = make_employee()
        make_wage(self.emp, amount='5000000', start='2024-01-01')
        make_wage(emp2,    amount='3000000', start='2024-01-01')
        total = MonthlyWage.get_total_for_period(1402, 10)
        self.assertEqual(total, Decimal('8000000'))

    def test_get_total_for_period_excludes_out_of_range(self):
        # Wage starts after the period ends
        make_wage(self.emp, amount='5000000', start='2025-01-01')
        # Jalali 1402/10 ≈ 2024-01 — wage not active yet
        total = MonthlyWage.get_total_for_period(1402, 10)
        self.assertEqual(total, Decimal('0'))

    def test_get_total_for_period_includes_open_ended(self):
        make_wage(self.emp, amount='4000000', start='2023-01-01', end=None)
        total = MonthlyWage.get_total_for_period(1402, 10)
        self.assertEqual(total, Decimal('4000000'))

    def test_is_active_for_period_in_range(self):
        w = make_wage(self.emp, start='2024-01-01', end=None)
        self.assertTrue(w.is_active_for_period(1402, 10))  # 1402/10 ≈ 2024-01

    def test_is_active_for_period_out_of_range(self):
        w = make_wage(self.emp, start='2025-01-01', end=None)
        self.assertFalse(w.is_active_for_period(1402, 10))  # period ends before wage starts


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class MonthlyWageAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('wagetest', 'w@test.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.emp = make_employee()

    def test_post_creates_wage_and_sets_config_flag(self):
        res = self.client.post(WAGES_URL, {
            'employee':   self.emp.pk,
            'amount':     '5000000',
            'start_date': '2024-01-01',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        cfg = PayrollTypeConfig.objects.get(employee=self.emp)
        self.assertTrue(cfg.has_monthly_wage)

    def test_post_with_overlapping_dates_returns_400(self):
        make_wage(self.emp, start='2024-01-01', end='2024-12-31')
        res = self.client.post(WAGES_URL, {
            'employee':   self.emp.pk,
            'amount':     '6000000',
            'start_date': '2024-06-01',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_amount_returns_400(self):
        w = make_wage(self.emp)
        res = self.client.patch(
            f'{WAGES_URL}{w.pk}/',
            {'amount': '9000000'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_notes_returns_200(self):
        w = make_wage(self.emp)
        res = self.client.patch(
            f'{WAGES_URL}{w.pk}/',
            {'notes': 'یادداشت'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['notes'], 'یادداشت')

    def test_delete_returns_405(self):
        w = make_wage(self.emp)
        res = self.client.delete(f'{WAGES_URL}{w.pk}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_filter_by_employee_and_is_active(self):
        emp2 = make_employee()
        make_wage(self.emp)
        make_wage(emp2)
        res = self.client.get(WAGES_URL, {'employee': self.emp.pk, 'is_active': 'true'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for item in res.data['results']:
            self.assertEqual(item['employee_name'], self.emp.full_name)

    def test_period_summary_returns_correct_totals(self):
        make_wage(self.emp, amount='5000000', start='2025-03-21')  # 1404/01/01
        res = self.client.get(f'{WAGES_URL}period_summary/', {'year': 1404, 'month': 1})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(res.data['total_amount'])), Decimal('5000000'))
        self.assertEqual(res.data['employee_count'], 1)

    def test_period_summary_without_params_returns_400(self):
        res = self.client.get(f'{WAGES_URL}period_summary/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(WAGES_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
