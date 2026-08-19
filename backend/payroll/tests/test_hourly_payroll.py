"""Tests for the new hourly payroll type: HourlyRate, HourlyWorkEntry,
finalize_hourly_payroll, and their Finance/report/admin integration.

The pre-existing HourlyWorkRecord (monthly aggregate, flat Employee.hourly_rate)
is untouched — covered separately by test_hourly_wage.py.

Covers:
  - hourly payroll type selection via EmployeeAdminForm (wage_type='hourly')
  - active hourly-rate lookup (HourlyRate.get_active_rate_for_date)
  - rate changes inside one payroll period price each entry independently
  - fractional worked hours (7.5, 4.25)
  - invalid hours (zero, negative, >24) rejected with Persian errors
  - total hourly salary calculation
  - a work entry cannot be priced/paid twice
  - snapshot preservation: later rate changes don't alter a finalized entry
  - Finance expense creation/update from hourly payroll
  - payroll report totals include the new hourly bucket
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from employees.admin import EmployeeAdminForm
from employees.models import Employee, JobPosition
from payroll.models import (
    HourlyRate,
    HourlyWorkEntry,
    PayrollPeriod,
    PayrollStatus,
    PayrollTypeConfig,
    _gregorian_to_jalali,
    _jalali_to_gregorian,
)
from payroll.services import finalize_hourly_payroll, preview_hourly_payroll

User = get_user_model()

_emp_counter = [0]


def make_position(name='تکنسین'):
    pos, _ = JobPosition.objects.get_or_create(name=name)
    return pos


def make_employee(position=None):
    if position is None:
        position = make_position()
    _emp_counter[0] += 1
    return Employee.objects.create(
        full_name=f'کارمند ساعتی {_emp_counter[0]}',
        national_id=f'2{_emp_counter[0]:09d}',
        gender='male',
        job_position=position,
        start_date=datetime.date(2024, 1, 1),
        personal_phone=f'093{_emp_counter[0]:08d}',
        emergency_contact_phone=f'094{_emp_counter[0]:08d}',
    )


def make_rate(employee, rate, start, end=None, is_active=True, user=None):
    return HourlyRate.objects.create(
        employee=employee, rate=rate, start_date=start, end_date=end,
        is_active=is_active, created_by=user,
    )


def make_entry(employee, work_date, hours):
    return HourlyWorkEntry.objects.create(
        employee=employee, work_date=work_date, hours_worked=hours,
    )


def make_period(year, month):
    return PayrollPeriod.objects.get_or_create(
        year=year, month=month, defaults={'status': PayrollStatus.OPEN},
    )[0]


def previous_jalali_month(year, month):
    return (year, month - 1) if month > 1 else (year - 1, 12)


# ---------------------------------------------------------------------------
# HourlyRate model
# ---------------------------------------------------------------------------

class HourlyRateModelTest(TestCase):

    def test_zero_rate_is_valid(self):
        emp = make_employee()
        rate = make_rate(emp, Decimal('0'), datetime.date(2025, 1, 1))
        rate.full_clean()  # must not raise

    def test_negative_rate_rejected(self):
        emp = make_employee()
        rate = HourlyRate(employee=emp, rate=Decimal('-1'), start_date=datetime.date(2025, 1, 1))
        with self.assertRaises(ValidationError):
            rate.full_clean()

    def test_overlapping_active_rates_rejected(self):
        emp = make_employee()
        make_rate(emp, Decimal('100000'), datetime.date(2025, 1, 1))
        overlapping = HourlyRate(
            employee=emp, rate=Decimal('200000'), start_date=datetime.date(2025, 2, 1),
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_non_overlapping_rates_allowed(self):
        emp = make_employee()
        make_rate(emp, Decimal('100000'), datetime.date(2025, 1, 1), end=datetime.date(2025, 1, 31))
        later = HourlyRate(
            employee=emp, rate=Decimal('200000'), start_date=datetime.date(2025, 2, 1),
        )
        later.full_clean()  # must not raise

    def test_rate_immutable_once_saved(self):
        emp = make_employee()
        rate = make_rate(emp, Decimal('100000'), datetime.date(2025, 1, 1))
        rate.rate = Decimal('999999')
        with self.assertRaises(ValueError):
            rate.save()

    def test_delete_protected(self):
        emp = make_employee()
        rate = make_rate(emp, Decimal('100000'), datetime.date(2025, 1, 1))
        with self.assertRaises(ProtectedError):
            rate.delete()

    def test_get_active_rate_for_date(self):
        emp = make_employee()
        make_rate(emp, Decimal('500000'), datetime.date(2025, 1, 1), end=datetime.date(2025, 1, 15))
        make_rate(emp, Decimal('600000'), datetime.date(2025, 1, 16))

        self.assertEqual(
            HourlyRate.get_active_rate_for_date(emp.pk, datetime.date(2025, 1, 10)),
            Decimal('500000'),
        )
        self.assertEqual(
            HourlyRate.get_active_rate_for_date(emp.pk, datetime.date(2025, 1, 20)),
            Decimal('600000'),
        )

    def test_get_active_rate_for_date_none_when_no_coverage(self):
        emp = make_employee()
        self.assertIsNone(HourlyRate.get_active_rate_for_date(emp.pk, datetime.date(2025, 1, 1)))

    def test_saving_hourly_rate_sets_payroll_config_flag(self):
        emp = make_employee()
        self.assertFalse(PayrollTypeConfig.objects.get(employee=emp).has_hourly_wage)
        make_rate(emp, Decimal('500000'), datetime.date(2025, 1, 1))
        self.assertTrue(PayrollTypeConfig.objects.get(employee=emp).has_hourly_wage)


# ---------------------------------------------------------------------------
# HourlyWorkEntry model — validation
# ---------------------------------------------------------------------------

class HourlyWorkEntryValidationTest(TestCase):

    def setUp(self):
        self.emp = make_employee()

    def test_fractional_hours_accepted(self):
        entry = make_entry(self.emp, datetime.date(2025, 1, 1), Decimal('7.5'))
        entry.full_clean()
        self.assertEqual(entry.hours_worked, Decimal('7.5'))

        entry2 = make_entry(self.emp, datetime.date(2025, 1, 2), Decimal('4.25'))
        entry2.full_clean()
        self.assertEqual(entry2.hours_worked, Decimal('4.25'))

    def test_zero_hours_rejected(self):
        entry = HourlyWorkEntry(employee=self.emp, work_date=datetime.date(2025, 1, 1), hours_worked=Decimal('0'))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_negative_hours_rejected(self):
        entry = HourlyWorkEntry(employee=self.emp, work_date=datetime.date(2025, 1, 1), hours_worked=Decimal('-1'))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_over_24_hours_rejected(self):
        entry = HourlyWorkEntry(employee=self.emp, work_date=datetime.date(2025, 1, 1), hours_worked=Decimal('24.01'))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_24_hours_exactly_allowed(self):
        entry = HourlyWorkEntry(employee=self.emp, work_date=datetime.date(2025, 1, 1), hours_worked=Decimal('24'))
        entry.full_clean()  # must not raise

    def test_multiple_entries_per_employee_allowed(self):
        make_entry(self.emp, datetime.date(2025, 1, 1), Decimal('7.5'))
        make_entry(self.emp, datetime.date(2025, 1, 2), Decimal('8'))
        make_entry(self.emp, datetime.date(2025, 1, 3), Decimal('4.25'))
        self.assertEqual(HourlyWorkEntry.objects.filter(employee=self.emp).count(), 3)

    def test_empty_form_row_does_not_create_record(self):
        # Mirrors admin-form behaviour: an unfilled ModelForm never reaches
        # .save() at all, so nothing should exist without an explicit create.
        self.assertEqual(HourlyWorkEntry.objects.count(), 0)


# ---------------------------------------------------------------------------
# finalize_hourly_payroll — the calculation service
# ---------------------------------------------------------------------------

class CalculateHourlyPayrollTest(TestCase):

    def setUp(self):
        self.emp = make_employee()
        today = datetime.date.today()
        self.jy, self.jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
        self.period = make_period(self.jy, self.jm)
        gy, gm, gd = _jalali_to_gregorian(self.jy, self.jm, 1)
        self.month_start = datetime.date(gy, gm, gd)

    def test_missing_rate_raises_validation_error(self):
        make_entry(self.emp, self.month_start, Decimal('8'))
        with self.assertRaises(ValidationError):
            finalize_hourly_payroll(self.emp, self.period)

    def test_simple_total(self):
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        make_entry(self.emp, self.month_start, Decimal('10'))
        total = finalize_hourly_payroll(self.emp, self.period)
        self.assertEqual(total, Decimal('5000000'))

    def test_rate_change_inside_period_prices_each_entry_on_its_own_date(self):
        """10h @ 500,000 + 15h @ 600,000 = 14,000,000 (per task spec example)."""
        gy, gm, gd = _jalali_to_gregorian(self.jy, self.jm, 1)
        day1 = datetime.date(gy, gm, gd)
        day2 = day1 + datetime.timedelta(days=1)

        make_rate(self.emp, Decimal('500000'), day1, end=day1)
        make_rate(self.emp, Decimal('600000'), day2)

        make_entry(self.emp, day1, Decimal('10'))
        make_entry(self.emp, day2, Decimal('15'))

        total = finalize_hourly_payroll(self.emp, self.period)
        self.assertEqual(total, Decimal('14000000'))

    def test_fractional_hours_calculation(self):
        make_rate(self.emp, Decimal('100000'), datetime.date(2020, 1, 1))
        make_entry(self.emp, self.month_start, Decimal('7.5'))
        total = finalize_hourly_payroll(self.emp, self.period)
        self.assertEqual(total, Decimal('750000'))

    def test_entries_marked_processed_after_calculation(self):
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        entry = make_entry(self.emp, self.month_start, Decimal('10'))
        finalize_hourly_payroll(self.emp, self.period)
        entry.refresh_from_db()
        self.assertTrue(entry.is_processed)
        self.assertEqual(entry.rate_used, Decimal('500000'))
        self.assertEqual(entry.amount, Decimal('5000000'))

    def test_entry_not_paid_twice(self):
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        make_entry(self.emp, self.month_start, Decimal('10'))

        first_total = finalize_hourly_payroll(self.emp, self.period)
        second_total = finalize_hourly_payroll(self.emp, self.period)

        self.assertEqual(first_total, Decimal('5000000'))
        # Nothing new to process on the second call.
        self.assertEqual(second_total, Decimal('0'))

    def test_new_entry_after_first_calculation_is_picked_up_on_recalc(self):
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        make_entry(self.emp, self.month_start, Decimal('10'))
        finalize_hourly_payroll(self.emp, self.period)

        make_entry(self.emp, self.month_start, Decimal('4'))
        second_total = finalize_hourly_payroll(self.emp, self.period)
        self.assertEqual(second_total, Decimal('2000000'))

    def test_rate_change_after_finalization_does_not_alter_processed_entry(self):
        rate = make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        entry = make_entry(self.emp, self.month_start, Decimal('10'))
        finalize_hourly_payroll(self.emp, self.period)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal('5000000'))

        # Deactivate the old rate and add a new, higher one.
        rate.is_active = False
        rate.end_date = self.month_start
        rate.save(update_fields=['is_active', 'end_date', 'updated_at'])
        make_rate(self.emp, Decimal('999999'), self.month_start + datetime.timedelta(days=60))

        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal('5000000'))
        self.assertEqual(entry.rate_used, Decimal('500000'))

    def test_processed_entry_cannot_be_edited(self):
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        entry = make_entry(self.emp, self.month_start, Decimal('10'))
        finalize_hourly_payroll(self.emp, self.period)

        entry.refresh_from_db()
        entry.hours_worked = Decimal('99')
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_processed_entry_cannot_be_deleted(self):
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        entry = make_entry(self.emp, self.month_start, Decimal('10'))
        finalize_hourly_payroll(self.emp, self.period)
        entry.refresh_from_db()
        with self.assertRaises(ProtectedError):
            entry.delete()

    def test_entries_outside_period_not_included(self):
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        outside_date = self.month_start - datetime.timedelta(days=60)
        make_entry(self.emp, outside_date, Decimal('10'))
        total = finalize_hourly_payroll(self.emp, self.period)
        self.assertEqual(total, Decimal('0'))

    def test_other_employees_entries_not_included(self):
        other = make_employee()
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        make_rate(other, Decimal('700000'), datetime.date(2020, 1, 1))
        make_entry(self.emp, self.month_start, Decimal('10'))
        make_entry(other, self.month_start, Decimal('10'))

        total = finalize_hourly_payroll(self.emp, self.period)
        self.assertEqual(total, Decimal('5000000'))


# ---------------------------------------------------------------------------
# EmployeeAdminForm — hourly wage_type selection
# ---------------------------------------------------------------------------

class EmployeeAdminFormHourlyWageTest(TestCase):

    def setUp(self):
        self.position = make_position()
        self.user = User.objects.create_superuser('hourly_form_admin', password='pass')

    def _form_data(self, **overrides):
        data = {
            'full_name': 'کارمند فرم ساعتی',
            'national_id': '9988776655',
            'gender': 'male',
            'job_position': self.position.pk,
            'start_date': '2024-01-01',
            'personal_phone': '09121112233',
            'emergency_contact_phone': '09121112244',
            'wage_type': 'hourly',
            'hourly_rate_amount': '450000',
        }
        data.update(overrides)
        return data

    def test_hourly_choice_available(self):
        labels = dict(EmployeeAdminForm.WAGE_CHOICES)
        self.assertEqual(labels.get('hourly'), 'حقوق ساعتی')

    def test_missing_rate_for_hourly_type_is_form_error(self):
        form = EmployeeAdminForm(data=self._form_data(hourly_rate_amount=''))
        self.assertFalse(form.is_valid())
        self.assertIn('hourly_rate_amount', form.errors)

    def test_valid_hourly_submission_creates_employee_and_rate(self):
        form = EmployeeAdminForm(data=self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        emp = form.save()

        from django.test import RequestFactory
        request = RequestFactory().post('/')
        request.user = self.user

        from employees.admin import EmployeeAdmin
        from django.contrib.admin.sites import AdminSite
        admin_obj = EmployeeAdmin(Employee, AdminSite())
        admin_obj._save_payroll(request, emp, form)

        rate = HourlyRate.objects.get(employee=emp, is_active=True)
        self.assertEqual(rate.rate, Decimal('450000'))
        self.assertTrue(PayrollTypeConfig.objects.get(employee=emp).has_hourly_wage)

    def test_zero_rate_is_accepted_by_form(self):
        form = EmployeeAdminForm(data=self._form_data(hourly_rate_amount='0'))
        self.assertTrue(form.is_valid(), form.errors)


# ---------------------------------------------------------------------------
# Finance integration
# ---------------------------------------------------------------------------

class HourlyPayrollFinanceIntegrationTest(TestCase):

    def setUp(self):
        self.emp = make_employee()
        self.user = User.objects.create_superuser('hourly_fin_admin', password='pass')
        today = datetime.date.today()
        self.jy, self.jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
        gy, gm, gd = _jalali_to_gregorian(self.jy, self.jm, 1)
        self.month_start = datetime.date(gy, gm, gd)

        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        make_entry(self.emp, self.month_start, Decimal('10'))

    def _hourly_expense(self, period, employee=None):
        from django.contrib.contenttypes.models import ContentType
        from finance.models import Transaction, TransactionType
        employee = employee or self.emp
        ct = ContentType.objects.get_for_model(period)
        marker = f'#emp-hourly:{employee.pk}:{period.pk}#'
        return Transaction.objects.filter(
            content_type=ct, object_id=period.pk,
            transaction_type=TransactionType.EXPENSE,
            description__contains=marker,
        )

    def test_closing_period_creates_hourly_expense(self):
        period = make_period(self.jy, self.jm)
        period.close()

        txs = self._hourly_expense(period)
        self.assertEqual(txs.count(), 1)
        tx = txs.first()
        self.assertEqual(tx.amount, Decimal('5000000'))

    def test_no_duplicate_hourly_expense_on_resync(self):
        from finance.services import PayrollFinanceService

        period = make_period(self.jy, self.jm)
        period.close()
        self.assertEqual(self._hourly_expense(period).count(), 1)

        PayrollFinanceService.sync_salary_expenses(period)
        self.assertEqual(self._hourly_expense(period).count(), 1)

    def test_new_entries_update_existing_expense_amount(self):
        from finance.services import PayrollFinanceService

        period = make_period(self.jy, self.jm)
        period.close()
        self.assertEqual(self._hourly_expense(period).first().amount, Decimal('5000000'))

        make_entry(self.emp, self.month_start, Decimal('4'))
        PayrollFinanceService.sync_salary_expenses(period)

        tx = self._hourly_expense(period).first()
        self.assertEqual(tx.amount, Decimal('7000000'))  # 5,000,000 + (4h * 500,000)

    def test_two_periods_for_same_employee_create_distinct_transactions(self):
        period_a = make_period(self.jy, self.jm)
        period_a.close()

        jy2, jm2 = previous_jalali_month(self.jy, self.jm)
        gy2, gm2, gd2 = _jalali_to_gregorian(jy2, jm2, 1)
        other_month_start = datetime.date(gy2, gm2, gd2)
        make_entry(self.emp, other_month_start, Decimal('6'))
        period_b = make_period(jy2, jm2)
        period_b.close()

        txs_a = self._hourly_expense(period_a)
        txs_b = self._hourly_expense(period_b)
        self.assertEqual(txs_a.count(), 1)
        self.assertEqual(txs_b.count(), 1)
        self.assertNotEqual(txs_a.first().pk, txs_b.first().pk)
        self.assertEqual(txs_a.first().amount, Decimal('5000000'))
        self.assertEqual(txs_b.first().amount, Decimal('3000000'))  # 6h * 500,000

    def test_resyncing_period_a_does_not_modify_period_b(self):
        from finance.services import PayrollFinanceService

        period_a = make_period(self.jy, self.jm)
        period_a.close()

        jy2, jm2 = previous_jalali_month(self.jy, self.jm)
        gy2, gm2, gd2 = _jalali_to_gregorian(jy2, jm2, 1)
        other_month_start = datetime.date(gy2, gm2, gd2)
        make_entry(self.emp, other_month_start, Decimal('6'))
        period_b = make_period(jy2, jm2)
        period_b.close()

        tx_b_before = self._hourly_expense(period_b).first()

        # Add a new entry to period A only, then resync A.
        make_entry(self.emp, self.month_start, Decimal('2'))
        PayrollFinanceService.sync_salary_expenses(period_a)

        tx_b_after = self._hourly_expense(period_b).first()
        self.assertEqual(tx_b_before.pk, tx_b_after.pk)
        self.assertEqual(tx_b_before.amount, tx_b_after.amount)
        # Period A's own transaction did pick up the new entry.
        self.assertEqual(self._hourly_expense(period_a).first().amount, Decimal('6000000'))

    def test_two_employees_in_one_period_create_separate_transactions(self):
        other = make_employee()
        make_rate(other, Decimal('700000'), datetime.date(2020, 1, 1))
        make_entry(other, self.month_start, Decimal('5'))

        period = make_period(self.jy, self.jm)
        period.close()

        tx_emp   = self._hourly_expense(period, employee=self.emp).first()
        tx_other = self._hourly_expense(period, employee=other).first()
        self.assertIsNotNone(tx_emp)
        self.assertIsNotNone(tx_other)
        self.assertNotEqual(tx_emp.pk, tx_other.pk)
        self.assertEqual(tx_emp.amount, Decimal('5000000'))
        self.assertEqual(tx_other.amount, Decimal('3500000'))  # 5h * 700,000


# ---------------------------------------------------------------------------
# Preview vs. finalization lifecycle separation
# ---------------------------------------------------------------------------

class PreviewFinalizeSeparationTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('preview_admin', password='pass')
        self.client.force_login(self.user)
        self.emp = make_employee()
        today = datetime.date.today()
        self.jy, self.jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
        gy, gm, gd = _jalali_to_gregorian(self.jy, self.jm, 1)
        self.month_start = datetime.date(gy, gm, gd)

        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        self.entry = make_entry(self.emp, self.month_start, Decimal('10'))
        self.period = make_period(self.jy, self.jm)

    def _assert_entry_untouched(self):
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_processed)
        self.assertIsNone(self.entry.rate_used)
        self.assertIsNone(self.entry.amount)
        self.assertIsNone(self.entry.payroll_period_id)

    def test_preview_service_does_not_mutate_entries(self):
        result = preview_hourly_payroll(self.emp, self.period)
        self.assertEqual(result['total_amount'], Decimal('5000000'))
        self._assert_entry_untouched()

    def test_preview_called_repeatedly_stays_non_mutating(self):
        preview_hourly_payroll(self.emp, self.period)
        preview_hourly_payroll(self.emp, self.period)
        preview_hourly_payroll(self.emp, self.period)
        self._assert_entry_untouched()

    def test_preview_creates_no_finance_transaction(self):
        from finance.models import Transaction
        preview_hourly_payroll(self.emp, self.period)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_report_api_read_does_not_process_entries(self):
        """Opening/refreshing the payroll report page must never finalize."""
        resp = self.client.get('/api/v2/payroll/report/', {
            'year': self.jy, 'month': self.jm,
        })
        self.assertEqual(resp.status_code, 200)
        self._assert_entry_untouched()

    def test_employee_cost_report_read_does_not_process_entries(self):
        resp = self.client.get('/api/v2/payroll/reports/employee-cost/', {
            'wage_type': 'hourly',
        })
        self.assertEqual(resp.status_code, 200)
        self._assert_entry_untouched()

    def test_calculate_api_action_is_read_only(self):
        """POST .../hourly-work-entries/calculate/ is a preview endpoint —
        must not process entries or create a PayrollPeriod row."""
        period_count_before = PayrollPeriod.objects.count()

        resp = self.client.post('/api/v2/payroll/hourly-work-entries/calculate/', {
            'employee': self.emp.pk, 'year': self.jy, 'month': self.jm,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.data['total_amount']), Decimal('5000000'))

        self._assert_entry_untouched()
        self.assertEqual(PayrollPeriod.objects.count(), period_count_before)

    def test_calculate_api_action_creates_no_finance_transaction(self):
        from finance.models import Transaction
        self.client.post('/api/v2/payroll/hourly-work-entries/calculate/', {
            'employee': self.emp.pk, 'year': self.jy, 'month': self.jm,
        })
        self.assertEqual(Transaction.objects.count(), 0)

    def test_only_period_close_finalizes_and_syncs_finance(self):
        from finance.models import Transaction

        # Repeated previews first — must not have finalized anything.
        preview_hourly_payroll(self.emp, self.period)
        preview_hourly_payroll(self.emp, self.period)
        self._assert_entry_untouched()
        self.assertEqual(Transaction.objects.count(), 0)

        # The only trigger that finalizes + syncs Finance.
        self.period.close()

        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_processed)
        self.assertEqual(self.entry.amount, Decimal('5000000'))
        self.assertEqual(Transaction.objects.count(), 1)

    def test_finalization_is_idempotent_and_never_double_pays(self):
        finalize_hourly_payroll(self.emp, self.period)
        self.entry.refresh_from_db()
        snapshot_amount = self.entry.amount

        # Repeated finalize calls (simulating repeated/concurrent close calls)
        second_total = finalize_hourly_payroll(self.emp, self.period)
        third_total  = finalize_hourly_payroll(self.emp, self.period)

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.amount, snapshot_amount)
        self.assertEqual(second_total, Decimal('0'))
        self.assertEqual(third_total, Decimal('0'))


# ---------------------------------------------------------------------------
# Payroll report — hourly totals
# ---------------------------------------------------------------------------

class HourlyPayrollReportTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('hourly_report_admin', password='pass')
        self.client.force_login(self.user)
        self.emp = make_employee()
        today = datetime.date.today()
        self.jy, self.jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
        gy, gm, gd = _jalali_to_gregorian(self.jy, self.jm, 1)
        self.month_start = datetime.date(gy, gm, gd)

        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        make_entry(self.emp, self.month_start, Decimal('10'))
        period = make_period(self.jy, self.jm)
        finalize_hourly_payroll(self.emp, period)

    def test_report_includes_total_hourly_salary(self):
        resp = self.client.get('/api/v2/payroll/report/', {
            'year': self.jy, 'month': self.jm,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.data['total_hourly_salary']), Decimal('5000000'))
        self.assertEqual(Decimal(resp.data['total_hours_worked']), Decimal('10'))

    def test_report_employee_row_includes_hourly_fields(self):
        resp = self.client.get('/api/v2/payroll/report/', {
            'year': self.jy, 'month': self.jm, 'employee': self.emp.pk,
        })
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(row['hourly_salary']), Decimal('5000000'))
        self.assertEqual(Decimal(row['total_hours_worked']), Decimal('10'))
        self.assertEqual(Decimal(row['total_payment']), Decimal('5000000'))

    def test_report_wage_type_hourly_filter(self):
        resp = self.client.get('/api/v2/payroll/report/', {'wage_type': 'hourly'})
        self.assertEqual(resp.status_code, 200)
        emp_ids = [row['employee_id'] for row in resp.data['employees']]
        self.assertIn(self.emp.pk, emp_ids)

    def test_employee_cost_report_includes_hourly(self):
        resp = self.client.get('/api/v2/payroll/reports/employee-cost/', {
            'wage_type': 'hourly',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.data['metadata']['total_hourly_wages']), Decimal('5000000'))
        result = next(r for r in resp.data['results'] if r['employee_id'] == self.emp.pk)
        self.assertEqual(Decimal(result['total_hourly_wages']), Decimal('5000000'))


# ---------------------------------------------------------------------------
# Regression — existing monthly / commission behaviour unaffected
# ---------------------------------------------------------------------------

class MonthlyAndCommissionRegressionTest(TestCase):

    def test_payroll_type_config_still_valid_with_only_monthly(self):
        from payroll.models import MonthlyWage
        emp = make_employee()
        MonthlyWage.objects.create(
            employee=emp, amount=Decimal('3000000'), start_date=datetime.date(2024, 1, 1),
        )
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        self.assertTrue(cfg.has_monthly_wage)
        self.assertFalse(cfg.has_hourly_wage)
        cfg.full_clean()  # must not raise — monthly alone still satisfies clean()

    def test_employee_with_only_hourly_satisfies_config_clean(self):
        emp = make_employee()
        make_rate(emp, Decimal('400000'), datetime.date(2024, 1, 1))
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        cfg.full_clean()  # must not raise


# ---------------------------------------------------------------------------
# Finance transaction identity — unique per (employee, payroll period)
# ---------------------------------------------------------------------------

class HourlyFinanceTransactionMarkerTest(TestCase):

    def test_marker_embeds_both_employee_and_period_id(self):
        from finance.services import PayrollFinanceService

        emp = make_employee()
        make_rate(emp, Decimal('500000'), datetime.date(2020, 1, 1))
        today = datetime.date.today()
        jy, jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
        gy, gm, gd = _jalali_to_gregorian(jy, jm, 1)
        make_entry(emp, datetime.date(gy, gm, gd), Decimal('10'))
        period = make_period(jy, jm)
        period.close()

        from finance.models import Transaction
        tx = Transaction.objects.get(
            category__name=PayrollFinanceService.HOURLY_CATEGORY_NAME,
            description__contains=f'#emp-hourly:{emp.pk}:{period.pk}#',
        )
        self.assertIn(f'#emp-hourly:{emp.pk}:{period.pk}#', tx.description)


# ---------------------------------------------------------------------------
# Admin/API-level immutability of processed HourlyWorkEntry rows
# ---------------------------------------------------------------------------

class HourlyWorkEntryImmutabilityTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('immut_admin', password='pass')
        self.client.force_login(self.user)
        self.emp = make_employee()
        make_rate(self.emp, Decimal('500000'), datetime.date(2020, 1, 1))
        today = datetime.date.today()
        self.jy, self.jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
        gy, gm, gd = _jalali_to_gregorian(self.jy, self.jm, 1)
        self.month_start = datetime.date(gy, gm, gd)
        self.entry = make_entry(self.emp, self.month_start, Decimal('10'))
        self.period = make_period(self.jy, self.jm)
        finalize_hourly_payroll(self.emp, self.period)
        self.entry.refresh_from_db()

    def test_api_delete_of_processed_entry_is_rejected(self):
        resp = self.client.delete(f'/api/v2/payroll/hourly-work-entries/{self.entry.pk}/')
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(HourlyWorkEntry.objects.filter(pk=self.entry.pk).exists())

    def test_api_patch_of_processed_entry_hours_is_rejected(self):
        resp = self.client.patch(
            f'/api/v2/payroll/hourly-work-entries/{self.entry.pk}/',
            {'hours_worked': '99'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.hours_worked, Decimal('10'))

    def test_admin_delete_view_of_processed_entry_is_blocked(self):
        resp = self.client.post(
            f'/admin/payroll/hourlyworkentry/{self.entry.pk}/delete/', {'post': 'yes'},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(HourlyWorkEntry.objects.filter(pk=self.entry.pk).exists())

    def test_admin_bulk_delete_action_not_offered(self):
        """The bulk 'Delete selected' action bypasses obj.delete() and the
        per-object permission check, so it must not be offered at all for
        this model (see HourlyWorkEntryAdmin.get_actions)."""
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        from payroll.models import HourlyWorkEntry as _HWE
        model_admin = site._registry[_HWE]
        request = RequestFactory().get('/admin/payroll/hourlyworkentry/')
        request.user = self.user
        actions = model_admin.get_actions(request)
        self.assertNotIn('delete_selected', actions)

    def test_admin_changelist_bulk_delete_post_does_not_delete_processed_row(self):
        """Even if a 'delete_selected' POST were forged, the action isn't
        registered, so Django admin has no route to execute it."""
        resp = self.client.post('/admin/payroll/hourlyworkentry/', {
            'action': 'delete_selected',
            '_selected_action': [str(self.entry.pk)],
        })
        self.assertTrue(HourlyWorkEntry.objects.filter(pk=self.entry.pk).exists())
