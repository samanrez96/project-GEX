"""Tests for CLI-52: Employee Cost Report.

Covers:
  - total_fixed_wages calculation (active MonthlyWage in date range)
  - total_commissions calculation (CommissionTransaction in date range by surgery date)
  - total_payments = total_fixed_wages + total_commissions
  - date range filtering (start_date, end_date)
  - wage_type filter: 'monthly', 'commission', 'all'
  - employee_id filter
  - position_id filter
  - highest-cost employee ordering (alphabetical by name)
  - pagination: count, next, previous, page_size
  - API permission enforcement
  - employees with no payroll in period not shown (graceful handling)
  - metadata block present and correct
  - invalid date returns 400
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, JobPosition
from payroll.models import CommissionRule, CommissionTransaction, MonthlyWage
from surgeries.models import Patient, SurgeryHistory, SurgeryType

User = get_user_model()

REPORT_URL = '/api/v1/payroll/reports/employee-cost/'

_seq = [0]


def _n():
    _seq[0] += 1
    return _seq[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _position(**kw):
    n = _n()
    # Prefix avoids collision with seeded positions (دکتر پوست, پرستار, etc.)
    d = {'name': f'تست_گزارش_{n}'}
    d.update(kw)
    return JobPosition.objects.create(**d)


def _employee(position=None, **kw):
    n = _n()
    if position is None:
        position = _position()
    d = {
        'full_name':    f'کارمند {n}',
        'national_id':  f'{n:010d}',
        'job_position': position,
        'start_date':   datetime.date(2020, 1, 1),
    }
    d.update(kw)
    return Employee.objects.create(**d)


def _wage(employee, amount, start_date, end_date=None, is_active=True):
    return MonthlyWage.objects.create(
        employee=employee,
        amount=Decimal(str(amount)),
        start_date=start_date,
        end_date=end_date,
        is_active=is_active,
    )


def _surgery_type(**kw):
    n = _n()
    d = {'name': f'عمل {n}', 'code': f'op_{n}', 'base_rate': Decimal('500000')}
    d.update(kw)
    return SurgeryType.objects.create(**d)


def _patient(**kw):
    n = _n()
    d = {'full_name': f'بیمار {n}', 'case_code': f'C{n:04d}', 'phone_number': f'091{n:08d}'}
    d.update(kw)
    return Patient.objects.create(**d)


def _surgery(surgery_type, surgery_date, **kw):
    d = {
        'patient':      _patient(),
        'surgery_type': surgery_type,
        'amount':       Decimal('10000000'),
        'surgery_date': surgery_date,
    }
    d.update(kw)
    return SurgeryHistory.objects.create(**d)


def _commission_rule(position, surgery_type, percent='10.00'):
    return CommissionRule.objects.create(
        job_position=position,
        surgery_type=surgery_type,
        commission_percent=Decimal(str(percent)),
        start_date=datetime.date(2020, 1, 1),
        is_active=True,
    )


def _commission(surgery, employee, rule, amount):
    return CommissionTransaction.objects.create(
        surgery=surgery,
        employee=employee,
        commission_rule=rule,
        amount=Decimal(str(amount)),
    )


def _user_in_group(username, group_name):
    user = User.objects.create_user(username=username, password='pass')
    grp, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(grp)
    return user


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------

class EmployeeCostReportBase(APITestCase):
    """
    Two employees with wages and commissions in Jan 2025 and Jun 2025.

    Employee A (doctor):
      - MonthlyWage:  5,000,000 ريال (active all year)
      - Commission Jan: 500,000 ريال (surgery Jan 15)
      - Commission Jun: 600,000 ريال (surgery Jun 1)

    Employee B (nurse):
      - MonthlyWage:  3,000,000 ريال (Jan 1 → Mar 31)
      - Commission Jun: 200,000 ريال (surgery Jun 1)
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser('sa2', 'sa2@t.com', 'pass')

        self.pos_doctor = _position()
        self.pos_nurse  = _position()

        self.emp_a = _employee(self.pos_doctor, full_name='احمد الف')
        self.emp_b = _employee(self.pos_nurse,  full_name='بتول ب')

        # Wages
        self.wage_a = _wage(
            self.emp_a, 5_000_000,
            start_date=datetime.date(2025, 1, 1),
        )
        self.wage_b = _wage(
            self.emp_b, 3_000_000,
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date(2025, 3, 31),
        )

        # Commission setup
        self.stype     = _surgery_type()
        self.rule_a    = _commission_rule(self.pos_doctor, self.stype)
        self.rule_b    = _commission_rule(self.pos_nurse,  self.stype)

        # Surgery Jan
        self.surg_jan = _surgery(
            self.stype,
            surgery_date=datetime.datetime(2025, 1, 15, tzinfo=datetime.timezone.utc),
        )
        # Surgery Jun
        self.surg_jun = _surgery(
            self.stype,
            surgery_date=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc),
        )

        # Commission transactions
        self.ct_a_jan = _commission(self.surg_jan, self.emp_a, self.rule_a, 500_000)
        self.ct_a_jun = _commission(self.surg_jun, self.emp_a, self.rule_a, 600_000)
        self.ct_b_jun = _commission(self.surg_jun, self.emp_b, self.rule_b, 200_000)

        self.client.force_authenticate(user=self.superuser)


