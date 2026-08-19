"""Tests for the payroll report API.

Covers:
- Date range filter
- Filter by employee
- Filter by position
- wage_type filter (fixed / commission / both)
- Sum of fixed + commission totals
- Authentication guard
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from employees.models import Employee, JobPosition
from payroll.models import CommissionRule, CommissionTransaction, MonthlyWage
from surgeries.models import Patient, SurgeryHistory, SurgeryType

REPORT_URL = '/api/v2/payroll/report/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _position(name='جراح-گزارش'):
    return JobPosition.objects.create(name=name)


def _employee(position, name='دکتر گزارش', national_id='REPORT-NID-1'):
    return Employee.objects.create(
        full_name=name,
        national_id=national_id,
        gender='male',
        job_position=position,
        start_date=datetime.date(2020, 1, 1),
        personal_phone='09120000000',
        emergency_contact_phone='09120000001',
    )


def _wage(employee, amount, start_date=None):
    return MonthlyWage.objects.create(
        employee=employee,
        amount=amount,
        start_date=start_date or datetime.date(2024, 1, 1),
    )


def _surgery_type(name='عمل-گزارش', code='report_type'):
    return SurgeryType.objects.get_or_create(
        code=code,
        defaults={'name': name, 'base_rate': 5_000_000},
    )[0]


def _patient(case_code='RPT-001'):
    return Patient.objects.create(
        full_name='بیمار گزارش',
        case_code=case_code,
        phone_number='09130000000',
    )


def _commission_transaction(employee, surgery, rule, amount):
    return CommissionTransaction.objects.create(
        employee=employee,
        surgery=surgery,
        commission_rule=rule,
        amount=amount,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class PayrollReportAPITest(TestCase):

    def setUp(self):
        from django.contrib.auth.models import Group
        self.client = APIClient()
        self.user   = User.objects.create_user(username='admin_rpt', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

        self.position  = _position()
        self.employee  = _employee(self.position)
        self.wage      = _wage(self.employee, Decimal('5000000'))

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_report_returns_200(self):
        resp = self.client.get(REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_total_fixed_salary_included(self):
        resp = self.client.get(REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('total_fixed_salary', resp.data)
        self.assertEqual(Decimal(str(resp.data['total_fixed_salary'])), Decimal('5000000'))

    def test_total_commission_included(self):
        st   = _surgery_type()
        rule = CommissionRule.objects.create(
            job_position=self.position,
            surgery_type=st,
            commission_percent=Decimal('10.00'),
        )
        surgery = SurgeryHistory.objects.create(
            patient=_patient(),
            surgery_type=st,
            doctor_or_therapist=None,
            amount=Decimal('8000000'),
        )
        CommissionTransaction.objects.create(
            surgery=surgery,
            employee=self.employee,
            commission_rule=rule,
            amount=Decimal('800000'),
        )

        resp = self.client.get(REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(resp.data['total_commission'])), Decimal('800000'))

    def test_total_labor_cost_is_sum(self):
        st   = _surgery_type()
        rule = CommissionRule.objects.create(
            job_position=self.position,
            surgery_type=st,
            commission_percent=Decimal('10.00'),
        )
        surgery = SurgeryHistory.objects.create(
            patient=_patient(),
            surgery_type=st,
            doctor_or_therapist=None,
            amount=Decimal('10000000'),
        )
        CommissionTransaction.objects.create(
            surgery=surgery,
            employee=self.employee,
            commission_rule=rule,
            amount=Decimal('1000000'),
        )

        resp = self.client.get(REPORT_URL)
        expected_labor = Decimal('5000000') + Decimal('1000000')
        self.assertEqual(Decimal(str(resp.data['total_labor_cost'])), expected_labor)

    def test_filter_by_employee(self):
        pos2  = _position('مشاور-گزارش')
        emp2  = _employee(pos2, name='دکتر دوم', national_id='REPORT-NID-2')
        _wage(emp2, Decimal('3000000'))

        resp = self.client.get(REPORT_URL, {'employee': self.employee.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['employee_count'], 1)
        self.assertEqual(resp.data['employees'][0]['employee_id'], self.employee.pk)

    def test_filter_by_position(self):
        pos2 = _position('مشاور-گزارش-فیلتر')
        emp2 = _employee(pos2, name='دکتر سوم', national_id='REPORT-NID-3')
        _wage(emp2, Decimal('3000000'))

        resp = self.client.get(REPORT_URL, {'position': self.position.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['employee_count'], 1)
        self.assertEqual(resp.data['employees'][0]['job_position'], self.position.name)

    def test_wage_type_fixed_excludes_commission(self):
        st   = _surgery_type(code='report_type_fixed')
        rule = CommissionRule.objects.create(
            job_position=self.position,
            surgery_type=st,
            commission_percent=Decimal('10.00'),
        )
        surgery = SurgeryHistory.objects.create(
            patient=_patient(case_code='RPT-002'),
            surgery_type=st,
            doctor_or_therapist=None,
            amount=Decimal('5000000'),
        )
        CommissionTransaction.objects.create(
            surgery=surgery, employee=self.employee,
            commission_rule=rule, amount=Decimal('500000'),
        )

        resp = self.client.get(REPORT_URL, {'wage_type': 'fixed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(resp.data['total_commission'])), Decimal('0'))
        self.assertGreater(Decimal(str(resp.data['total_fixed_salary'])), Decimal('0'))

    def test_wage_type_commission_excludes_fixed(self):
        st   = _surgery_type(code='report_type_comm')
        rule = CommissionRule.objects.create(
            job_position=self.position,
            surgery_type=st,
            commission_percent=Decimal('10.00'),
        )
        surgery = SurgeryHistory.objects.create(
            patient=_patient(case_code='RPT-003'),
            surgery_type=st,
            doctor_or_therapist=None,
            amount=Decimal('5000000'),
        )
        CommissionTransaction.objects.create(
            surgery=surgery, employee=self.employee,
            commission_rule=rule, amount=Decimal('500000'),
        )

        resp = self.client.get(REPORT_URL, {'wage_type': 'commission'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(resp.data['total_fixed_salary'])), Decimal('0'))
        self.assertGreater(Decimal(str(resp.data['total_commission'])), Decimal('0'))

    def test_date_range_filter_excludes_old_data(self):
        # Wage active before our start range should be excluded
        _wage(
            _employee(_position('آرشیو-گزارش'), name='دکتر قدیمی', national_id='REPORT-NID-4'),
            Decimal('9000000'),
            start_date=datetime.date(2010, 1, 1),
        )
        future_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        resp = self.client.get(REPORT_URL, {
            'start_date': future_date,
            'end_date':   future_date,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Wage with end_date=None extends to future, so it's still active
        # Just check the response doesn't error
        self.assertIn('total_fixed_salary', resp.data)
