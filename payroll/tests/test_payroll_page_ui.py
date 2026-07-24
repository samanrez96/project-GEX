"""Regression tests for the payroll-page UI/data-mapping bugs.

Covers:
  - the API response has all nine named per-employee fields, always present
  - monthly salary never leaks into hourly_salary (and vice versa)
  - hourly_salary and total_hours_worked are always consistently paired
    (never one populated with the other blank)
  - total_commission / total_payment formulas
  - zero values are returned explicitly, never omitted
  - full scenario matrix: monthly-only, hourly-only, commission-only,
    monthly+hourly, monthly+hourly+commission, no components at all
  - the payroll-page template renders exactly six header columns and uses
    colspan="6" for its loading row
  - the summary totals equal the sum of the row totals
  - opening/refreshing the payroll page never finalizes HourlyWorkEntry rows
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from employees.models import Employee, JobPosition
from payroll.models import (
    CommissionRule,
    CommissionTransaction,
    HourlyRate,
    HourlyWorkEntry,
    MonthlyWage,
    PayrollPeriod,
    PayrollStatus,
    _gregorian_to_jalali,
    _jalali_to_gregorian,
)
from payroll.services import finalize_hourly_payroll
from surgeries.models import Patient, SurgeryHistory, SurgeryType

User = get_user_model()
REPORT_URL = '/api/v1/payroll/report/'
PAGE_URL = '/admin/payroll/payroll-page/'

EXPECTED_ROW_FIELDS = {
    'employee_id', 'employee_name', 'job_position',
    'fixed_salary', 'purchase_commission', 'surgery_commission',
    'total_commission', 'hourly_salary', 'total_hours_worked',
    'total_payment',
}

_counter = [0]


def make_position(name=None):
    _counter[0] += 1
    return JobPosition.objects.create(name=name or f'موقعیت-پیرول-{_counter[0]}')


def make_employee(position=None, **kwargs):
    _counter[0] += 1
    defaults = {
        'full_name': f'کارمند پیرول {_counter[0]}',
        'national_id': f'3{_counter[0]:09d}',
        'gender': 'male',
        'job_position': position or make_position(),
        'start_date': datetime.date(2024, 1, 1),
        'personal_phone': f'091{_counter[0]:08d}',
        'emergency_contact_phone': f'092{_counter[0]:08d}',
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_wage(employee, amount, start=datetime.date(2024, 1, 1)):
    return MonthlyWage.objects.create(employee=employee, amount=amount, start_date=start)


def make_surgery_type():
    _counter[0] += 1
    return SurgeryType.objects.create(
        name=f'عمل-پیرول-{_counter[0]}', code=f'payroll_type_{_counter[0]}', base_rate=Decimal('0'),
    )


def make_commission(employee, position, percent=Decimal('10.00'), amount=Decimal('1000000')):
    st = make_surgery_type()
    rule = CommissionRule.objects.create(
        job_position=position, surgery_type=st, commission_percent=percent,
    )
    patient = Patient.objects.create(
        full_name='بیمار پیرول', case_code=f'PR-{_counter[0]}', phone_number='09130000000',
    )
    surgery = SurgeryHistory.objects.create(
        patient=patient, surgery_type=st, doctor_or_therapist=None, amount=amount,
    )
    return CommissionTransaction.objects.create(
        surgery=surgery, employee=employee, commission_rule=rule,
        amount=(amount * percent / Decimal('100')),
    )


def _current_jalali_period():
    today = datetime.date.today()
    jy, jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
    period, _ = PayrollPeriod.objects.get_or_create(
        year=jy, month=jm, defaults={'status': PayrollStatus.OPEN},
    )
    gy, gm, gd = _jalali_to_gregorian(jy, jm, 1)
    return period, jy, jm, datetime.date(gy, gm, gd)


def make_finalized_hourly(employee, rate, hours):
    period, jy, jm, month_start = _current_jalali_period()
    HourlyRate.objects.create(employee=employee, rate=rate, start_date=datetime.date(2020, 1, 1))
    HourlyWorkEntry.objects.create(employee=employee, work_date=month_start, hours_worked=hours)
    finalize_hourly_payroll(employee, period)
    return period, jy, jm


class PayrollReportContractTest(TestCase):
    """API response contract: named fields, always present, correctly typed."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='pay_ui_admin', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

    def test_row_has_all_nine_named_fields(self):
        position = make_position()
        emp = make_employee(position=position)
        make_wage(emp, Decimal('5000000'))

        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = resp.data['employees'][0]
        self.assertTrue(EXPECTED_ROW_FIELDS.issubset(set(row.keys())))

    def test_employee_with_no_payroll_components_is_absent_or_zeroed(self):
        # An employee with literally nothing configured must never appear
        # with garbage/undefined values — either absent from the list, or
        # present with every numeric field at an explicit zero.
        position = make_position()
        emp = make_employee(position=position)
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = [r for r in resp.data['employees'] if r['employee_id'] == emp.pk]
        for row in rows:
            self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('0'))
            self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('0'))
            self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('0'))
            self.assertEqual(Decimal(str(row['total_commission'])), Decimal('0'))
            self.assertEqual(Decimal(str(row['total_payment'])), Decimal('0'))