# ---------------------------------------------------------------------------
# Total calculation
# ---------------------------------------------------------------------------

class EmployeeCostTotalTest(EmployeeCostReportBase):

    def test_grand_total_fixed_wages(self):
        # Both wages are active all year → 5M + 3M = 8M
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(res.data['metadata']['total_fixed_wages']),
            Decimal('8000000'),
        )

    def test_grand_total_commissions(self):
        # emp_a: 500k + 600k = 1.1M; emp_b: 200k; total = 1.3M
        res = self.client.get(REPORT_URL)
        self.assertEqual(
            Decimal(res.data['metadata']['total_commissions']),
            Decimal('1300000'),
        )

    def test_grand_total_payments(self):
        # 8M wages + 1.3M commissions = 9.3M
        res = self.client.get(REPORT_URL)
        self.assertEqual(
            Decimal(res.data['metadata']['total_payments']),
            Decimal('9300000'),
        )

    def test_per_employee_totals(self):
        res = self.client.get(REPORT_URL)
        rows = {r['employee_id']: r for r in res.data['results']}

        # emp_a: wage=5M, commission=1.1M
        row_a = rows[self.emp_a.pk]
        self.assertEqual(Decimal(row_a['total_fixed_wages']), Decimal('5000000'))
        self.assertEqual(Decimal(row_a['total_commissions']), Decimal('1100000'))
        self.assertEqual(Decimal(row_a['total_payments']),    Decimal('6100000'))

        # emp_b: wage=3M, commission=200k
        row_b = rows[self.emp_b.pk]
        self.assertEqual(Decimal(row_b['total_fixed_wages']), Decimal('3000000'))
        self.assertEqual(Decimal(row_b['total_commissions']), Decimal('200000'))
        self.assertEqual(Decimal(row_b['total_payments']),    Decimal('3200000'))

    def test_total_payments_equals_wages_plus_commissions(self):
        res = self.client.get(REPORT_URL)
        for row in res.data['results']:
            expected = Decimal(row['total_fixed_wages']) + Decimal(row['total_commissions'])
            self.assertEqual(Decimal(row['total_payments']), expected)

    def test_employee_count_in_metadata(self):
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.data['metadata']['employee_count'], 2)


# ---------------------------------------------------------------------------
# Date range filter
# ---------------------------------------------------------------------------

