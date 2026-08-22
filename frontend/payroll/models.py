import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum
from django.db.models.deletion import ProtectedError
from django.utils import timezone


# ---------------------------------------------------------------------------
# Jalali helpers
# ---------------------------------------------------------------------------

PERSIAN_MONTHS = {
    1: 'فروردین',  2: 'اردیبهشت', 3: 'خرداد',
    4: 'تیر',      5: 'مرداد',    6: 'شهریور',
    7: 'مهر',      8: 'آبان',     9: 'آذر',
    10: 'دی',      11: 'بهمن',    12: 'اسفند',
}


_JALALI_LEAP_REMAINDERS = frozenset({1, 5, 9, 13, 17, 22, 26, 30})


def _is_jalali_leap(jy):
    """True if jy is a Jalali leap year. Uses 33-year cycle rule."""
    return jy % 33 in _JALALI_LEAP_REMAINDERS


def _jalali_days_in_month(jy, jm):
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if _is_jalali_leap(jy) else 29


def _jalali_to_gregorian(jy, jm, jd):
    """Convert Jalali to Gregorian date. Pure Python, no deps.

    Verified: 1404/01/01 → 2025/03/21.
    """
    jy -= 979
    jm -= 1
    jd -= 1

    j_day_no = 365 * jy + (jy // 33) * 8 + (jy % 33 + 3) // 4
    for i in range(jm):
        j_day_no += [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29][i]
    j_day_no += jd

    g_day_no = j_day_no + 79

    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097

    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False

    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461

    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365

    g_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for i, d in enumerate(g_days):
        if g_day_no < d:
            return gy, i + 1, g_day_no + 1
        g_day_no -= d

    return gy, 12, g_day_no + 1


def _gregorian_to_jalali(gy, gm, gd):
    """Convert Gregorian date to Jalali (Solar Hijri). Pure Python, no deps.

    Every 33 Jalali years = 12053 days; every 4-year sub-cycle = 1461 days.
    Verified: 2025-03-21 → 1404/01/01.
    """
    year  = gy - 1600
    month = gm - 1
    day   = gd - 1

    g_day_no = (
        365 * year
        + (year + 3) // 4
        - (year + 99) // 100
        + (year + 399) // 400
    )
    for i in range(month):
        g_day_no += [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][i]
    if month > 1 and (
        (year % 4 == 0 and year % 100 != 0) or (year + 1600) % 400 == 0
    ):
        g_day_no += 1
    g_day_no += day

    j_day_no = g_day_no - 79

    j_np      = j_day_no // 12053
    j_day_no %= 12053

    jy        = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy      += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    for i in range(11):
        j_mi = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30][i]
        if j_day_no >= j_mi:
            j_day_no -= j_mi
        else:
            return jy, i + 1, j_day_no + 1

    return jy, 12, j_day_no - 29


# ---------------------------------------------------------------------------
# PayrollStatus
# ---------------------------------------------------------------------------

class PayrollStatus(models.TextChoices):
    OPEN      = 'OPEN',      'باز'
    CLOSED    = 'CLOSED',    'بسته'
    PROCESSED = 'PROCESSED', 'پردازش‌شده'


# ---------------------------------------------------------------------------
# PayrollPeriod
# ---------------------------------------------------------------------------

class PayrollPeriod(models.Model):
    year     = models.PositiveIntegerField(verbose_name='سال')
    month    = models.PositiveIntegerField(verbose_name='ماه')
    status   = models.CharField(
        max_length=10,
        choices=PayrollStatus.choices,
        default=PayrollStatus.OPEN,
        verbose_name='وضعیت',
    )
    notes     = models.TextField(blank=True, verbose_name='توضیحات')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    closed_at  = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ بسته شدن')

    class Meta:
        verbose_name        = 'دوره حقوقی'
        verbose_name_plural = 'دوره‌های حقوقی'
        unique_together     = [('year', 'month')]
        ordering            = ['-year', '-month']

    def __str__(self):
        return f'{self.year}/{self.month:02d}'

    @property
    def display_name(self):
        return f'{PERSIAN_MONTHS[self.month]} {self.year}'

    @transaction.atomic
    def close(self):
        if self.status != PayrollStatus.OPEN:
            raise ValidationError('فقط دوره‌های باز را می‌توان بست.')
        self.status    = PayrollStatus.CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=['status', 'closed_at'])

    @classmethod
    def get_or_create_current(cls):
        today = datetime.date.today()
        jy, jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
        obj, _ = cls.objects.get_or_create(
            year=jy, month=jm,
            defaults={'status': PayrollStatus.OPEN},
        )
        return obj


