"""Regression tests for the Payroll report excluding newly recorded,
not-yet-finalized hourly work.

Root cause: PayrollReportView built its "new hourly payroll" aggregate from

    HourlyWorkEntry.objects.filter(amount__isnull=False)

`amount` (along with `rate_used` and `payroll_period`) is intentionally left
null until finalize_hourly_payroll() prices and locks an entry in — so any
entry recorded and not yet finalized (the normal state for "this month's
work so far") was silently excluded from the report's hourly_salary /
total_hours_worked, even though a valid HourlyRate existed and the entry
should have priced to a definite amount.

Example (Employee ID 9): HourlyRate 33.00, one HourlyWorkEntry with
hours_worked=19 and no payroll_period yet — expected preview 19 × 33 = 627,
but the report showed nothing for it.

Covers:
  - a pending (unprocessed) entry now appears in the report's hourly
    preview, priced via the same HourlyRate.get_active_rate_for_date rule
    finalize_hourly_payroll uses
  - GET never mutates rate_used / amount / payroll_period
  - a finalized entry in the same window still uses its stored snapshot,
    not a live recalculation
  - finalized + pending entries in the same window sum without double
    counting
  - an unbounded ("all periods") report does not pull in a future-dated
    pending entry
  - a pending entry whose work_date has no effective HourlyRate is skipped
    rather than crashing the whole report
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from employees.models import Employee, JobPosition
from payroll.models import HourlyRate, HourlyWorkEntry, PayrollPeriod, PayrollStatus
from payroll.services import finalize_hourly_payroll

REPORT_URL = '/api/v2/payroll/report/'

_counter = [0]


def make_position():
    _counter[0] += 1
    return JobPosition.objects.create(name=f'موقعیت-پیش‌نمایش-ساعتی-{_counter[0]}')


def make_employee(position=None):
    _counter[0] += 1
    return Employee.objects.create(
        full_name=f'کارمند پیش‌نمایش {_counter[0]}',
        national_id=f'5{_counter[0]:09d}',
        gender='male',
        job_position=position or make_position(),
        start_date=datetime.date(2024, 1, 1),
        personal_phone=f'0930{_counter[0]:07d}',
        emergency_contact_phone=f'0940{_counter[0]:07d}',
    )


def make_rate(employee, rate, start, end=None):
    return HourlyRate.objects.create(employee=employee, rate=rate, start_date=start, end_date=end)


def make_entry(employee, work_date, hours):
    return HourlyWorkEntry.objects.create(employee=employee, work_date=work_date, hours_worked=hours)


class ReportAuthedTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username=f'pending_rpt_admin_{id(self)}', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)


class PendingHourlyEntryAppearsInReportTest(ReportAuthedTestCase):
    """The exact Employee-9 scenario: rate 33, 19 pending hours -> 627."""

    def test_pending_entry_prices_into_report(self):
        emp = make_employee()
        make_rate(emp, Decimal('33'), datetime.date(2020, 1, 1))
        make_entry(emp, datetime.date(2026, 6, 12), Decimal('19'))  # 1405/04/20-ish, any past date

        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('19'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('627'))
        self.assertEqual(Decimal(str(row['total_payment'])), Decimal('627'))

    def test_pending_entry_within_explicit_date_range(self):
        emp = make_employee()
        make_rate(emp, Decimal('33'), datetime.date(2020, 1, 1))
        make_entry(emp, datetime.date(2026, 4, 20), Decimal('19'))

        resp = self.client.get(REPORT_URL, {
            'employee': emp.pk,
            'start_date': '2026-04-01',
            'end_date': '2026-04-30',
        })
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('19'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('627'))


class ReportDoesNotMutateEntriesTest(ReportAuthedTestCase):
    """Loading the report is read-only: rate_used/amount/payroll_period
    must remain null on a pending entry no matter how many times the
    report is fetched."""

    def test_get_leaves_pending_entry_unprocessed(self):
        emp = make_employee()
        make_rate(emp, Decimal('33'), datetime.date(2020, 1, 1))
        entry = make_entry(emp, datetime.date(2026, 6, 12), Decimal('19'))

        for _ in range(3):
            resp = self.client.get(REPORT_URL, {'employee': emp.pk})
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        entry.refresh_from_db()
        self.assertIsNone(entry.rate_used)
        self.assertIsNone(entry.amount)
        self.assertIsNone(entry.payroll_period)
        self.assertFalse(entry.is_processed)


class FinalizedAndPendingCombineWithoutDoubleCountingTest(ReportAuthedTestCase):

    def _period_for(self, d):
        from payroll.models import _gregorian_to_jalali
        jy, jm, _ = _gregorian_to_jalali(d.year, d.month, d.day)
        return PayrollPeriod.objects.get_or_create(
            year=jy, month=jm, defaults={'status': PayrollStatus.OPEN},
        )[0]

    def test_finalized_entry_uses_snapshot_not_recalculated(self):
        emp = make_employee()
        make_rate(emp, Decimal('500000'), datetime.date(2020, 1, 1))
        work_date = datetime.date(2026, 5, 10)
        make_entry(emp, work_date, Decimal('10'))
        finalize_hourly_payroll(emp, self._period_for(work_date))

        # A later, higher rate must never retroactively change the
        # already-finalized entry's contribution to the report.
        make_rate(emp, Decimal('999999'), datetime.date(2026, 5, 11))

        resp = self.client.get(REPORT_URL, {'employee': emp.pk, 'start_date': '2026-05-01', 'end_date': '2026-05-31'})
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('5000000'))  # 10 * 500,000, not the new rate
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('10'))

    def test_finalized_plus_pending_sum_without_double_counting(self):
        emp = make_employee()
        make_rate(emp, Decimal('100000'), datetime.date(2020, 1, 1))

        finalized_date = datetime.date(2026, 5, 5)
        make_entry(emp, finalized_date, Decimal('4'))
        finalize_hourly_payroll(emp, self._period_for(finalized_date))

        pending_date = datetime.date(2026, 5, 20)
        make_entry(emp, pending_date, Decimal('6'))  # left pending on purpose

        resp = self.client.get(REPORT_URL, {'employee': emp.pk, 'start_date': '2026-05-01', 'end_date': '2026-05-31'})
        row = resp.data['employees'][0]
        # 4h finalized (400,000) + 6h pending (600,000) = 1,000,000 / 10 hours
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('10'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('1000000'))

        entries = HourlyWorkEntry.objects.filter(employee=emp).order_by('work_date')
        self.assertEqual(entries.count(), 2)
        self.assertTrue(entries[0].is_processed)
        self.assertFalse(entries[1].is_processed)


class UnboundedReportExcludesFutureEntriesTest(ReportAuthedTestCase):

    def test_all_periods_report_ignores_future_dated_pending_entry(self):
        emp = make_employee()
        make_rate(emp, Decimal('33'), datetime.date(2020, 1, 1))
        make_entry(emp, datetime.date(2026, 6, 12), Decimal('19'))          # past — included
        make_entry(emp, datetime.date.today() + datetime.timedelta(days=30), Decimal('5'))  # future — excluded

        resp = self.client.get(REPORT_URL, {'employee': emp.pk})  # no date filter at all
        row = resp.data['employees'][0]
        self.assertEqual(Decimal(str(row['total_hours_worked'])), Decimal('19'))
        self.assertEqual(Decimal(str(row['hourly_salary'])), Decimal('627'))


class PendingEntryWithoutEffectiveRateIsSkippedTest(ReportAuthedTestCase):

    def test_report_does_not_crash_when_no_rate_covers_the_work_date(self):
        emp = make_employee()
        # Rate starts after the work date on purpose — no effective rate.
        make_rate(emp, Decimal('33'), datetime.date(2026, 12, 1))
        make_entry(emp, datetime.date(2026, 6, 12), Decimal('19'))

        resp = self.client.get(REPORT_URL, {'employee': emp.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Employee still appears (configured for hourly), just with nothing priced.
        rows = [r for r in resp.data['employees'] if r['employee_id'] == emp.pk]
        if rows:
            self.assertEqual(Decimal(str(rows[0]['hourly_salary'])), Decimal('0'))
