"""Tests for the hourly wage system (HourlyWorkRecord)."""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from employees.models import Employee, JobPosition
from payroll.models import HourlyWorkRecord

User = get_user_model()


def _make_position():
    pos, _ = JobPosition.objects.get_or_create(name='تکنسین')
    return pos


_emp_counter = [0]


def _make_employee(position=None, hourly_rate=None):
    if not position:
        position = _make_position()
    _emp_counter[0] += 1
    return Employee.objects.create(
        full_name=f'کارمند تست {_emp_counter[0]}',
        national_id=f'1{_emp_counter[0]:09d}',
        gender='male',
        job_position=position,
        start_date=datetime.date(2025, 1, 1),
        personal_phone=f'091{_emp_counter[0]:08d}',
        emergency_contact_phone=f'092{_emp_counter[0]:08d}',
        hourly_rate=hourly_rate,
    )


class HourlyWorkRecordModelTest(TestCase):

    def setUp(self):
        self.emp = _make_employee(hourly_rate=Decimal('500000'))

    def test_calculated_salary_on_save(self):
        """500,000 toman/hr × 160 hrs = 80,000,000 toman."""
        rec = HourlyWorkRecord.objects.create(
            employee=self.emp,
            jalali_year=1404,
            jalali_month=4,
            hours_worked=Decimal('160'),
            hourly_rate=Decimal('500000'),
            notes='',
        )
        self.assertEqual(rec.calculated_salary, Decimal('80000000'))

    def test_record_date_set_on_save(self):
        """record_date is the Gregorian first day of the Jalali month."""
        rec = HourlyWorkRecord.objects.create(
            employee=self.emp,
            jalali_year=1404,
            jalali_month=1,
            hours_worked=Decimal('160'),
            hourly_rate=Decimal('500000'),
        )
        # 1404/01/01 → 2025-03-21
        self.assertEqual(rec.record_date, datetime.date(2025, 3, 21))

    def test_unique_per_employee_month(self):
        """Two records for the same employee+month should fail."""
        HourlyWorkRecord.objects.create(
            employee=self.emp, jalali_year=1404, jalali_month=2,
            hours_worked=Decimal('160'), hourly_rate=Decimal('500000'),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            HourlyWorkRecord.objects.create(
                employee=self.emp, jalali_year=1404, jalali_month=2,
                hours_worked=Decimal('120'), hourly_rate=Decimal('500000'),
            )


class HourlyWageFinanceIntegrationTest(TestCase):
    """Hourly wage salary is included in finance employee cost."""

    def setUp(self):
        from finance.models import FinanceCategory
        self.emp = _make_employee(hourly_rate=Decimal('500000'))
        self.rec = HourlyWorkRecord.objects.create(
            employee=self.emp,
            jalali_year=1404,
            jalali_month=4,
            hours_worked=Decimal('160'),
            hourly_rate=Decimal('500000'),
        )

    def test_employee_cost_includes_hourly_salary(self):
        from finance.views import compute_finance_summary
        summary = compute_finance_summary()
        self.assertGreaterEqual(summary['total_employee_cost'], Decimal('80000000'))


class HourlyWageAdminTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('hw_admin', 'a@b.com', 'pass')
        self.client.force_login(self.superuser)
        self.emp = _make_employee(hourly_rate=Decimal('500000'))

    def test_hourly_record_admin_list_loads(self):
        resp = self.client.get('/admin/payroll/hourlyworkrecord/')
        self.assertEqual(resp.status_code, 200)

    def test_hourly_record_admin_add_is_blocked(self):
        """Legacy hourly payroll is read-only: HourlyWorkRecord is superseded
        by HourlyRate/HourlyWorkEntry, so the admin no longer allows creating
        new rows here (see HourlyWorkRecordAdmin.has_add_permission)."""
        resp = self.client.get('/admin/payroll/hourlyworkrecord/add/')
        self.assertEqual(resp.status_code, 403)

    def test_create_hourly_record_via_admin_is_blocked(self):
        resp = self.client.post('/admin/payroll/hourlyworkrecord/add/', {
            'employee': self.emp.pk,
            'jalali_year': 1404,
            'jalali_month': 4,
            'hours_worked': '160',
            'hourly_rate': '500000',
            'notes': '',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(HourlyWorkRecord.objects.count(), 0)

    def test_hourly_record_admin_change_is_view_only(self):
        """A superuser has view permission, so Django admin renders the
        change page read-only (200) rather than 403 — but the underlying
        has_change_permission=False must still reject any actual save."""
        rec = HourlyWorkRecord.objects.create(
            employee=self.emp, jalali_year=1404, jalali_month=5,
            hours_worked=Decimal('100'), hourly_rate=Decimal('500000'),
        )
        resp = self.client.post(f'/admin/payroll/hourlyworkrecord/{rec.pk}/change/', {
            'employee': self.emp.pk,
            'jalali_year': 1404,
            'jalali_month': 5,
            'hours_worked': '999',
            'hourly_rate': '999999',
            'notes': 'tampered',
        })
        self.assertEqual(resp.status_code, 403)
        rec.refresh_from_db()
        self.assertEqual(rec.hours_worked, Decimal('100'))
        self.assertEqual(rec.hourly_rate, Decimal('500000'))