# ---------------------------------------------------------------------------
# PayrollTypeConfig
# ---------------------------------------------------------------------------

class PayrollTypeConfig(models.Model):
    employee          = models.OneToOneField(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='payroll_config',
        verbose_name='کارمند',
    )
    has_monthly_wage  = models.BooleanField(default=False, verbose_name='دارای حقوق ثابت')
    has_commission    = models.BooleanField(default=False, verbose_name='دارای کمیسیون')
    has_hourly_wage   = models.BooleanField(default=False, verbose_name='دارای حقوق ساعتی')
    notes             = models.TextField(blank=True, verbose_name='توضیحات')
    updated_at        = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'تنظیمات حقوقی'
        verbose_name_plural = 'تنظیمات حقوقی'
        ordering            = ['employee__full_name']

    def __str__(self):
        return f'{self.employee.full_name} — payroll config'

    def clean(self):
        # Only enforce on updates (pk exists).
        # Auto-created records (pk=None, via signal) are exempt and represent
        # "not yet configured" state — both flags False is valid at creation.
        if self.pk is not None and not self.has_monthly_wage and not self.has_commission and not self.has_hourly_wage:
            raise ValidationError(
                'حداقل یکی از گزینه‌های حقوق ثابت، کمیسیون یا حقوق ساعتی باید فعال باشد.'
            )


# ---------------------------------------------------------------------------
# MonthlyWage
# ---------------------------------------------------------------------------

class MonthlyWage(models.Model):
    employee   = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='monthly_wages',
        verbose_name='کارمند',
    )
    amount     = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='مبلغ حقوق')
    start_date = models.DateField(verbose_name='تاریخ شروع')
    end_date   = models.DateField(null=True, blank=True, verbose_name='تاریخ پایان')
    is_active  = models.BooleanField(default=True, verbose_name='فعال')
    notes      = models.TextField(blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_wages',
        verbose_name='ایجاد شده توسط',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'حقوق ماهیانه'
        verbose_name_plural = 'حقوق ماهیانه'
        ordering            = ['-start_date']
        indexes             = [
            models.Index(fields=['employee']),
            models.Index(fields=['is_active']),
            models.Index(fields=['start_date']),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store original amount via __dict__ to avoid triggering deferred field
        # access. If amount is deferred (e.g. .only() without amount), this is
        # None and the immutability guard in save() is skipped safely.
        self.__original_amount = self.__dict__.get('amount')

    def __str__(self):
        return f'{self.employee.full_name} — {self.amount:,} ریال'

    def clean(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'تاریخ پایان باید بعد از تاریخ شروع باشد.'})

        # Overlap: two active wages overlap when neither has ended before the
        # other starts.
        #   existing still running when self starts:
        #     end_date IS NULL  OR  end_date >= self.start_date
        #   existing started before self ends:
        #     start_date <= self.end_date  (or self is open-ended → always True)
        cond_existing_running = (
            Q(end_date__isnull=True) | Q(end_date__gte=self.start_date)
        )
        cond_self_not_ended = (
            Q(start_date__lte=self.end_date) if self.end_date is not None else Q()
        )
        qs = MonthlyWage.objects.filter(
            employee=self.employee,
            is_active=True,
        ).filter(cond_existing_running).filter(cond_self_not_ended)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if qs.exists():
            raise ValidationError(
                'این کارمند در این بازه زمانی دارای حقوق فعال دیگری است.'
            )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = self.__original_amount
            current  = self.__dict__.get('amount')
            if original is not None and current is not None and original != current:
                raise ValueError(
                    'حقوق ماهیانه قابل ویرایش نیست. '
                    'رکورد قدیمی را غیرفعال کنید و رکورد جدید ایجاد کنید.'
                )
        super().save(*args, **kwargs)
        self.__original_amount = self.__dict__.get('amount')

    def delete(self, *args, **kwargs):
        # CLI-29: when PayrollEntry is added, check for references here:
        # from payroll.models import PayrollEntry
        # if PayrollEntry.objects.filter(monthly_wage=self).exists():
        #     raise ProtectedError("...", {self})
        raise ProtectedError(
            'حذف حقوق ماهیانه مجاز نیست. رکورد را غیرفعال کنید.',
            {self},
        )

    # ── Period helpers ────────────────────────────────────────────

    def is_active_for_period(self, year: int, month: int) -> bool:
        if not self.is_active:
            return False
        last_day   = _jalali_days_in_month(year, month)
        first_greg = datetime.date(*_jalali_to_gregorian(year, month, 1))
        last_greg  = datetime.date(*_jalali_to_gregorian(year, month, last_day))
        if self.start_date > last_greg:
            return False
        if self.end_date is not None and self.end_date < first_greg:
            return False
        return True

    @classmethod
    def get_total_for_period(cls, year: int, month: int) -> Decimal:
        """Total monthly wage cost for a Jalali year/month period."""
        last_day   = _jalali_days_in_month(year, month)
        first_greg = datetime.date(*_jalali_to_gregorian(year, month, 1))
        last_greg  = datetime.date(*_jalali_to_gregorian(year, month, last_day))
        result = cls.objects.filter(
            is_active=True,
            start_date__lte=last_greg,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=first_greg)
        ).aggregate(total=Sum('amount'))['total']
        return result or Decimal('0')


