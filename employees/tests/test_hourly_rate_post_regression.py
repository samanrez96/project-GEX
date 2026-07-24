"""End-to-end regression tests for the Employee hourly-payroll persistence
bug, driven through the real admin HTTP POST endpoint (not the service layer
directly), per the follow-up investigation into Employee ID 9.

Live DB inspection at the start of this investigation showed the canonical
HourlyRate the previous fix creates is in fact correct and current:

    HourlyRate(id=4, employee_id=9, rate=33.00, start_date=2026-07-11,
               end_date=None, is_active=True)
    HourlyRate(id=1, employee_id=9, rate=33.00, start_date=2027-01-12,
               end_date=2027-01-12, is_active=False)   # superseded, preserved
    PayrollTypeConfig(employee_id=9, has_hourly_wage=True)
    employee.hourly_rate (legacy) = None

EmployeeSerializer(employee).data confirmed current_hourly_rate='33.00',
current_hourly_rate_start_date='2026-07-11' — i.e. the canonical read path
already returns the correct value for Employee 9. These tests exist to
prove that result generalizes (not just true by accident for one row) by
exercising the actual admin POST endpoint end-to-end, and to lock in the
explicit transaction.atomic() wrapping added around
EmployeeAdmin.save_model() so a payroll-sync failure can never leave a
saved Employee behind.
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from employees.models import Employee, JobPosition
from payroll.models import HourlyRate, PayrollTypeConfig

User = get_user_model()

_counter = [0]


def make_position():
    _counter[0] += 1
    return JobPosition.objects.create(name=f'موقعیت-پیگیری-پرداخت-{_counter[0]}')


def _base_post_data(position_pk, **overrides):
    _counter[0] += 1
    data = {
        'full_name':               'کارمند تست پیگیری حقوق ساعتی',
        'national_id':              f'8{_counter[0]:09d}',
        'gender':                  'male',
        'job_position':            position_pk,
        'start_date':              '2024-01-01',
        'is_active':               'on',
        'email':                   '',
        'personal_phone':          f'091{_counter[0]:08d}',
        'emergency_contact_phone': f'092{_counter[0]:08d}',
        'address':                 '',
        'hourly_rate':             '',   # legacy field — left blank on purpose
        'description':             '',
        'wage_type':               'hourly',
        'monthly_amount':          '',
        'hourly_rate_amount':      '33',
        'wage_start_date':         '2027-01-12',
        'documents-TOTAL_FORMS':   '1',
        'documents-INITIAL_FORMS': '0',
        'documents-MIN_NUM_FORMS': '0',
        'documents-MAX_NUM_FORMS': '1000',
        'documents-0-file':        '',
    }
    data.update(overrides)
    return data


class AdminPostCreatesCanonicalHourlyRateTest(TestCase):
    """Bullets 1-5, 12: the actual admin POST creates PayrollTypeConfig and
    a canonical HourlyRate belonging to the right employee, with the
    submitted rate/date, and never leaves overlapping active rows."""

    def setUp(self):
        self.admin = User.objects.create_superuser('hr_post_admin', password='pass')
        self.client = Client()
        self.client.force_login(self.admin)
        self.position = make_position()

    def test_post_creates_payroll_type_config_with_hourly_wage_true(self):
        resp = self.client.post('/admin/employees/employee/add/', _base_post_data(self.position.pk))
        self.assertEqual(resp.status_code, 302, getattr(resp, 'context', None))
        emp = Employee.objects.latest('id')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        self.assertTrue(cfg.has_hourly_wage)

    def test_post_creates_hourly_rate_belonging_to_the_right_employee(self):
        resp = self.client.post('/admin/employees/employee/add/', _base_post_data(self.position.pk))
        self.assertEqual(resp.status_code, 302, getattr(resp, 'context', None))
        emp = Employee.objects.latest('id')
        rate = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(rate.employee_id, emp.pk)

    def test_rate_value_persists(self):
        resp = self.client.post(
            '/admin/employees/employee/add/',
            _base_post_data(self.position.pk, hourly_rate_amount='33'),
        )
        self.assertEqual(resp.status_code, 302)
        emp = Employee.objects.latest('id')
        rate = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(rate.rate, Decimal('33'))

    def test_start_date_persists(self):
        resp = self.client.post(
            '/admin/employees/employee/add/',
            _base_post_data(self.position.pk, wage_start_date='2027-01-12'),
        )
        self.assertEqual(resp.status_code, 302)
        emp = Employee.objects.latest('id')
        rate = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(rate.start_date, datetime.date(2027, 1, 12))

    def test_changing_only_start_date_synchronizes_a_new_rate(self):
        resp = self.client.post('/admin/employees/employee/add/', _base_post_data(self.position.pk))
        self.assertEqual(resp.status_code, 302)
        emp = Employee.objects.latest('id')
        original = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(original.start_date, datetime.date(2027, 1, 12))

        resp2 = self.client.post(
            f'/admin/employees/employee/{emp.pk}/change/',
            _base_post_data(self.position.pk, national_id=emp.national_id, wage_start_date='2026-07-11'),
        )
        self.assertEqual(resp2.status_code, 302, getattr(resp2, 'context', None))

        active = HourlyRate.objects.filter(employee=emp, is_active=True)
        self.assertEqual(active.count(), 1, 'no overlapping active rows')
        current = active.get()
        self.assertEqual(current.rate, Decimal('33'))
        self.assertEqual(current.start_date, datetime.date(2026, 7, 11))

        original.refresh_from_db()
        self.assertFalse(original.is_active)
        self.assertGreaterEqual(original.end_date, original.start_date)  # never inverted
        self.assertEqual(HourlyRate.objects.filter(employee=emp).count(), 2)


class ReloadedFormAndDetailShowPersistedValuesTest(TestCase):
    """Bullets 7-8: after saving, both the reloaded change form and the
    (JSON) data backing the detail page must show the same persisted rate
    and date — reloaded from the database, not the in-memory form."""

    def setUp(self):
        self.admin = User.objects.create_superuser('hr_reload_admin', password='pass')
        self.client = Client()
        self.client.force_login(self.admin)
        self.position = make_position()

    def test_reloaded_change_form_shows_persisted_values(self):
        add_resp = self.client.post(
            '/admin/employees/employee/add/',
            _base_post_data(self.position.pk, wage_start_date='2026-07-11'),
        )
        self.assertEqual(add_resp.status_code, 302)
        emp = Employee.objects.latest('id')

        reload_resp = self.client.get(f'/admin/employees/employee/{emp.pk}/change/')
        self.assertEqual(reload_resp.status_code, 200)
        form = reload_resp.context['adminform'].form
        self.assertEqual(form.initial.get('wage_start_date'), datetime.date(2026, 7, 11))
        self.assertEqual(form.initial.get('hourly_rate_amount'), Decimal('33'))
        self.assertEqual(form.initial.get('wage_type'), 'hourly')

    def test_employee_detail_data_shows_the_same_rate_as_the_reloaded_form(self):
        from rest_framework.test import APIClient

        add_resp = self.client.post(
            '/admin/employees/employee/add/',
            _base_post_data(self.position.pk, wage_start_date='2026-07-11'),
        )
        self.assertEqual(add_resp.status_code, 302)
        emp = Employee.objects.latest('id')

        api_client = APIClient()
        api_client.force_authenticate(user=self.admin)
        resp = api_client.get(f'/api/v1/employees/{emp.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.data['current_hourly_rate'])
        self.assertEqual(Decimal(resp.data['current_hourly_rate']), Decimal('33'))
        self.assertEqual(str(resp.data['current_hourly_rate_start_date']), '2026-07-11')
        self.assertNotEqual(resp.data['current_hourly_rate'], 'تنظیم نشده')

    def test_legacy_employee_hourly_rate_field_not_used_by_detail_data(self):
        """Even if the archived column somehow had a value, the detail
        payload's canonical fields must come from HourlyRate alone."""
        from rest_framework.test import APIClient

        add_resp = self.client.post(
            '/admin/employees/employee/add/',
            _base_post_data(self.position.pk, wage_start_date='2026-07-11'),
        )
        self.assertEqual(add_resp.status_code, 302)
        emp = Employee.objects.latest('id')
        emp.hourly_rate = Decimal('999999')
        emp.save(update_fields=['hourly_rate'])

        api_client = APIClient()
        api_client.force_authenticate(user=self.admin)
        resp = api_client.get(f'/api/v1/employees/{emp.pk}/')
        self.assertEqual(Decimal(resp.data['current_hourly_rate']), Decimal('33'))
        self.assertEqual(Decimal(resp.data['legacy_hourly_rate']), Decimal('999999'))