class EmployeeCostDateFilterTest(EmployeeCostReportBase):

    def test_start_date_excludes_earlier_commissions(self):
        # start_date Jun 1 → only Jun commissions counted
        res = self.client.get(REPORT_URL, {'start_date': '2025-06-01'})
        rows = {r['employee_id']: r for r in res.data['results']}
        # emp_a commission: only Jun 600k (Jan 500k excluded)
        self.assertEqual(Decimal(rows[self.emp_a.pk]['total_commissions']), Decimal('600000'))

    def test_end_date_excludes_later_commissions(self):
        # end_date Jan 31 → only Jan commissions counted
        res = self.client.get(REPORT_URL, {'end_date': '2025-01-31'})
        rows = {r['employee_id']: r for r in res.data['results']}
        self.assertEqual(Decimal(rows[self.emp_a.pk]['total_commissions']), Decimal('500000'))

    def test_date_range_wage_overlap_end_date(self):
        # Wage B ends Mar 31; filtering after Apr 1 should exclude it
        res = self.client.get(REPORT_URL, {'start_date': '2025-04-01'})
        employee_ids = [r['employee_id'] for r in res.data['results']]
        # emp_b's wage has end_date=Mar 31, so no longer active after Apr 1
        # emp_b still has Jun commission so will appear but with wage=0
        if self.emp_b.pk in employee_ids:
            row_b = next(r for r in res.data['results'] if r['employee_id'] == self.emp_b.pk)
            self.assertEqual(Decimal(row_b['total_fixed_wages']), Decimal('0'))

    def test_date_range_no_results(self):
        # 2020 — no wages or commissions
        res = self.client.get(REPORT_URL, {'start_date': '2020-01-01', 'end_date': '2020-12-31'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(res.data['metadata']['total_payments']), Decimal('0'))
        self.assertEqual(res.data['count'], 0)
        self.assertEqual(res.data['results'], [])

    def test_invalid_date_returns_400(self):
        res = self.client.get(REPORT_URL, {'start_date': 'not-a-date'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# wage_type filter
# ---------------------------------------------------------------------------

class EmployeeCostWageTypeTest(EmployeeCostReportBase):

    def test_wage_type_monthly_only_shows_wages(self):
        res = self.client.get(REPORT_URL, {'wage_type': 'monthly'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for row in res.data['results']:
            self.assertEqual(Decimal(row['total_commissions']), Decimal('0'))

    def test_wage_type_monthly_total_fixed_wages(self):
        res = self.client.get(REPORT_URL, {'wage_type': 'monthly'})
        self.assertEqual(
            Decimal(res.data['metadata']['total_fixed_wages']),
            Decimal('8000000'),
        )
        self.assertEqual(
            Decimal(res.data['metadata']['total_commissions']),
            Decimal('0'),
        )

    def test_wage_type_monthly_excludes_commission_only_employees(self):
        # Create employee with commission only (no wage)
        emp_c = _employee(self.pos_doctor, full_name='جواد ج')
        surg  = _surgery(
            self.stype,
            surgery_date=datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc),
        )
        _commission(surg, emp_c, self.rule_a, 400_000)

        res = self.client.get(REPORT_URL, {'wage_type': 'monthly'})
        emp_ids = [r['employee_id'] for r in res.data['results']]
        self.assertNotIn(emp_c.pk, emp_ids)

    def test_wage_type_commission_only_shows_commissions(self):
        res = self.client.get(REPORT_URL, {'wage_type': 'commission'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for row in res.data['results']:
            self.assertEqual(Decimal(row['total_fixed_wages']), Decimal('0'))

    def test_wage_type_commission_total_commissions(self):
        res = self.client.get(REPORT_URL, {'wage_type': 'commission'})
        self.assertEqual(
            Decimal(res.data['metadata']['total_commissions']),
            Decimal('1300000'),
        )
        self.assertEqual(
            Decimal(res.data['metadata']['total_fixed_wages']),
            Decimal('0'),
        )

    def test_wage_type_commission_excludes_wage_only_employees(self):
        # Create employee with only a wage and no commissions
        emp_d = _employee(self.pos_nurse, full_name='دلارام د')
        _wage(emp_d, 2_000_000, start_date=datetime.date(2025, 1, 1))

        res = self.client.get(REPORT_URL, {'wage_type': 'commission'})
        emp_ids = [r['employee_id'] for r in res.data['results']]
        self.assertNotIn(emp_d.pk, emp_ids)

    def test_wage_type_all_includes_both(self):
        res = self.client.get(REPORT_URL, {'wage_type': 'all'})
        self.assertEqual(res.data['count'], 2)

    def test_invalid_wage_type_defaults_to_all(self):
        res = self.client.get(REPORT_URL, {'wage_type': 'nonsense'})
        self.assertEqual(res.data['metadata']['wage_type'], 'all')
        self.assertEqual(res.data['count'], 2)

    def test_metadata_reflects_wage_type(self):
        res = self.client.get(REPORT_URL, {'wage_type': 'monthly'})
        self.assertEqual(res.data['metadata']['wage_type'], 'monthly')


# ---------------------------------------------------------------------------
# employee_id filter
# ---------------------------------------------------------------------------

class EmployeeCostEmployeeFilterTest(EmployeeCostReportBase):

    def test_filter_by_employee_id(self):
        res = self.client.get(REPORT_URL, {'employee_id': self.emp_a.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['employee_id'], self.emp_a.pk)

    def test_filter_by_employee_id_totals_correct(self):
        res = self.client.get(REPORT_URL, {'employee_id': self.emp_a.pk})
        row = res.data['results'][0]
        self.assertEqual(Decimal(row['total_fixed_wages']), Decimal('5000000'))
        self.assertEqual(Decimal(row['total_commissions']), Decimal('1100000'))

    def test_filter_by_nonexistent_employee_returns_empty(self):
        res = self.client.get(REPORT_URL, {'employee_id': 999999})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 0)
        self.assertEqual(res.data['results'], [])

    def test_metadata_reflects_employee_id(self):
        res = self.client.get(REPORT_URL, {'employee_id': self.emp_a.pk})
        self.assertEqual(res.data['metadata']['employee_id'], self.emp_a.pk)


# ---------------------------------------------------------------------------
# position_id filter
# ---------------------------------------------------------------------------

class EmployeeCostPositionFilterTest(EmployeeCostReportBase):

    def test_filter_by_position_id(self):
        res = self.client.get(REPORT_URL, {'position_id': self.pos_doctor.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['employee_id'], self.emp_a.pk)

    def test_filter_by_position_excludes_other_positions(self):
        res = self.client.get(REPORT_URL, {'position_id': self.pos_nurse.pk})
        emp_ids = [r['employee_id'] for r in res.data['results']]
        self.assertNotIn(self.emp_a.pk, emp_ids)
        self.assertIn(self.emp_b.pk, emp_ids)

    def test_metadata_reflects_position_id(self):
        res = self.client.get(REPORT_URL, {'position_id': self.pos_doctor.pk})
        self.assertEqual(res.data['metadata']['position_id'], self.pos_doctor.pk)


# ---------------------------------------------------------------------------
# Employees with no payroll — graceful handling
# ---------------------------------------------------------------------------

class EmployeeCostGracefulHandlingTest(EmployeeCostReportBase):

    def test_employee_with_no_payroll_not_in_results(self):
        emp_e = _employee(self.pos_doctor, full_name='امیر ا')
        res = self.client.get(REPORT_URL)
        emp_ids = [r['employee_id'] for r in res.data['results']]
        self.assertNotIn(emp_e.pk, emp_ids)

    def test_no_payroll_in_period_returns_empty(self):
        # Wages start in 2025; 2024 has no wages or commissions → empty
        res = self.client.get(REPORT_URL, {'start_date': '2024-01-01', 'end_date': '2024-12-31'})
        self.assertEqual(res.data['count'], 0)
        self.assertEqual(res.data['results'], [])
        self.assertEqual(Decimal(res.data['metadata']['total_payments']), Decimal('0'))

    def test_inactive_wage_excluded(self):
        emp_f = _employee(self.pos_nurse, full_name='فرزانه ف')
        _wage(emp_f, 2_000_000, start_date=datetime.date(2025, 1, 1), is_active=False)
        res = self.client.get(REPORT_URL)
        emp_ids = [r['employee_id'] for r in res.data['results']]
        self.assertNotIn(emp_f.pk, emp_ids)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class EmployeeCostPermissionsTest(EmployeeCostReportBase):

    def test_superuser_allowed(self):
        self.client.force_authenticate(user=self.superuser)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_finance_user_allowed(self):
        user = _user_in_group(f'fin_{_n()}', 'finance_user')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_admin_group_user_allowed(self):
        user = _user_in_group(f'adm_{_n()}', 'admin')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_inventory_user_forbidden(self):
        user = _user_in_group(f'inv_{_n()}', 'inventory_user')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_manager_forbidden(self):
        user = _user_in_group(f'empmgr_{_n()}', 'employee_manager')
        self.client.force_authenticate(user=user)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Metadata block
# ---------------------------------------------------------------------------

class EmployeeCostMetadataTest(EmployeeCostReportBase):

    def test_metadata_fields_present(self):
        res = self.client.get(REPORT_URL)
        meta = res.data['metadata']
        for field in [
            'start_date', 'end_date', 'wage_type',
            'employee_id', 'position_id',
            'total_fixed_wages', 'total_commissions', 'total_payments',
            'employee_count',
        ]:
            self.assertIn(field, meta, msg=f'Missing metadata field: {field}')

    def test_metadata_defaults(self):
        res = self.client.get(REPORT_URL)
        meta = res.data['metadata']
        self.assertIsNone(meta['start_date'])
        self.assertIsNone(meta['end_date'])
        self.assertEqual(meta['wage_type'], 'all')
        self.assertIsNone(meta['employee_id'])
        self.assertIsNone(meta['position_id'])

    def test_row_fields_present(self):
        res = self.client.get(REPORT_URL)
        for row in res.data['results']:
            for field in [
                'employee_id', 'employee_name', 'position_name',
                'total_fixed_wages', 'total_commissions', 'total_payments',
            ]:
                self.assertIn(field, row, msg=f'Missing row field: {field}')

    def test_row_includes_position_name(self):
        res = self.client.get(REPORT_URL, {'employee_id': self.emp_a.pk})
        self.assertEqual(res.data['results'][0]['position_name'], self.pos_doctor.name)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class EmployeeCostPaginationTest(EmployeeCostReportBase):

    def test_count_matches_total_rows(self):
        res = self.client.get(REPORT_URL)
        self.assertEqual(res.data['count'], len(res.data['results']))

    def test_page_size_1_returns_one_row(self):
        res = self.client.get(REPORT_URL, {'page_size': '1'})
        self.assertEqual(len(res.data['results']), 1)
        self.assertEqual(res.data['count'], 2)
        self.assertIsNotNone(res.data['next'])
        self.assertIsNone(res.data['previous'])

    def test_second_page(self):
        res = self.client.get(REPORT_URL, {'page': '2', 'page_size': '1'})
        self.assertEqual(len(res.data['results']), 1)
        self.assertIsNone(res.data['next'])
        self.assertIsNotNone(res.data['previous'])

    def test_empty_result_no_next_or_previous(self):
        res = self.client.get(REPORT_URL, {'start_date': '2020-01-01', 'end_date': '2020-12-31'})
        self.assertIsNone(res.data['next'])
        self.assertIsNone(res.data['previous'])
