"""Regression tests for: an active Employee correctly configured for a
payroll type (PayrollTypeConfig flag set) was missing entirely from
/admin/payroll/payroll-page/ whenever they had no actual transaction row
yet for the selected period — e.g. an hourly employee with an HourlyRate
but zero HourlyWorkEntry rows (exact reproduction: Employee ID 9).

Root cause: PayrollReportView derived its employee list purely from the
union of employees appearing in the wage/commission/hourly *totals*
dictionaries (an inner join on activity) instead of from
PayrollTypeConfig-eligible employees left-joined with those totals — so a
correctly-configured employee with nothing accrued yet was silently
dropped even though the form save flow itself synced PayrollTypeConfig
correctly.

Covers:
  - Employee form save -> PayrollTypeConfig.has_hourly_wage sync (already
    correct — locked in end-to-end via a real admin POST, not just a
    direct service call)
  - a configured hourly employee with zero HourlyWorkEntry rows appears
    with hourly_salary=0 / total_hours_worked=0
  - a configured commission employee with zero CommissionTransaction rows
    appears with zero commission
  - adding work entries later updates the same row, not a second one
  - inactive employees remain excluded
  - employees whose rate starts after the selected period remain excluded
  - employees whose rate starts during the selected period are included
  - no date filter includes a configured employee regardless of a
    future-dated rate (the exact real-world shape of Employee ID 9)
  - existing monthly/commission-with-activity and combined-type rows are
    unaffected
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from employees.admin import EmployeeAdmin, EmployeeAdminForm
from employees.models import Employee, JobPosition
from payroll.models import (
    CommissionRule,
    CommissionTransaction,
    HourlyRate,
    HourlyWorkEntry,
    MonthlyWage,
    PayrollTypeConfig,
)
from payroll.services import finalize_hourly_payroll
from payroll.models import PayrollPeriod, PayrollStatus, _gregorian_to_jalali, _jalali_to_gregorian
from surgeries.models import Patient, SurgeryHistory, SurgeryType

User = get_user_model()
REPORT_URL = '/api/v2/payroll/report/'

_counter = [0]


def make_position(name=None):
    _counter[0] += 1
    return JobPosition.objects.create(name=name or f'موقعیت-صفر-{_counter[0]}')


def make_employee(position=None, **kwargs):
    _counter[0] += 1
    defaults = {
        'full_name': f'کارمند صفر {_counter[0]}',
        'national_id': f'4{_counter[0]:09d}',
        'gender': 'male',
        'job_position': position or make_position(),
        'start_date': datetime.date(2024, 1, 1),
        'personal_phone': f'095{_counter[0]:08d}',
        'emergency_contact_phone': f'096{_counter[0]:08d}',
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_hourly_rate(employee, rate=Decimal('500000'), start=datetime.date(2020, 1, 1), end=None):
    return HourlyRate.objects.create(employee=employee, rate=rate, start_date=start, end_date=end)


def _current_jalali_period():
    today = datetime.date.today()
    jy, jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
    period, _ = PayrollPeriod.objects.get_or_create(
        year=jy, month=jm, defaults={'status': PayrollStatus.OPEN},
    )
    gy, gm, gd = _jalali_to_gregorian(jy, jm, 1)
    return period, jy, jm, datetime.date(gy, gm, gd)


class EmployeeHourlyFormSyncEndToEndTest(TestCase):
    """Locks in that a real admin POST (not just a direct service call)
    correctly syncs PayrollTypeConfig.has_hourly_wage — this was already
    working, but the task explicitly asked for coverage of it."""

    def setUp(self):
        self.admin = User.objects.create_superuser('zero_incl_admin', password='pass')
        self.client.force_login(self.admin)
        self.position = make_position()

    def test_admin_post_with_hourly_wage_type_syncs_payroll_type_config(self):
        data = {
            'full_name': 'کارمند فرم ساعتی صفر',
            'national_id': '5551112223',
            'gender': 'male',
            'job_position': self.position.pk,
            'start_date': '2024-01-01',
            'personal_phone': '09121112233',
            'emergency_contact_phone': '09121112244',
            'wage_type': 'hourly',
            'hourly_rate_amount': '400000',
            'documents-TOTAL_FORMS': '0',
            'documents-INITIAL_FORMS': '0',
            'documents-MIN_NUM_FORMS': '0',
            'documents-MAX_NUM_FORMS': '1000',
        }
        resp = self.client.post('/admin/employees/employee/add/', data)
        self.assertEqual(resp.status_code, 302, getattr(resp, 'context', None) and resp.context['errors'])

        emp = Employee.objects.get(national_id='5551112223')
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        self.assertTrue(cfg.has_hourly_wage)
        self.assertTrue(HourlyRate.objects.filter(employee=emp, is_active=True, rate=Decimal('400000')).exists())

    def test_form_does_not_only_update_legacy_hourly_rate_field(self):
        """Saving wage_type='hourly' must go through the new HourlyRate
        system, not silently write only the legacy Employee.hourly_rate
        field (which no report/finalization code reads)."""
        form = EmployeeAdminForm(data={
            'full_name': 'کارمند قدیمی نبودن',
            'national_id': '5551112225',
            'gender': 'male',
            'job_position': self.position.pk,
            'start_date': '2024-01-01',
            'personal_phone': '09121112255',
            'emergency_contact_phone': '09121112266',
            'wage_type': 'hourly',
            'hourly_rate_amount': '300000',
        })
        self.assertTrue(form.is_valid(), form.errors)
        emp = form.save()

        from django.test import RequestFactory
        from django.contrib.admin.sites import AdminSite
        request = RequestFactory().post('/')
        request.user = self.admin
        EmployeeAdmin(Employee, AdminSite())._save_payroll(request, emp, form)

        self.assertIsNone(emp.hourly_rate)  # legacy field untouched
        self.assertTrue(HourlyRate.objects.filter(employee=emp, is_active=True).exists())


class ConfiguredZeroHourEmployeeInclusionTest(TestCase):
    """Exact reproduction of the Employee ID 9 bug."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='zero_incl_api', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

    def test_hourly_employee_with_no_work_entries_appears_with_zero_values(self):
        emp = make_employee()
        make_hourly_rate(emp)  # active HourlyRate, zero HourlyWorkEntry rows
        self.assertTrue(PayrollTypeConfig.objects.get(employee=emp).has_hourly_wage)
        self.assertEqual(HourlyWorkEntry.objects.filter(employee=emp).count(), 0)

        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = resp.data['employees']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('0'))

    def test_no_date_filter_includes_employee_despite_future_dated_rate(self):
        """The exact real-world shape of Employee ID 9: HourlyRate starting
        months in the future, viewed with no period filter at all."""
        emp = make_employee()
        make_hourly_rate(emp, start=datetime.date(2027, 1, 12))

        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        ids = [r['employee_id'] for r in resp.data['employees']]
        self.assertIn(emp.pk, ids)

    def test_commission_configured_employee_with_no_transactions_appears_zero(self):
        position = make_position()
        emp = make_employee(position=position)
        surgery_type = SurgeryType.objects.create(
            name='عمل-صفر', code='zero_comm_type', base_rate=Decimal('0'),
        )
        CommissionRule.objects.create(
            job_position=position, surgery_type=surgery_type, commission_percent=Decimal('10.00'),
        )
        self.assertTrue(PayrollTypeConfig.objects.get(employee=emp).has_commission)
        self.assertEqual(CommissionTransaction.objects.filter(employee=emp).count(), 0)

        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        rows = resp.data['employees']
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(str(rows[0]['total_commission'])), Decimal('0'))

    def test_adding_work_entries_updates_same_row_not_a_second_row(self):
        emp = make_employee()
        make_hourly_rate(emp, rate=Decimal('500000'))
        period, jy, jm, month_start = _current_jalali_period()

        resp_before = self.client.get(REPORT_URL, {'employee': emp.pk, 'year': jy, 'month': jm})
        rows_before = resp_before.data['employees']
        self.assertEqual(len(rows_before), 1)
        self.assertEqual(Decimal(str(rows_before[0]['hourly_salary'])), Decimal('0'))

        HourlyWorkEntry.objects.create(employee=emp, work_date=month_start, hours_worked=Decimal('6'))
        finalize_hourly_payroll(emp, period)

        resp_after = self.client.get(REPORT_URL, {'employee': emp.pk, 'year': jy, 'month': jm})
        rows_after = resp_after.data['employees']
        self.assertEqual(len(rows_after), 1)  # still one row, not two
        self.assertEqual(Decimal(str(rows_after[0]['hourly_salary'])), Decimal('3000000'))
        self.assertEqual(Decimal(str(rows_after[0]['total_hours_worked'])), Decimal('6'))

    def test_inactive_employee_remains_excluded(self):
        emp = make_employee(is_active=False)
        make_hourly_rate(emp)
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        ids = [r['employee_id'] for r in resp.data['employees']]
        self.assertNotIn(emp.pk, ids)

    def test_employee_starting_after_period_end_excluded(self):
        emp = make_employee()
        make_hourly_rate(emp, start=datetime.date(2030, 3, 1))
        resp = self.client.get(REPORT_URL, {
            'start_date': '2030-01-01', 'end_date': '2030-01-31',
        })
        ids = [r['employee_id'] for r in resp.data['employees']]
        self.assertNotIn(emp.pk, ids)

    def test_employee_starting_during_period_included(self):
        emp = make_employee()
        make_hourly_rate(emp, start=datetime.date(2030, 1, 15))
        resp = self.client.get(REPORT_URL, {
            'start_date': '2030-01-01', 'end_date': '2030-01-31',
        })
        ids = [r['employee_id'] for r in resp.data['employees']]
        self.assertIn(emp.pk, ids)

    def test_employee_ending_before_period_start_excluded(self):
        emp = make_employee()
        make_hourly_rate(
            emp, start=datetime.date(2029, 1, 1), end=datetime.date(2029, 6, 30),
        )
        resp = self.client.get(REPORT_URL, {
            'start_date': '2030-01-01', 'end_date': '2030-01-31',
        })
        ids = [r['employee_id'] for r in resp.data['employees']]
        self.assertNotIn(emp.pk, ids)


class ExistingPayrollBehaviorUnaffectedTest(TestCase):
    """Combined-type and activity-based rows already worked correctly —
    confirm the left-join change doesn't alter their computed values."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='zero_incl_combo', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

    def test_monthly_only_employee_with_wage_still_shown_correctly(self):
        emp = make_employee()
        MonthlyWage.objects.create(employee=emp, amount=Decimal('3000000'), start_date=datetime.date(2024, 1, 1))
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('3000000'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('3000000'))

    def test_monthly_plus_hourly_with_zero_hours_this_period(self):
        emp = make_employee()
        MonthlyWage.objects.create(employee=emp, amount=Decimal('2000000'), start_date=datetime.date(2024, 1, 1))
        make_hourly_rate(emp)  # configured, but no work entries at all
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        rows = resp.data['employees']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('2000000'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('2000000'))

    def test_unconfigured_employee_still_absent(self):
        emp = make_employee()  # no PayrollTypeConfig flags set at all
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        ids = [r['employee_id'] for r in resp.data['employees']]
        self.assertNotIn(emp.pk, ids)
