"""Payroll service layer.

calculate_surgery_commission: given a SurgeryHistory instance, identifies
the involved employee (doctor_or_therapist), looks up the active CommissionRule
for their job position × surgery type, and creates / skips a CommissionTransaction.

One transaction per (surgery, employee, rule) — the unique constraint on
CommissionTransaction prevents duplicates even if the signal fires twice.

preview_hourly_payroll / finalize_hourly_payroll: two read/write-separated
entry points over the same pricing logic for an employee's unprocessed
HourlyWorkEntry rows inside a PayrollPeriod, priced using the HourlyRate
effective on each entry's own work_date.

  - preview_hourly_payroll  — read-only. Never writes to the database. Safe
    to call from GET requests, report rendering, or any "show me the
    calculation" UI action, as many times as needed.
  - preview_pending_hourly_totals — same read-only pricing, but grouped by
    employee over an already-fetched, arbitrary-date-range queryset (rather
    than a single employee + PayrollPeriod) — what the multi-employee
    payroll report uses to fold pending hours into its hourly preview.
  - finalize_hourly_payroll — the only function that snapshots rate_used/
    amount onto each entry and links payroll_period, i.e. the only one that
    can ever mark a work entry "processed". Called exactly once per period
    close, from finance.services.PayrollFinanceService._sync_hourly_expenses
    (itself only triggered by the PayrollPeriod CLOSED/PROCESSED lifecycle —
    there is no separate finalize-hourly-payroll HTTP endpoint; finalization
    rides on the same PayrollPeriod.close() lifecycle as MonthlyWage and
    CommissionTransaction).

Both raise ValidationError (Persian message) if any in-range entry has no
HourlyRate effective on its work_date, and both are idempotent: entries
already linked to a payroll_period (payroll_period is not null) are excluded
from consideration, so finalizing twice never re-prices, re-sums, or re-pays
an already-processed entry, and a rate change after finalization can never
alter the frozen rate_used/amount on a processed entry.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction


def calculate_surgery_commission(surgery_history) -> list:
    """Calculate and persist commission transactions for one SurgeryHistory.

    Args:
        surgery_history: a surgeries.SurgeryHistory instance.

    Returns:
        A list of CommissionTransaction instances that were created.
        Already-existing transactions are silently skipped (idempotent).

    Skips silently when:
      - No doctor_or_therapist is assigned to the surgery.
      - No active CommissionRule exists for the employee's job position +
        surgery type combination.
    """
    from payroll.models import CommissionRule, CommissionTransaction  # avoid circular import

    created = []

    employee = surgery_history.doctor_or_therapist
    if employee is None:
        return created

    rule = CommissionRule.get_active_rule(
        job_position_id=employee.job_position_id,
        surgery_type_id=surgery_history.surgery_type_id,
    )
    if rule is None:
        return created

    amount = (surgery_history.amount * rule.commission_percent / Decimal('100')).quantize(
        Decimal('0.01')
    )

    try:
        with transaction.atomic():
            ct = CommissionTransaction.objects.create(
                surgery=surgery_history,
                employee=employee,
                commission_rule=rule,
                amount=amount,
                notes=(
                    f'کمیسیون خودکار — عمل #{surgery_history.pk} '
                    f'({surgery_history.surgery_type.name}) '
                    f'{rule.commission_percent}%'
                ),
            )
            created.append(ct)
    except IntegrityError:
        # Duplicate (surgery, employee, rule) — already calculated, skip.
        pass

    return created


def _eligible_hourly_entries_qs(employee, period):
    """Unprocessed HourlyWorkEntry rows for `employee` whose work_date falls
    inside `period`'s Jalali month — the shared candidate set for both
    preview and finalization. Callers add .select_for_update() themselves
    when locking is needed (finalization only)."""
    from .models import HourlyWorkEntry, _jalali_days_in_month, _jalali_to_gregorian
    import datetime

    last_day   = _jalali_days_in_month(period.year, period.month)
    first_greg = datetime.date(*_jalali_to_gregorian(period.year, period.month, 1))
    last_greg  = datetime.date(*_jalali_to_gregorian(period.year, period.month, last_day))

    return HourlyWorkEntry.objects.filter(
        employee=employee,
        payroll_period__isnull=True,
        work_date__gte=first_greg,
        work_date__lte=last_greg,
    )


def _price_hourly_entries(employee, entries):
    """Price each entry using the HourlyRate effective on its own work_date.

    Pure function — takes already-fetched entries, returns
    [(entry, rate, amount), ...] plus the total, without touching the
    database. Raises ValidationError (Persian message) if any entry has no
    effective rate.
    """
    from .models import HourlyRate

    total  = Decimal('0')
    priced = []
    for entry in entries:
        rate = HourlyRate.get_active_rate_for_date(employee.pk, entry.work_date)
        if rate is None:
            raise ValidationError(
                f'برای تاریخ {entry.work_date} نرخ ساعتی فعالی برای '
                f'{employee.full_name} یافت نشد.'
            )
        amount = (entry.hours_worked * rate).quantize(Decimal('1'))
        priced.append((entry, rate, amount))
        total += amount
    return priced, total


def preview_hourly_payroll(employee, period) -> dict:
    """Read-only calculation: what finalize_hourly_payroll *would* do,
    without writing anything. Never sets rate_used/amount/payroll_period on
    any entry, never touches Finance. Safe to call as often as needed (page
    opens, refreshes, GET/preview API requests).

    Returns {'total_amount': Decimal, 'total_hours': Decimal, 'entries': [
        {'entry_id', 'work_date', 'hours_worked', 'rate', 'amount'}, ...
    ]}.
    """
    entries = list(_eligible_hourly_entries_qs(employee, period))
    priced, total = _price_hourly_entries(employee, entries)
    total_hours = sum((entry.hours_worked for entry in entries), Decimal('0'))

    return {
        'total_amount': total,
        'total_hours':  total_hours,
        'entries': [
            {
                'entry_id':     entry.pk,
                'work_date':    entry.work_date,
                'hours_worked': entry.hours_worked,
                'rate':         rate,
                'amount':       amount,
            }
            for entry, rate, amount in priced
        ],
    }


def preview_pending_hourly_totals(pending_entries) -> dict:
    """Group already-fetched, unprocessed HourlyWorkEntry rows by employee
    and price each using the HourlyRate effective on its own work_date —
    the same per-entry pricing rule finalize_hourly_payroll uses, without
    writing anything. Used by the multi-employee payroll report (which
    spans an arbitrary date range, not a single PayrollPeriod) to fold
    pending work into the hourly preview alongside already-finalized totals.

    Unlike _price_hourly_entries (used by the single-employee preview/
    finalize path, which raises if any entry has no effective rate), an
    entry with no effective rate is left out of both totals here rather
    than failing the whole report over one employee's data gap — this
    function only ever aggregates for display, it never blocks a save.

    Returns {employee_id: {'hours': Decimal, 'salary': Decimal}}.
    """
    from .models import HourlyRate

    totals = {}
    for entry in pending_entries:
        rate = HourlyRate.get_active_rate_for_date(entry.employee_id, entry.work_date)
        if rate is None:
            continue
        amount = (entry.hours_worked * rate).quantize(Decimal('1'))
        bucket = totals.setdefault(entry.employee_id, {'hours': Decimal('0'), 'salary': Decimal('0')})
        bucket['hours']  += entry.hours_worked
        bucket['salary'] += amount
    return totals


@transaction.atomic
def finalize_hourly_payroll(employee, period) -> Decimal:
    """Price, snapshot, and lock in this employee's unprocessed
    HourlyWorkEntry rows inside `period`; returns the total hourly salary
    (Decimal) for the entries processed by *this* call.

    The only function that ever sets rate_used/amount/payroll_period — once
    it does, an entry is permanently excluded from every future preview or
    finalize call (for this or any other period), which is what prevents an
    entry from ever being paid twice and keeps a finalized payroll immune to
    later HourlyRate changes.

    select_for_update() locks the candidate rows for the duration of this
    atomic transaction: a concurrent finalize call for the same employee/
    period blocks until this one commits, then re-evaluates
    payroll_period__isnull=True against the now-committed rows and finds
    none of them eligible anymore — so two concurrent/repeated finalizations
    can never both price the same entry. (SQLite has no real row-level
    locking — select_for_update() is a silent no-op there per Django, but
    SQLite's own connection-level write serialization gives the same
    end result for a single-process dev server.)

    Raises ValidationError the same way preview_hourly_payroll does.
    """
    entries = list(_eligible_hourly_entries_qs(employee, period).select_for_update())
    priced, total = _price_hourly_entries(employee, entries)

    for entry, rate, amount in priced:
        entry.rate_used      = rate
        entry.amount         = amount
        entry.payroll_period = period
        entry.save(update_fields=['rate_used', 'amount', 'payroll_period', 'updated_at'])

    return total