# ---------------------------------------------------------------------------
# HourlyRate — effective-dated hourly wage rate per employee
#
# Mirrors MonthlyWage's pattern (effective dates, immutable rate once saved,
# overlap prevention, deactivate-then-recreate to change). This is the
# historical rate source for the new HourlyWorkEntry-based hourly payroll —
# distinct from the pre-existing Employee.hourly_rate / HourlyWorkRecord
# (a single flat rate + manually-entered monthly total, kept unchanged for
# backward compatibility).
# ---------------------------------------------------------------------------

class HourlyRate(models.Model):
    employee   = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='hourly_rates',
        verbose_name='کارمند',
    )
    rate       = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='نرخ هر ساعت')
    start_date = models.DateField(verbose_name='تاریخ شروع')
    end_date   = models.DateField(null=True, blank=True, verbose_name='تاریخ پایان')
    is_active  = models.BooleanField(default=True, verbose_name='فعال')
    notes      = models.TextField(blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_hourly_rates',
        verbose_name='ایجاد شده توسط',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'نرخ ساعتی'
        verbose_name_plural = 'نرخ‌های ساعتی'
        ordering            = ['-start_date']
        indexes             = [
            models.Index(fields=['employee']),
            models.Index(fields=['is_active']),
            models.Index(fields=['start_date']),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_rate = self.__dict__.get('rate')

    def __str__(self):
        return f'{self.employee.full_name} — {self.rate:,} تومان/ساعت'

    def clean(self):
        if self.rate is not None and self.rate < 0:
            raise ValidationError({'rate': 'نرخ هر ساعت نمی‌تواند منفی باشد.'})

        if self.end_date is not None and self.start_date is not None and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'تاریخ پایان باید بعد از تاریخ شروع باشد.'})

        if not self.employee_id or not self.start_date:
            return

        # Overlap check — identical logic/shape to MonthlyWage.clean().
        cond_existing_running = (
            Q(end_date__isnull=True) | Q(end_date__gte=self.start_date)
        )
        cond_self_not_ended = (
            Q(start_date__lte=self.end_date) if self.end_date is not None else Q()
        )
        qs = HourlyRate.objects.filter(
            employee_id=self.employee_id,
            is_active=True,
        ).filter(cond_existing_running).filter(cond_self_not_ended)

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        if qs.exists():
            raise ValidationError(
                'این کارمند در این بازه زمانی دارای نرخ ساعتی فعال دیگری است.'
            )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = self.__original_rate
            current  = self.__dict__.get('rate')
            if original is not None and current is not None and original != current:
                raise ValueError(
                    'نرخ ساعتی قابل ویرایش نیست. '
                    'رکورد قدیمی را غیرفعال کنید و رکورد جدید ایجاد کنید.'
                )
        super().save(*args, **kwargs)
        self.__original_rate = self.__dict__.get('rate')

    def delete(self, *args, **kwargs):
        raise ProtectedError(
            'حذف نرخ ساعتی مجاز نیست. رکورد را غیرفعال کنید.',
            {self},
        )

    @classmethod
    def get_active_rate_for_date(cls, employee_id: int, work_date) -> 'Decimal | None':
        """The HourlyRate effective on `work_date` for `employee_id`, or None.

        Used to price each HourlyWorkEntry using the rate that was actually
        in force on its own work date — not just the employee's latest rate —
        so a rate change mid-period prices only the entries on/after it.
        """
        rate = cls.objects.filter(
            employee_id=employee_id,
            is_active=True,
            start_date__lte=work_date,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=work_date)
        ).order_by('-start_date').first()
        return rate.rate if rate else None

    @classmethod
    def get_current_and_future(cls, employee_id: int, reference_date) -> 'tuple[HourlyRate | None, HourlyRate | None]':
        """(current, future) HourlyRate rows for `employee_id` as of
        `reference_date` — real date objects compared against `start_date`/
        `end_date`, never just "is_active".

        `current` is the row actually in effect on `reference_date` (same
        rule as get_active_rate_for_date). `future` is the next row whose
        `start_date` is after `reference_date`, if one exists and no current
        row covers it yet — this is what lets a screen tell an employee with
        an as-yet-unstarted rate apart from one with no rate configured at
        all, instead of both looking like "تنظیم نشده".
        """
        current = cls.objects.filter(
            employee_id=employee_id,
            is_active=True,
            start_date__lte=reference_date,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=reference_date)
        ).order_by('-start_date').first()

        future = cls.objects.filter(
            employee_id=employee_id,
            is_active=True,
            start_date__gt=reference_date,
        ).order_by('start_date').first()

        return current, future


