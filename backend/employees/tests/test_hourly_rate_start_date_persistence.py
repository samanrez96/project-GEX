"""Regression tests for the Employee hourly-payroll start-date field not
being persisted (Employee ID 9): EmployeeAdmin._save_hourly_rate() skipped
creating a new canonical HourlyRate whenever the submitted rate matched the
existing active row's rate — even if the submitted start date ("تاریخ شروع
حقوق") was different. So editing only the date, saving, and reloading the
form kept showing the old date; the hourly rate value alone was compared,
the date never was.

Root cause was in employees/admin.py EmployeeAdmin._save_hourly_rate():

    existing = HourlyRate.objects.filter(employee=obj, is_active=True).first()
    if existing and existing.rate == Decimal(str(hourly_rate_amount)):
        return   # <- returned even when only wage_start_date changed

A second, related bug in the same method: when closing the previous active
row, `old.end_date = wage_start` was set unconditionally — if the corrected
start date is *earlier* than the old row's own start date (exactly what
happens when fixing a mistakenly future-dated rate), this produced an
invalid end_date < start_date row.

Covers:
  - changing only the start date (same rate) creates a new HourlyRate and
    deactivates the old one, with a valid (non-inverted) end_date
  - the rate value survives across a date-only correction
  - Persian-digit Jalali input for wage_start_date parses to the same date
    as the equivalent Latin-digit/ISO input
  - an invalid date string raises a Persian form validation error and
    performs no save
  - no two active HourlyRate rows ever coexist after a correction
  - the change-form GET (reload) reflects the new date via the same
    canonical get_current_and_future() helper as the detail page
  - the Employee detail API and the change-form prefill agree
"""
import datetime
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from rest_framework.test import APIClient

from employees.admin import EmployeeAdmin, EmployeeAdminForm
from employees.models import Employee, JobPosition
from payroll.models import HourlyRate, _jalali_to_gregorian

User = get_user_model()

_counter = [0]


def make_position():
    _counter[0] += 1
    return JobPosition.objects.create(name=f'موقعیت-شروع-حقوق-{_counter[0]}')