class InvalidJalaliInputReturnsFormErrorTest(TestCase):
    """Bullet 9: invalid Jalali dates must never silently keep the old date
    — they must fail as a normal Persian form validation error, and the
    POST must not redirect (no 302) since nothing was saved."""

    def setUp(self):
        self.admin = User.objects.create_superuser('hr_invalid_admin', password='pass')
        self.client = Client()
        self.client.force_login(self.admin)
        self.position = make_position()

    def test_invalid_date_does_not_redirect_and_shows_persian_error(self):
        resp = self.client.post(
            '/admin/employees/employee/add/',
            _base_post_data(self.position.pk, wage_start_date='1405/13/40'),
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a redirect
        form = resp.context['adminform'].form
        self.assertFalse(form.is_valid())
        self.assertIn('wage_start_date', form.errors)
        error_text = ' '.join(form.errors['wage_start_date'])
        self.assertTrue(any('؀' <= ch <= 'ۿ' for ch in error_text), error_text)
        self.assertEqual(Employee.objects.count(), 0)
        self.assertEqual(HourlyRate.objects.count(), 0)


class HourlySyncFailureDoesNotSilentlySucceedTest(TestCase):
    """Bullet 10: if HourlyRate synchronization itself raises, the Employee
    save must not be treated as successful — no redirect, and (thanks to
    the explicit transaction.atomic() around save_model()) no partially
    saved Employee left behind either."""

    def setUp(self):
        self.admin = User.objects.create_superuser('hr_sync_fail_admin', password='pass')
        self.client = Client()
        self.client.force_login(self.admin)
        self.client.raise_request_exception = False
        self.position = make_position()

    def test_hourly_rate_creation_failure_prevents_employee_from_being_left_saved(self):
        post_data = _base_post_data(self.position.pk)
        with patch('payroll.models.HourlyRate.objects.create', side_effect=RuntimeError('simulated db failure')):
            resp = self.client.post('/admin/employees/employee/add/', post_data)

        self.assertEqual(resp.status_code, 500)
        self.assertFalse(
            Employee.objects.filter(national_id=post_data['national_id']).exists(),
            'the Employee row must be rolled back along with the failed payroll sync',
        )