# ---------------------------------------------------------------------------
# HourlyWorkEntry — one dated, fractional-hours work record for an employee
#
# Multiple entries per employee per payroll period are expected (e.g. one
# per work day). `payroll_period` / `rate_used` / `amount` stay null until
# the entry is included in a payroll calculation (see
# payroll.services.calculate_hourly_payroll) — at that point they are
# snapshotted and the entry becomes immutable, so later rate changes or
# edits can never silently alter an already-finalized payroll.
# ---------------------------------------------------------------------------

class HourlyWorkEntry(models.Model):
    employee       = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='hourly_work_entries',
        verbose_name='کارمند',
    )
    work_date      = models.DateField(verbose_name='تاریخ کار')
    hours_worked   = models.DecimalField(
        max_digits=5, decimal_places=2,
        verbose_name='ساعات کارکرد',
    )
    description    = models.TextField(blank=True, default='', verbose_name='توضیحات')
    payroll_period = models.ForeignKey(
        PayrollPeriod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='hourly_work_entries',
        verbose_name='دوره حقوقی',
        help_text='پس از محاسبه حقوق ساعتی این دوره، به‌طور خودکار تکمیل می‌شود.',
    )
    rate_used      = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True, editable=False,
        verbose_name='نرخ اعمال‌شده',
        help_text='نرخ ساعتی مؤثر در تاریخ کار — هنگام محاسبه حقوق snapshot می‌شود.',
    )
    amount         = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True, editable=False,
        verbose_name='مبلغ محاسبه‌شده',
        help_text='= ساعات کارکرد × نرخ اعمال‌شده',
    )
    created_at     = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at     = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'رکورد ساعت کاری'
        verbose_name_plural = 'رکوردهای ساعت کاری'
        ordering            = ['-work_date']
        indexes             = [
            models.Index(fields=['employee']),
            models.Index(fields=['work_date']),
            models.Index(fields=['payroll_period']),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original = {
            'employee_id':    self.__dict__.get('employee_id'),
            'work_date':      self.__dict__.get('work_date'),
            'hours_worked':   self.__dict__.get('hours_worked'),
            'payroll_period_id': self.__dict__.get('payroll_period_id'),
        }

    def __str__(self):
        return f'{self.employee.full_name} — {self.work_date} — {self.hours_worked} ساعت'

    @property
    def is_processed(self) -> bool:
        return self.payroll_period_id is not None

    def clean(self):
        if self.hours_worked is not None:
            if self.hours_worked <= 0:
                raise ValidationError({'hours_worked': 'ساعات کارکرد باید بزرگ‌تر از صفر باشد.'})
            if self.hours_worked > 24:
                raise ValidationError({'hours_worked': 'یک رکورد روزانه نمی‌تواند بیشتر از ۲۴ ساعت باشد.'})

        if self.payroll_period_id and self.work_date:
            period = self.payroll_period
            last_day   = _jalali_days_in_month(period.year, period.month)
            first_greg = datetime.date(*_jalali_to_gregorian(period.year, period.month, 1))
            last_greg  = datetime.date(*_jalali_to_gregorian(period.year, period.month, last_day))
            if not (first_greg <= self.work_date <= last_greg):
                raise ValidationError(
                    {'work_date': 'تاریخ کار باید در بازه دوره حقوقی انتخاب‌شده باشد.'}
                )

        if self.pk and self.__original['payroll_period_id'] is not None:
            changed = (
                self.__original['employee_id']    != self.employee_id
                or self.__original['work_date']    != self.work_date
                or self.__original['hours_worked'] != self.hours_worked
            )
            if changed:
                raise ValidationError(
                    'این رکورد در محاسبه حقوق پردازش شده و قابل ویرایش نیست. '
                    'برای ویرایش، ابتدا آن را از دوره حقوقی خارج کنید.'
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.__original = {
            'employee_id':       self.employee_id,
            'work_date':         self.work_date,
            'hours_worked':      self.hours_worked,
            'payroll_period_id': self.payroll_period_id,
        }

    def delete(self, *args, **kwargs):
        if self.payroll_period_id is not None:
            raise ProtectedError(
                'این رکورد در محاسبه حقوق پردازش شده و قابل حذف نیست.',
                {self},
            )
        return super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# CommissionRule
# ---------------------------------------------------------------------------

class CommissionRule(models.Model):
    """
    Rate card entry: commission percentage for a (job_position × surgery_type) pair.

    Invariants:
    - Only one active rule per pair at a time (enforced by clean() and serializer).
      Note: queryset.update() bypasses clean(); avoid bulk-activating rules via ORM.
    - commission_percent is immutable once saved. Deactivate old, create new.
    """

    job_position       = models.ForeignKey(
        'employees.JobPosition',
        on_delete=models.PROTECT,
        related_name='commission_rules',
        verbose_name='موقعیت شغلی',
    )
    surgery_type       = models.ForeignKey(
        'surgeries.SurgeryType',
        on_delete=models.PROTECT,
        related_name='commission_rules',
        verbose_name='نوع عمل',
    )
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='درصد کمیسیون',
    )
    start_date         = models.DateField(
        default=datetime.date.today,
        verbose_name='تاریخ شروع',
    )
    is_active          = models.BooleanField(default=True, verbose_name='فعال')
    notes              = models.TextField(blank=True, verbose_name='توضیحات')
    created_by         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_commission_rules',
        verbose_name='ایجاد شده توسط',
    )
    created_at         = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at         = models.DateTimeField(auto_now=True,     verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'قانون کمیسیون'
        verbose_name_plural = 'قوانین کمیسیون'
        ordering            = ['-start_date']
        indexes = [
            models.Index(fields=['job_position']),
            models.Index(fields=['surgery_type']),
            models.Index(fields=['is_active']),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_commission_percent = self.__dict__.get('commission_percent')

    def __str__(self) -> str:
        return f'{self.job_position} × {self.surgery_type} = {self.commission_percent}%'

    def clean(self):
        if self.commission_percent is not None:
            if self.commission_percent <= 0:
                raise ValidationError(
                    {'commission_percent': 'درصد کمیسیون باید بزرگ‌تر از صفر باشد.'}
                )
            if self.commission_percent > 100:
                raise ValidationError(
                    {'commission_percent': 'درصد کمیسیون نمی‌تواند بیشتر از ۱۰۰ باشد.'}
                )

        if self.job_position_id and self.surgery_type_id and self.is_active:
            qs = CommissionRule.objects.filter(
                job_position_id=self.job_position_id,
                surgery_type_id=self.surgery_type_id,
                is_active=True,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    'یک قانون کمیسیون فعال برای این ترکیب موقعیت شغلی و نوع عمل وجود دارد.'
                )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = self.__original_commission_percent
            current  = self.__dict__.get('commission_percent')
            if original is not None and current is not None and original != current:
                raise ValueError(
                    'درصد کمیسیون قابل ویرایش نیست. '
                    'قانون قدیمی را غیرفعال کنید و قانون جدید ایجاد کنید.'
                )
        super().save(*args, **kwargs)
        self.__original_commission_percent = self.__dict__.get('commission_percent')

    @classmethod
    def get_active_rule(
        cls, job_position_id: int, surgery_type_id: int
    ) -> 'CommissionRule | None':
        """Returns the single active CommissionRule for a given position + surgery type.

        Returns None if no active rule exists. Used by CLI-31 commission calculation.
        Explicit order_by('-start_date') ensures determinism even when two active rules
        exist (possible via queryset.update() bypassing clean()).
        """
        return cls.objects.filter(
            job_position_id=job_position_id,
            surgery_type_id=surgery_type_id,
            is_active=True,
        ).order_by('-start_date').first()


# ---------------------------------------------------------------------------
# CommissionTransaction
# ---------------------------------------------------------------------------

class CommissionTransaction(models.Model):
    """One calculated commission per (surgery, employee, commission_rule) triple.

    Unique constraint prevents duplicate commission entries for the same
    surgery + employee + rule combination.  The service layer creates these;
    signals fire the service automatically when a SurgeryHistory is saved.
    """

    surgery = models.ForeignKey(
        'surgeries.SurgeryHistory',
        on_delete=models.CASCADE,
        related_name='commission_transactions',
        verbose_name='تاریخچه عمل',
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='commission_transactions',
        verbose_name='کارمند',
    )
    commission_rule = models.ForeignKey(
        CommissionRule,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='قانون کمیسیون',
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='مبلغ کمیسیون',
        help_text='مبلغ کمیسیون = مبلغ عمل × درصد کمیسیون / ۱۰۰',
    )
    notes      = models.TextField(blank=True, default='', verbose_name='توضیحات')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True,     verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'تراکنش کمیسیون'
        verbose_name_plural = 'تراکنش‌های کمیسیون'
        ordering            = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['surgery', 'employee', 'commission_rule'],
                name='unique_surgery_employee_rule',
            ),
        ]
        indexes = [
            models.Index(fields=['surgery'],  name='idx_ct_surgery'),
            models.Index(fields=['employee'], name='idx_ct_employee'),
            models.Index(fields=['created_at'], name='idx_ct_created_at'),
        ]

    def __str__(self) -> str:
        return (
            f'{self.employee.full_name} | '
            f'{self.commission_rule} | '
            f'{self.amount:,} ریال'
        )

    def __repr__(self) -> str:
        return (
            f'<CommissionTransaction pk={self.pk} '
            f'surgery={self.surgery_id} employee={self.employee_id} '
            f'amount={self.amount}>'
        )


