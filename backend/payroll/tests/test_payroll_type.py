import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, GenderChoice, JobPosition
from payroll.models import (
    PERSIAN_MONTHS,
    PayrollPeriod,
    PayrollStatus,
    PayrollTypeConfig,
    _gregorian_to_jalali,
)

User = get_user_model()

PERIODS_URL = '/api/v1/payroll/periods/'
CONFIGS_URL = '/api/v1/payroll/configs/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(name='پرستار'):
    pos, _ = JobPosition.objects.get_or_create(name=name, defaults={'is_active': True})
    return pos


def make_employee(**kwargs):
    if 'job_position' not in kwargs:
        kwargs['job_position'] = make_position()
    defaults = {
        'full_name':               'علی رضایی',
        'national_id':             '0012345678',
        'gender':                  GenderChoice.MALE,
        'start_date':              datetime.date(2022, 3, 1),
        'personal_phone':          '09121234567',
        'emergency_contact_phone': '09129876543',
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_period(year=1403, month=1, **kwargs):
    defaults = {'status': PayrollStatus.OPEN}
    defaults.update(kwargs)
    period, _ = PayrollPeriod.objects.get_or_create(year=year, month=month, defaults=defaults)
    return period


# ---------------------------------------------------------------------------
# PayrollPeriod model tests
# ---------------------------------------------------------------------------

class PayrollPeriodModelTest(TestCase):

    def test_create_period_success(self):
        p = make_period(year=1403, month=5)
        self.assertEqual(p.year, 1403)
        self.assertEqual(p.month, 5)
        self.assertEqual(p.status, PayrollStatus.OPEN)

    def test_str(self):
        p = make_period(year=1403, month=7)
        self.assertEqual(str(p), '1403/07')

    def test_display_name_correct(self):
        p = make_period(year=1404, month=2)
        self.assertEqual(p.display_name, 'اردیبهشت 1404')

    def test_display_name_all_12_months(self):
        for m in range(1, 13):
            p = PayrollPeriod(year=1400, month=m)
            self.assertIn(PERSIAN_MONTHS[m], p.display_name)

    def test_unique_together_year_month(self):
        make_period(year=1403, month=3)
        with self.assertRaises(IntegrityError):
            PayrollPeriod.objects.create(year=1403, month=3, status=PayrollStatus.OPEN)

    def test_close_sets_status_and_closed_at(self):
        p = make_period(year=1403, month=4)
        before = timezone.now()
        p.close()
        p.refresh_from_db()
        self.assertEqual(p.status, PayrollStatus.CLOSED)
        self.assertIsNotNone(p.closed_at)
        self.assertGreaterEqual(p.closed_at, before)

    def test_close_already_closed_raises(self):
        p = make_period(year=1403, month=6, status=PayrollStatus.CLOSED)
        with self.assertRaises(ValidationError):
            p.close()

    def test_close_processed_raises(self):
        p = make_period(year=1403, month=8, status=PayrollStatus.PROCESSED)
        with self.assertRaises(ValidationError):
            p.close()

    def test_get_or_create_current_returns_period(self):
        p = PayrollPeriod.get_or_create_current()
        self.assertIsInstance(p, PayrollPeriod)
        self.assertIsNotNone(p.pk)
        # year should be a plausible Jalali year (>= 1400)
        self.assertGreaterEqual(p.year, 1400)
        self.assertIn(p.month, range(1, 13))

    def test_get_or_create_current_idempotent(self):
        p1 = PayrollPeriod.get_or_create_current()
        p2 = PayrollPeriod.get_or_create_current()
        self.assertEqual(p1.pk, p2.pk)

    def test_gregorian_to_jalali_known_date(self):
        jy, jm, jd = _gregorian_to_jalali(2025, 3, 21)
        self.assertEqual((jy, jm, jd), (1404, 1, 1))


# ---------------------------------------------------------------------------
# PayrollTypeConfig model tests
# ---------------------------------------------------------------------------

class PayrollTypeConfigModelTest(TestCase):

    def test_auto_created_on_employee_creation(self):
        emp = make_employee(national_id='1111111111')
        self.assertTrue(PayrollTypeConfig.objects.filter(employee=emp).exists())

    def test_auto_created_with_both_flags_false(self):
        emp = make_employee(national_id='2222222222')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        self.assertFalse(cfg.has_monthly_wage)
        self.assertFalse(cfg.has_commission)

    def test_clean_blocks_both_false_on_update(self):
        emp = make_employee(national_id='3333333333')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        cfg.has_monthly_wage = False
        cfg.has_commission   = False
        with self.assertRaises(ValidationError):
            cfg.full_clean()

    def test_clean_allows_monthly_wage_only(self):
        emp = make_employee(national_id='4444444444')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        cfg.has_monthly_wage = True
        cfg.has_commission   = False
        cfg.full_clean()  # should not raise

    def test_clean_allows_commission_only(self):
        emp = make_employee(national_id='5555555555')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        cfg.has_monthly_wage = False
        cfg.has_commission   = True
        cfg.full_clean()  # should not raise

    def test_patch_has_monthly_wage_true(self):
        emp = make_employee(national_id='6666666666')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        cfg.has_monthly_wage = True
        cfg.save()
        cfg.refresh_from_db()
        self.assertTrue(cfg.has_monthly_wage)

    def test_onetoone_second_config_raises(self):
        emp = make_employee(national_id='7777777777')
        with self.assertRaises(IntegrityError):
            PayrollTypeConfig.objects.create(employee=emp)

    def test_str(self):
        emp = make_employee(national_id='8888888888', full_name='مریم احمدی')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        self.assertIn('مریم احمدی', str(cfg))


# ---------------------------------------------------------------------------
# PayrollTypeSummary label tests
# ---------------------------------------------------------------------------

class PayrollTypeSummaryLabelTest(TestCase):

    def _make_config(self, monthly, commission):
        emp = make_employee(
            national_id=f'9{monthly}{commission}0000000'[:10],
            full_name='تست کارمند',
        )
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        cfg.has_monthly_wage = monthly
        cfg.has_commission   = commission
        cfg.save()
        return cfg

    def test_label_monthly_only(self):
        from payroll.serializers import PayrollTypeSummarySerializer
        cfg = self._make_config(True, False)
        data = PayrollTypeSummarySerializer(cfg).data
        self.assertEqual(data['payroll_type_label'], 'ثابت')

    def test_label_commission_only(self):
        from payroll.serializers import PayrollTypeSummarySerializer
        cfg = self._make_config(False, True)
        data = PayrollTypeSummarySerializer(cfg).data
        self.assertEqual(data['payroll_type_label'], 'کمیسیونی')

    def test_label_both(self):
        from payroll.serializers import PayrollTypeSummarySerializer
        cfg = self._make_config(True, True)
        data = PayrollTypeSummarySerializer(cfg).data
        self.assertEqual(data['payroll_type_label'], 'ثابت + کمیسیون')

    def test_label_neither(self):
        from payroll.serializers import PayrollTypeSummarySerializer
        emp = make_employee(national_id='0099887766')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        data = PayrollTypeSummarySerializer(cfg).data
        self.assertEqual(data['payroll_type_label'], 'تنظیم نشده')


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class PayrollPeriodAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('paytest', 'p@test.com', 'pass')
        self.client.force_authenticate(user=self.user)

    def test_list_periods(self):
        make_period(1403, 1)
        make_period(1403, 2)
        res = self.client.get(PERIODS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.data['count'], 2)

    def test_filter_by_status_open(self):
        make_period(1403, 9, status=PayrollStatus.OPEN)
        make_period(1403, 10, status=PayrollStatus.CLOSED)
        res = self.client.get(PERIODS_URL, {'status': 'OPEN'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for item in res.data['results']:
            self.assertEqual(item['status'], 'OPEN')

    def test_close_action_success(self):
        p = make_period(1403, 11)
        res = self.client.post(f'{PERIODS_URL}{p.pk}/close/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], PayrollStatus.CLOSED)

    def test_close_already_closed_returns_400(self):
        p = make_period(1403, 12, status=PayrollStatus.CLOSED)
        res = self.client.post(f'{PERIODS_URL}{p.pk}/close/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(PERIODS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PayrollTypeConfigAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('cfgtest', 'c@test.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.emp = make_employee(national_id='0123456789')
        self.cfg = PayrollTypeConfig.objects.get(employee=self.emp)

    def test_list_configs(self):
        res = self.client.get(CONFIGS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_by_employee_returns_correct_config(self):
        res = self.client.get(f'{CONFIGS_URL}by_employee/', {'employee': self.emp.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['employee'], self.emp.pk)

    def test_patch_has_monthly_wage(self):
        res = self.client.patch(
            f'{CONFIGS_URL}{self.cfg.pk}/',
            {'has_monthly_wage': True},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['has_monthly_wage'])

    def test_post_create_not_allowed(self):
        res = self.client.post(CONFIGS_URL, {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_not_allowed(self):
        res = self.client.delete(f'{CONFIGS_URL}{self.cfg.pk}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(CONFIGS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
