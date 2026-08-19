"""Regression tests for the Employee-form / Employee-detail hourly-rate
mismatch (Employee ID 9): the edit form pre-fills from the canonical
payroll.HourlyRate, but the detail page's payroll tab was reading the
archived Employee.hourly_rate column via EmployeeSerializer — so an
employee with only a HourlyRate (no legacy value) showed "تنظیم نشده" on
the detail page while the edit form correctly showed the real rate.

Covers:
  - saving the hourly rate from the Employee admin form creates a
    canonical HourlyRate, and the employee detail API reflects that same
    rate (current_hourly_rate) — not the legacy column
  - a HourlyRate whose start_date is in the future is exposed as
    future_hourly_rate, never as current_hourly_rate
  - deactivating a rate before creating a new one preserves the old row
    (history), it is not deleted or edited in place
  - the archived Employee.hourly_rate column is exposed separately
    (legacy_hourly_rate) and is never used to compute current/future rate
"""
import datetime
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.test import Client
from rest_framework.test import APIClient

from employees.admin import EmployeeAdmin, EmployeeAdminForm
from employees.models import Employee, JobPosition
from employees.serializers import EmployeeSerializer
from payroll.models import HourlyRate, PayrollTypeConfig

User = get_user_model()

_counter = [0]


def make_position():
    _counter[0] += 1
    return JobPosition.objects.create(name=f'موقعیت-نرخ-ساعتی-{_counter[0]}')


def make_employee(**kwargs):
    _counter[0] += 1
    defaults = dict(
        full_name=f'کارمند نرخ ساعتی {_counter[0]}',
        national_id=f'4{_counter[0]:09d}',
        gender='male',
        job_position=make_position(),
        start_date=datetime.date(2024, 1, 1),
        personal_phone=f'095{_counter[0]:08d}',
        emergency_contact_phone=f'096{_counter[0]:08d}',
    )
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


class EmployeeFormSavesCanonicalHourlyRateTest(TestCase):
    """Reproduces the exact save flow used by the Employee admin form."""

    def setUp(self):
        self.user = User.objects.create_superuser('hr_disp_admin', password='pass')
        self.admin_obj = EmployeeAdmin(Employee, AdminSite())

    def _save_via_form(self, employee=None, rate='33', start_date='2024-01-01', **overrides):
        position = make_position()
        data = {
            'full_name': 'کارمند تست نرخ ساعتی',
            'national_id': '7766554433',
            'gender': 'male',
            'job_position': position.pk,
            'start_date': '2024-01-01',
            'personal_phone': '09131112233',
            'emergency_contact_phone': '09131112244',
            'wage_type': 'hourly',
            'hourly_rate_amount': rate,
            'wage_start_date': start_date,
        }
        data.update(overrides)
        form = EmployeeAdminForm(data=data, instance=employee)
        self.assertTrue(form.is_valid(), form.errors)
        emp = form.save()
        request = RequestFactory().post('/')
        request.user = self.user
        self.admin_obj._save_payroll(request, emp, form)
        return emp

    def test_saving_hourly_rate_creates_canonical_hourly_rate_row(self):
        emp = self._save_via_form(rate='33')
        rate = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(rate.rate, Decimal('33'))
        self.assertTrue(PayrollTypeConfig.objects.get(employee=emp).has_hourly_wage)

    def test_detail_api_reflects_same_rate_the_form_saved(self):
        emp = self._save_via_form(rate='33', start_date='2024-01-01')

        api_client = APIClient()
        api_client.force_authenticate(user=self.user)
        resp = api_client.get(f'/api/v2/employees/{emp.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.data['current_hourly_rate']), Decimal('33'))
        self.assertEqual(str(resp.data['current_hourly_rate_start_date']), '2024-01-01')

    def test_future_start_date_is_exposed_as_future_not_current(self):
        """The exact Employee-9 scenario: a HourlyRate exists but its
        start_date is after today, so it must never render as the current
        rate — only as a distinct future rate."""
        emp = self._save_via_form(rate='33', start_date='2027-01-12')

        api_client = APIClient()
        api_client.force_authenticate(user=self.user)
        resp = api_client.get(f'/api/v2/employees/{emp.pk}/')
        self.assertIsNone(resp.data['current_hourly_rate'])
        self.assertEqual(Decimal(resp.data['future_hourly_rate']), Decimal('33'))
        self.assertEqual(str(resp.data['future_hourly_rate_start_date']), '2027-01-12')

    def test_changing_rate_preserves_previous_rate_as_history(self):
        emp = self._save_via_form(rate='33', start_date='2024-01-01')
        first = HourlyRate.objects.get(employee=emp, is_active=True)

        self._save_via_form(employee=emp, rate='55', start_date='2025-01-01')

        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(first.end_date, datetime.date(2025, 1, 1))
        self.assertEqual(first.rate, Decimal('33'))  # never edited in place

        current = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(current.rate, Decimal('55'))
        self.assertEqual(HourlyRate.objects.filter(employee=emp).count(), 2)


class LegacyHourlyRateNotCanonicalTest(TestCase):
    """The archived Employee.hourly_rate column must never be used to
    compute current/future hourly rate, even when it's populated."""

    def setUp(self):
        self.user = User.objects.create_superuser('hr_legacy_admin', password='pass')

    def test_legacy_value_without_hourly_rate_row_is_not_current(self):
        emp = make_employee(hourly_rate=Decimal('999999'))

        api_client = APIClient()
        api_client.force_authenticate(user=self.user)
        resp = api_client.get(f'/api/v2/employees/{emp.pk}/')
        self.assertEqual(Decimal(resp.data['legacy_hourly_rate']), Decimal('999999'))
        self.assertIsNone(resp.data['current_hourly_rate'])
        self.assertIsNone(resp.data['future_hourly_rate'])

    def test_no_hourly_data_at_all_is_none_everywhere(self):
        emp = make_employee()
        serializer = EmployeeSerializer(emp)
        data = serializer.data
        self.assertIsNone(data['legacy_hourly_rate'])
        self.assertIsNone(data['current_hourly_rate'])
        self.assertIsNone(data['future_hourly_rate'])


class EmployeeDetailPageRendersWithoutErrorTest(TestCase):
    """The read-only admin detail tab (template) must still load — the JS
    reads the new API fields, but the server-rendered shell is unchanged."""

    def setUp(self):
        self.admin = User.objects.create_superuser('hr_page_admin', password='pass')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_detail_page_loads(self):
        emp = make_employee()
        HourlyRate.objects.create(
            employee=emp, rate=Decimal('33'), start_date=datetime.date(2027, 1, 12), is_active=True,
        )
        resp = self.client.get(f'/admin/employees/employee/{emp.pk}/detail/')
        self.assertEqual(resp.status_code, 200)