# ---------------------------------------------------------------------------
# HourlyWorkRecord — monthly hours-based salary
# ---------------------------------------------------------------------------

class HourlyWorkRecord(models.Model):
    """LEGACY — superseded by HourlyRate + HourlyWorkEntry (dated, per-entry
    hours priced with historical effective rates). Kept only so existing
    monthly-total records and Employee.hourly_rate keep working; the admin
    no longer allows creating or editing new rows here (see
    HourlyWorkRecordAdmin.has_add_permission/has_change_permission) and
    report/Finance code treats this as the hourly source ONLY for an
    employee with no HourlyWorkEntry data — never combined with it.

    calculated_salary = hours_worked × hourly_rate (stored as snapshot).
    record_date stores the Gregorian first day of the Jalali month for easy
    date-range filtering.
    """

    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='hourly_work_records',
        verbose_name='کارمند',
    )
    jalali_year  = models.PositiveIntegerField(verbose_name='سال شمسی')
    jalali_month = models.PositiveIntegerField(verbose_name='ماه شمسی')
    hours_worked = models.DecimalField(
        max_digits=7, decimal_places=2,
        verbose_name='ساعات کاری',
        help_text='کل ساعات کاری در این ماه',
    )
    hourly_rate = models.DecimalField(
        max_digits=14, decimal_places=2,
        verbose_name='نرخ هر ساعت (تومان)',
        help_text='نرخ ساعتی اعمال‌شده برای این ماه — برای حفظ تاریخچه snapshot می‌شود.',
    )
    calculated_salary = models.DecimalField(
        max_digits=14, decimal_places=2,
        verbose_name='حقوق محاسبه‌شده (تومان)',
        editable=False,
        help_text='= ساعات کاری × نرخ هر ساعت',
    )
    record_date = models.DateField(
        verbose_name='تاریخ دوره (میلادی)',
        editable=False,
        help_text='اولین روز ماه شمسی به میلادی — برای فیلتر بازه تاریخ',
    )
    notes     = models.TextField(blank=True, default='', verbose_name='توضیحات')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True,     verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'رکورد ساعات کاری ماهانه'
        verbose_name_plural = 'رکوردهای ساعات کاری ماهانه'
        unique_together     = [('employee', 'jalali_year', 'jalali_month')]
        ordering            = ['-jalali_year', '-jalali_month']
        indexes = [
            models.Index(fields=['employee'],    name='idx_hwr_employee'),
            models.Index(fields=['record_date'], name='idx_hwr_record_date'),
        ]

    def __str__(self) -> str:
        month_name = PERSIAN_MONTHS.get(self.jalali_month, str(self.jalali_month))
        return (
            f'{self.employee.full_name} — '
            f'{month_name} {self.jalali_year} — '
            f'{self.calculated_salary:,} تومان'
        )

    def clean(self):
        if self.jalali_month is not None and not (1 <= self.jalali_month <= 12):
            raise ValidationError({'jalali_month': 'ماه باید بین ۱ تا ۱۲ باشد.'})
        if self.hours_worked is not None and self.hours_worked < 0:
            raise ValidationError({'hours_worked': 'ساعات کاری نمی‌تواند منفی باشد.'})
        if self.hourly_rate is not None and self.hourly_rate <= 0:
            raise ValidationError({'hourly_rate': 'نرخ هر ساعت باید بزرگ‌تر از صفر باشد.'})

    def save(self, *args, **kwargs):
        if self.jalali_year and self.jalali_month:
            gy, gm, gd = _jalali_to_gregorian(self.jalali_year, self.jalali_month, 1)
            self.record_date = datetime.date(gy, gm, gd)
        if self.hours_worked is not None and self.hourly_rate is not None:
            self.calculated_salary = (
                Decimal(str(self.hours_worked)) * Decimal(str(self.hourly_rate))
            ).quantize(Decimal('1'))
        super().save(*args, **kwargs)