class PayrollScenarioMatrixTest(TestCase):
    """The exact scenario matrix requested by the task: monthly-only,
    hourly-only, commission-only, monthly+hourly, monthly+hourly+commission,
    and no components at all."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='pay_matrix_admin', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

    def _row_for(self, employee, **params):
        params['employee'] = employee.pk
        resp = self.client.get(REPORT_URL, params)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = resp.data['employees']
        return rows[0] if rows else None

    def test_monthly_only_employee(self):
        emp = make_employee()
        make_wage(emp, Decimal('4000000'))
        row = self._row_for(emp)
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('4000000'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_commission'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('4000000'))

    def test_hourly_only_employee(self):
        emp = make_employee()
        make_finalized_hourly(emp, Decimal('500000'), Decimal('10'))
        row = self._row_for(emp)
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('5000000'))
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('10'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('5000000'))

    def test_commission_only_employee(self):
        position = make_position()
        emp = make_employee(position=position)
        make_commission(emp, position, amount=Decimal('2000000'))
        row = self._row_for(emp)
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['surgery_commission'])), Decimal('200000'))
        self.assertEqual(Decimal(str(row['total_commission'])), Decimal('200000'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('200000'))

    def test_monthly_plus_hourly_employee(self):
        emp = make_employee()
        make_wage(emp, Decimal('3000000'))
        make_finalized_hourly(emp, Decimal('400000'), Decimal('5'))
        row = self._row_for(emp)
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('3000000'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('2000000'))
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('5'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('5000000'))

    def test_monthly_plus_hourly_plus_commission_employee(self):
        position = make_position()
        emp = make_employee(position=position)
        make_wage(emp, Decimal('2000000'))
        make_finalized_hourly(emp, Decimal('300000'), Decimal('4'))
        make_commission(emp, position, amount=Decimal('1000000'))
        row = self._row_for(emp)
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('2000000'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('1200000'))
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('4'))
        self.assertEqual(Decimal(str(row['surgery_commission'])), Decimal('100000'))
        self.assertEqual(Decimal(str(row['total_commission'])), Decimal('100000'))
        # 2,000,000 + 1,200,000 + 100,000
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('3300000'))

    def test_employee_with_no_components_absent_from_default_report(self):
        emp = make_employee()
        resp = self.client.get(REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [r['employee_id'] for r in resp.data['employees']]
        self.assertNotIn(emp.pk, ids)


class HourlyFixedNoMixupTest(TestCase):
    """The specific reported bug: the same amount must never appear in both
    fixed_salary and hourly_salary, and hourly_salary/total_hours_worked
    must never be inconsistent (one set, the other blank)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='pay_mixup_admin', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

    def test_fixed_salary_not_copied_into_hourly_salary(self):
        emp = make_employee()
        make_wage(emp, Decimal('6000000'))
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('6000000'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('0'))

    def test_hourly_salary_not_copied_into_fixed_salary(self):
        emp = make_employee()
        make_finalized_hourly(emp, Decimal('500000'), Decimal('8'))
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('4000000'))
        self.assertEqual(Decimal(str(row['fixed_salary'])), Decimal('0'))

    def test_hourly_salary_and_hours_are_paired(self):
        emp = make_employee()
        make_finalized_hourly(emp, Decimal('500000'), Decimal('7.5'))
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        row = resp.data['employees'][0]
        self.assertGreater(Decimal(str(row['hourly_salary'])), Decimal('0'))
        self.assertGreater(Decimal(str(row['total_hours_worked'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('7.5'))

    def test_no_active_hourly_configuration_shows_zero_zero(self):
        emp = make_employee()
        make_wage(emp, Decimal('1000000'))  # only monthly, no hourly at all
        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('0'))


class PayrollSummaryMatchesRowsTest(TestCase):
    """The sum of row total_payment values must equal the page total."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='pay_sum_admin', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

    def test_total_labor_cost_equals_sum_of_row_totals(self):
        position = make_position()
        emp1 = make_employee(position=position)
        make_wage(emp1, Decimal('3000000'))
        emp2 = make_employee(position=position)
        make_finalized_hourly(emp2, Decimal('500000'), Decimal('6'))
        emp3 = make_employee(position=position)
        make_commission(emp3, position, amount=Decimal('500000'))

        resp = self.client.get(REPORT_URL, {'position': position.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = resp.data['employees']
        row_sum = sum(Decimal(str(r['total_payment'])) for r in rows)
        self.assertEqual(row_sum, Decimal(str(resp.data['total_labor_cost'])))

    def test_total_hourly_salary_card_matches_row_sum(self):
        emp1 = make_employee()
        make_finalized_hourly(emp1, Decimal('500000'), Decimal('4'))
        emp2 = make_employee()
        make_finalized_hourly(emp2, Decimal('600000'), Decimal('3'))

        resp = self.client.get(REPORT_URL)
        rows = resp.data['employees']
        hourly_sum = sum(
            Decimal(str(r['hourly_salary'])) for r in rows
            if r['employee_id'] in (emp1.pk, emp2.pk)
        )
        # 4h * 500,000 + 3h * 600,000
        self.assertEqual(hourly_sum, Decimal('3800000'))
        self.assertGreaterEqual(Decimal(str(resp.data['total_hourly_salary'])), hourly_sum)


class PayrollPageDoesNotFinalizeTest(TestCase):
    """Opening/refreshing the payroll page must never finalize work entries
    — it only reads already-priced (finalized) HourlyWorkEntry rows."""

    def setUp(self):
        self.admin = User.objects.create_superuser('pay_page_admin', password='pass')
        self.client.force_login(self.admin)

    def test_unprocessed_entries_stay_unprocessed_after_report_read(self):
        emp = make_employee()
        HourlyRate.objects.create(employee=emp, rate=Decimal('500000'), start_date=datetime.date(2020, 1, 1))
        _, jy, jm, month_start = _current_jalali_period()
        entry = HourlyWorkEntry.objects.create(employee=emp, work_date=month_start, hours_worked=Decimal('5'))

        api_client = APIClient()
        api_client.force_authenticate(user=self.admin)
        resp = api_client.get(REPORT_URL, {'year': jy, 'month': jm})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        entry.refresh_from_db()
        self.assertFalse(entry.is_processed)
        self.assertIsNone(entry.rate_used)
        self.assertIsNone(entry.amount)

    def test_opening_payroll_page_html_does_not_finalize(self):
        emp = make_employee()
        HourlyRate.objects.create(employee=emp, rate=Decimal('500000'), start_date=datetime.date(2020, 1, 1))
        _, jy, jm, month_start = _current_jalali_period()
        entry = HourlyWorkEntry.objects.create(employee=emp, work_date=month_start, hours_worked=Decimal('5'))

        resp = self.client.get(PAGE_URL)
        self.assertEqual(resp.status_code, 200)

        entry.refresh_from_db()
        self.assertFalse(entry.is_processed)


class PayrollPageTemplateStructureTest(TestCase):
    """The rendered template must have exactly six header columns and use
    colspan="6" for its loading row — the exact count the JS/API contract
    (and every row it renders) must match. Purchase/surgery commission and
    worked-hours detail no longer have their own columns — they only appear
    inside the per-row expandable detail row."""

    def setUp(self):
        self.admin = User.objects.create_superuser('pay_tmpl_admin', password='pass')
        self.client.force_login(self.admin)

    def test_page_loads(self):
        resp = self.client.get(PAGE_URL)
        self.assertEqual(resp.status_code, 200)

    def test_header_has_six_columns(self):
        resp = self.client.get(PAGE_URL)
        content = resp.content.decode('utf-8')
        thead = content.split('<thead>')[1].split('</thead>')[0]
        self.assertEqual(thead.count('<th>'), 6)

    def test_loading_row_uses_colspan_six(self):
        resp = self.client.get(PAGE_URL)
        self.assertContains(resp, 'colspan="6"')
        self.assertNotContains(resp, 'colspan="9"')

    def test_column_order_matches_expected_contract(self):
        resp = self.client.get(PAGE_URL)
        content = resp.content.decode('utf-8')
        thead = content.split('<thead>')[1].split('</thead>')[0]
        headers = [h.split('</th>')[0] for h in thead.split('<th>')[1:]]
        self.assertEqual(headers, [
            'نام کارمند', 'پوزیشن', 'حقوق ثابت',
            'کمیسیون‌ها', 'حقوق ساعتی', 'مجموع پرداختی',
        ])

    def test_uses_semantic_table_inside_scroll_wrapper(self):
        resp = self.client.get(PAGE_URL)
        content = resp.content.decode('utf-8')
        self.assertIn('payroll-table__wrap', content)
        self.assertIn('<table', content)
        self.assertIn('<thead>', content)
        self.assertIn('<tbody', content)

    def test_no_leaked_developer_comment_text(self):
        """Regression for a multi-line {# ... #} Django comment — Django's
        comment tag cannot span multiple lines, so the literal English note
        rendered straight into the page above the table."""
        resp = self.client.get(PAGE_URL)
        self.assertNotContains(resp, 'Column widths are defined exactly once')
        self.assertNotContains(resp, 'apply\n     identically')

    def test_no_raw_template_comment_syntax_leaks(self):
        resp = self.client.get(PAGE_URL)
        content = resp.content.decode('utf-8')
        # A real Django {# #} comment is stripped entirely by the template
        # engine — if either delimiter shows up in the rendered output, some
        # comment in the template failed to parse as a comment.
        self.assertNotIn('{#', content)
        self.assertNotIn('#}', content)

    def test_colgroup_has_exactly_six_columns(self):
        resp = self.client.get(PAGE_URL)
        content = resp.content.decode('utf-8')
        colgroup = content.split('<colgroup>')[1].split('</colgroup>')[0]
        self.assertEqual(colgroup.count('<col'), 6)

    def test_no_leftover_nine_column_skeleton(self):
        resp = self.client.get(PAGE_URL)
        self.assertNotContains(resp, 'colspan="9"')
        self.assertNotContains(resp, 'py-col-money')
        self.assertNotContains(resp, 'py-col-hours')


class PayrollPageJSRenderingSourceTest(TestCase):
    """The row/detail-row rendering lives in client-side JS (payroll_page.js)
    and runs against data fetched after page load, so it can't be exercised
    through Django's test client (no JS engine here). These tests instead
    assert the required rendering hooks are present in the shipped source —
    the same structural-guarantee approach used for the template tests above.
    Full interactive behavior (actual expand/collapse, computed zero-dash
    output) should additionally be checked manually in a browser."""

    def setUp(self):
        import pathlib
        js_path = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / 'static' / 'admin' / 'js' / 'payroll_page.js'
        )
        self.source = js_path.read_text(encoding='utf-8')

    def test_cols_constant_is_six(self):
        self.assertIn('COLS       = 6', self.source)

    def test_defines_zero_dash_helpers(self):
        self.assertIn('function formatMoneyOrDash(', self.source)
        self.assertIn('function formatHoursOrDash(', self.source)
        self.assertIn('function isZeroish(', self.source)

    def test_total_payment_never_uses_dash_helper(self):
        total_cell = self.source.split("payroll-table__amount--total")[1][:200]
        self.assertIn('formatPrice(totalPayment)', total_cell)
        self.assertNotIn('formatMoneyOrDash(totalPayment)', total_cell)

    def test_hourly_cell_combines_amount_and_hours(self):
        self.assertIn('payroll-table__hourly-secondary', self.source)
        self.assertIn('hourlyIsZero', self.source)

    def test_detail_row_uses_colspan_variable_and_holds_commission_fields(self):
        self.assertIn("detailRow.innerHTML =", self.source)
        self.assertIn("'<td colspan=\"' + COLS + '\">'", self.source)
        self.assertIn('purchaseComm', self.source)
        self.assertIn('surgeryComm', self.source)

    def test_toggle_is_keyboard_activatable_button_with_aria(self):
        self.assertIn('payroll-table__toggle', self.source)
        self.assertIn("type=\"button\"", self.source)
        self.assertIn('aria-expanded', self.source)
        self.assertIn('aria-controls', self.source)

    def test_loading_and_error_states_use_cols_variable(self):
        self.assertIn("colspan=\"' + COLS + '\"", self.source)
        self.assertNotIn('colspan="9"', self.source)