def _base_post_data(position_pk, **overrides):
    _counter[0] += 1
    data = {
        'full_name':               'کارمند تست تاریخ شروع حقوق',
        'national_id':              f'6{_counter[0]:09d}',
        'gender':                  'male',
        'job_position':            position_pk,
        'start_date':              '2024-01-01',
        'is_active':               'on',
        'email':                   '',
        'personal_phone':          f'097{_counter[0]:08d}',
        'emergency_contact_phone': f'098{_counter[0]:08d}',
        'address':                 '',
        'hourly_rate':             '',
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


class HourlyStartDateOnlyChangeAdminHttpTest(TestCase):
    """End-to-end reproduction through the real admin HTTP views — closest
    match to the reported steps (edit the field on the change page, save,
    reload)."""

    def setUp(self):
        self.admin = User.objects.create_superuser('hr_start_admin', password='pass')
        self.client = Client()
        self.client.force_login(self.admin)
        self.position = make_position()

    def test_editing_only_start_date_persists_after_reload(self):
        add_resp = self.client.post(
            '/admin/employees/employee/add/',
            _base_post_data(self.position.pk, wage_start_date='2027-01-12'),
        )
        self.assertEqual(add_resp.status_code, 302, getattr(add_resp, 'context', None))
        emp = Employee.objects.latest('id')

        rate = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(rate.rate, Decimal('33'))
        self.assertEqual(rate.start_date, datetime.date(2027, 1, 12))

        # Same rate (33), only the date changes — this is the exact reported case.
        change_resp = self.client.post(
            f'/admin/employees/employee/{emp.pk}/change/',
            _base_post_data(
                self.position.pk,
                national_id=emp.national_id,
                wage_start_date='2026-06-22',   # == 1405/04/01
            ),
        )
        self.assertEqual(change_resp.status_code, 302, getattr(change_resp, 'context', None))

        active_rates = HourlyRate.objects.filter(employee=emp, is_active=True)
        self.assertEqual(active_rates.count(), 1, 'must never leave two active rates')
        current = active_rates.get()
        self.assertEqual(current.rate, Decimal('33'))
        self.assertEqual(current.start_date, datetime.date(2026, 6, 22))

        # The old (wrongly future-dated) row must be preserved, deactivated,
        # and not corrupted into an end_date before its own start_date.
        old = HourlyRate.objects.get(employee=emp, is_active=False)
        self.assertEqual(old.start_date, datetime.date(2027, 1, 12))
        self.assertEqual(old.rate, Decimal('33'))
        self.assertGreaterEqual(old.end_date, old.start_date)

        # Reload the change form (GET) — must show the corrected date, not
        # the original one.
        reload_resp = self.client.get(f'/admin/employees/employee/{emp.pk}/change/')
        self.assertEqual(reload_resp.status_code, 200)
        form = reload_resp.context['adminform'].form
        self.assertEqual(form.initial.get('wage_start_date'), datetime.date(2026, 6, 22))
        self.assertEqual(form.initial.get('hourly_rate_amount'), Decimal('33'))


class HourlyStartDateOnlyChangeDirectFormTest(TestCase):
    """Same scenario driven directly through EmployeeAdminForm/_save_payroll,
    isolating the fix from HTTP/formset plumbing."""

    def setUp(self):
        self.user = User.objects.create_superuser('hr_start_direct_admin', password='pass')
        self.admin_obj = EmployeeAdmin(Employee, AdminSite())
        self.position = make_position()

    def _form_data(self, **overrides):
        data = {
            'full_name': 'کارمند مستقیم تست تاریخ',
            'national_id': '5544332211',
            'gender': 'male',
            'job_position': self.position.pk,
            'start_date': '2024-01-01',
            'personal_phone': '09141112233',
            'emergency_contact_phone': '09141112244',
            'wage_type': 'hourly',
            'hourly_rate_amount': '33',
            'wage_start_date': '2027-01-12',
        }
        data.update(overrides)
        return data

    def _save(self, employee=None, **overrides):
        form = EmployeeAdminForm(data=self._form_data(**overrides), instance=employee)
        self.assertTrue(form.is_valid(), form.errors)
        emp = form.save()
        request = RequestFactory().post('/')
        request.user = self.user
        self.admin_obj._save_payroll(request, emp, form)
        return emp

    def test_rate_unchanged_but_date_changed_still_versions_a_new_row(self):
        emp = self._save(wage_start_date='2027-01-12')
        first = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(first.rate, Decimal('33'))

        self._save(employee=emp, wage_start_date='2026-06-22')  # same rate, earlier date

        self.assertEqual(HourlyRate.objects.filter(employee=emp).count(), 2)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertGreaterEqual(first.end_date, first.start_date)  # never inverted

        current = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(current.rate, Decimal('33'))
        self.assertEqual(current.start_date, datetime.date(2026, 6, 22))

    def test_identical_resubmission_does_not_create_a_duplicate_row(self):
        emp = self._save(wage_start_date='2027-01-12')
        self._save(employee=emp, wage_start_date='2027-01-12')  # nothing changed
        self.assertEqual(HourlyRate.objects.filter(employee=emp).count(), 1)

    def test_persian_digit_start_date_matches_latin_digit_equivalent(self):
        emp_a = self._save(wage_start_date='۱۴۰۵/۰۴/۰۱', national_id='5544332212')
        emp_b = self._save(wage_start_date='1405/04/01', national_id='5544332213')

        rate_a = HourlyRate.objects.get(employee=emp_a, is_active=True)
        rate_b = HourlyRate.objects.get(employee=emp_b, is_active=True)
        self.assertEqual(rate_a.start_date, rate_b.start_date)
        self.assertEqual(rate_a.start_date, datetime.date(*_jalali_to_gregorian(1405, 4, 1)))

    def test_invalid_jalali_date_is_a_persian_form_error_and_does_not_save(self):
        form = EmployeeAdminForm(data=self._form_data(wage_start_date='1405/13/40'))
        self.assertFalse(form.is_valid())
        self.assertIn('wage_start_date', form.errors)
        # Persian error message, not a raw traceback / English default.
        error_text = ' '.join(form.errors['wage_start_date'])
        self.assertTrue(any('؀' <= ch <= 'ۿ' for ch in error_text))
        self.assertEqual(HourlyRate.objects.count(), 0)

    def test_no_overlapping_active_rates_after_correction(self):
        emp = self._save(wage_start_date='2027-01-12')
        self._save(employee=emp, wage_start_date='2026-06-22')
        active = HourlyRate.objects.filter(employee=emp, is_active=True)
        self.assertEqual(active.count(), 1)

    def test_get_form_prefill_uses_corrected_date_after_save(self):
        emp = self._save(wage_start_date='2027-01-12')
        self._save(employee=emp, wage_start_date='2026-06-22')

        request = RequestFactory().get('/')
        request.user = self.user
        form_class = self.admin_obj.get_form(request, emp)
        form = form_class(instance=emp)
        self.assertEqual(form.initial.get('wage_start_date'), datetime.date(2026, 6, 22))
        self.assertEqual(form.initial.get('hourly_rate_amount'), Decimal('33'))

    def test_employee_detail_api_matches_change_form_after_correction(self):
        emp = self._save(wage_start_date='2027-01-12')
        self._save(employee=emp, wage_start_date='2026-06-22')

        request = RequestFactory().get('/')
        request.user = self.user
        form_class = self.admin_obj.get_form(request, emp)
        form = form_class(instance=emp)

        api_client = APIClient()
        api_client.force_authenticate(user=self.user)
        resp = api_client.get(f'/api/v1/employees/{emp.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.data['current_hourly_rate']), form.initial.get('hourly_rate_amount'))
        self.assertEqual(
            str(resp.data['current_hourly_rate_start_date']),
            form.initial.get('wage_start_date').isoformat(),
        )
