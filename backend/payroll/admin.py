from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import path

from common.admin import (
    DECIMAL_FORMFIELD_OVERRIDES as _DECIMAL_OVERRIDES,
    JALALI_FORMFIELD_OVERRIDES as _JALALI_DATE_OVERRIDES,
    JalaliAdminDatesMixin,
    clean_decimal_display,
)
from .models import (
    CommissionRule,
    CommissionTransaction,
    HourlyRate,
    HourlyWorkEntry,
    HourlyWorkRecord,
    MonthlyWage,
    PayrollPeriod,
    PayrollStatus,
    PayrollTypeConfig,
)


# ---------------------------------------------------------------------------
# Payroll page — custom admin view
# ---------------------------------------------------------------------------

@staff_member_required
def payroll_page_view(request):
    """Render the payroll page inside the Django admin shell."""
    context = {
        **admin.site.each_context(request),
        'title': 'حقوق و دستمزد',
    }
    return render(request, 'admin/payroll/payroll_page.html', context)


# ---------------------------------------------------------------------------
# ModelAdmins (registered after assigning custom admin site)
# ---------------------------------------------------------------------------

@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ['display_name', 'year', 'month', 'status', 'created_at_jalali', 'closed_at_jalali']
    list_filter     = ['status', 'year']
    readonly_fields = ['created_at_jalali', 'closed_at_jalali', 'display_name']
    actions         = ['close_periods']

    @admin.action(description='بستن دوره‌های انتخاب‌شده')
    def close_periods(self, request, queryset):
        for period in queryset.filter(status=PayrollStatus.OPEN):
            period.close()


@admin.register(PayrollTypeConfig)
class PayrollTypeConfigAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ['employee', 'has_monthly_wage', 'has_commission', 'has_hourly_wage', 'updated_at_jalali']
    list_filter     = ['has_monthly_wage', 'has_commission', 'has_hourly_wage']
    search_fields   = ['employee__full_name']
    readonly_fields = ['updated_at_jalali']


@admin.register(MonthlyWage)
class MonthlyWageAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ['employee', 'get_amount_display', 'start_date_jalali', 'end_date_jalali', 'is_active', 'created_at_jalali']
    list_filter     = ['is_active', 'employee__job_position']
    search_fields   = ['employee__full_name']
    readonly_fields = ['created_by', 'created_at_jalali', 'updated_at_jalali']
    formfield_overrides = {**_JALALI_DATE_OVERRIDES, **_DECIMAL_OVERRIDES}

    @admin.display(description='مبلغ حقوق', ordering='amount')
    def get_amount_display(self, obj):
        return clean_decimal_display(obj.amount)
    fieldsets = (
        ('اطلاعات حقوق', {
            'fields': ('employee', 'amount', 'start_date', 'end_date'),
        }),
        ('وضعیت', {
            'fields': ('is_active', 'notes'),
        }),
        ('سیستم', {
            'fields': ('created_by', 'created_at_jalali', 'updated_at_jalali'),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(HourlyRate)
class HourlyRateAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ['employee', 'get_rate_display', 'start_date_jalali', 'end_date_jalali', 'is_active', 'created_at_jalali']
    list_filter     = ['employee', 'is_active', 'employee__job_position']
    search_fields   = ['employee__full_name']
    readonly_fields = ['created_by', 'created_at_jalali', 'updated_at_jalali']
    formfield_overrides = {**_JALALI_DATE_OVERRIDES, **_DECIMAL_OVERRIDES}

    @admin.display(description='نرخ هر ساعت', ordering='rate')
    def get_rate_display(self, obj):
        return clean_decimal_display(obj.rate)

    fieldsets = (
        ('اطلاعات نرخ ساعتی', {
            'fields': ('employee', 'rate', 'start_date', 'end_date'),
        }),
        ('وضعیت', {
            'fields': ('is_active', 'notes'),
        }),
        ('سیستم', {
            'fields': ('created_by', 'created_at_jalali', 'updated_at_jalali'),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(HourlyWorkEntry)
class HourlyWorkEntryAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = [
        'employee', 'work_date_jalali', 'get_hours_display',
        'get_rate_used_display', 'get_amount_display', 'payroll_period',
    ]
    list_filter     = ['employee', 'employee__job_position', 'payroll_period']
    search_fields   = ['employee__full_name']
    readonly_fields = ['rate_used', 'amount', 'payroll_period', 'created_at_jalali', 'updated_at_jalali']
    ordering        = ['-work_date']
    formfield_overrides = {**_JALALI_DATE_OVERRIDES, **_DECIMAL_OVERRIDES}
    fieldsets = (
        ('اطلاعات ساعت کاری', {
            'fields': ('employee', 'work_date', 'hours_worked', 'description'),
        }),
        ('نتیجه محاسبه (پس از پردازش دوره حقوقی)', {
            'fields': ('rate_used', 'amount', 'payroll_period'),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='تاریخ کار', ordering='work_date')
    def work_date_jalali(self, obj):
        from common.dates import to_jalali_date
        return to_jalali_date(obj.work_date)

    @admin.display(description='ساعات کارکرد', ordering='hours_worked')
    def get_hours_display(self, obj):
        return clean_decimal_display(obj.hours_worked)

    @admin.display(description='نرخ اعمال‌شده')
    def get_rate_used_display(self, obj):
        return clean_decimal_display(obj.rate_used) if obj.rate_used is not None else '—'

    @admin.display(description='مبلغ محاسبه‌شده (تومان)')
    def get_amount_display(self, obj):
        if obj.amount is None:
            return '—'
        from finance.admin import _fmt_toman
        return f'{_fmt_toman(obj.amount)} تومان'

    def get_readonly_fields(self, request, obj=None):
        base = list(super().get_readonly_fields(request, obj))
        if obj and obj.is_processed:
            base.extend(['employee', 'work_date', 'hours_worked'])
        return base

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_processed:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        return actions


@admin.register(CommissionRule)
class CommissionRuleAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = [
        'job_position', 'surgery_type',
        'get_commission_percent_display', 'start_date_jalali',
        'is_active', 'created_at_jalali',
    ]
    list_filter     = ['is_active', 'job_position', 'surgery_type']
    search_fields   = ['job_position__name', 'surgery_type__name']
    readonly_fields = ['created_by', 'created_at_jalali', 'updated_at_jalali']
    formfield_overrides = {**_JALALI_DATE_OVERRIDES, **_DECIMAL_OVERRIDES}

    @admin.display(description='درصد کمیسیون', ordering='commission_percent')
    def get_commission_percent_display(self, obj):
        return clean_decimal_display(obj.commission_percent)
    fieldsets = (
        ('قانون کمیسیون', {
            'fields': ('job_position', 'surgery_type', 'commission_percent', 'start_date'),
        }),
        ('وضعیت', {
            'fields': ('is_active', 'notes'),
        }),
        ('سیستم', {
            'fields': ('created_by', 'created_at_jalali', 'updated_at_jalali'),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CommissionTransaction)
class CommissionTransactionAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = [
        'pk', 'surgery', 'employee', 'commission_rule', 'get_amount_display', 'created_at_jalali',
    ]
    list_filter     = ['employee__job_position', 'commission_rule__surgery_type']
    search_fields   = [
        'employee__full_name',
        'surgery__patient__full_name',
        'surgery__case_code',
        'notes',
    ]
    readonly_fields = ['amount', 'surgery', 'employee', 'commission_rule', 'created_at_jalali', 'updated_at_jalali']
    ordering        = ['-created_at']
    fieldsets = (
        ('کمیسیون', {
            'fields': ('surgery', 'employee', 'commission_rule', 'amount', 'notes'),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='مبلغ کمیسیون', ordering='amount')
    def get_amount_display(self, obj):
        return clean_decimal_display(obj.amount)


@admin.register(HourlyWorkRecord)
class HourlyWorkRecordAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    """LEGACY — read-only. New hourly payroll is entered via the Employee
    form's «حقوق و دستمزد» (wage_type=hourly) + the HourlyRate/HourlyWorkEntry
    admin pages. This page stays visible only so previously-created monthly
    records remain auditable; it no longer accepts new or edited rows."""

    list_display    = [
        'employee', 'get_period_display', 'get_hours_worked_display',
        'get_hourly_rate_display', 'get_calculated_salary_display', 'created_at_jalali',
    ]
    list_filter     = ['employee__job_position', 'jalali_year', 'jalali_month']
    search_fields   = ['employee__full_name']
    readonly_fields = ['calculated_salary', 'record_date', 'created_at_jalali', 'updated_at_jalali']
    ordering        = ['-jalali_year', '-jalali_month', 'employee__full_name']
    formfield_overrides = _DECIMAL_OVERRIDES
    fieldsets = (
        ('اطلاعات ساعات کاری (قدیمی / بایگانی)', {
            'fields': ('employee', 'jalali_year', 'jalali_month', 'hours_worked', 'hourly_rate'),
            'description': (
                'این بخش سامانه قدیمی حقوق ساعتی است و فقط برای مشاهده رکوردهای گذشته نگه '
                'داشته شده — دیگر امکان ثبت یا ویرایش رکورد جدید در اینجا وجود ندارد. '
                'برای حقوق ساعتی جدید از فرم کارمند (نوع دستمزد: «حقوق ساعتی») استفاده کنید.'
            ),
        }),
        ('نتیجه محاسبه', {
            'fields': ('calculated_salary', 'record_date'),
        }),
        ('یادداشت', {
            'fields': ('notes',),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='دوره')
    def get_period_display(self, obj):
        from payroll.models import PERSIAN_MONTHS
        month_name = PERSIAN_MONTHS.get(obj.jalali_month, str(obj.jalali_month))
        return f'{month_name} {obj.jalali_year}'

    @admin.display(description='ساعات کاری', ordering='hours_worked')
    def get_hours_worked_display(self, obj):
        return clean_decimal_display(obj.hours_worked)

    @admin.display(description='نرخ ساعتی', ordering='hourly_rate')
    def get_hourly_rate_display(self, obj):
        return clean_decimal_display(obj.hourly_rate)

    @admin.display(description='حقوق محاسبه‌شده (تومان)')
    def get_calculated_salary_display(self, obj):
        from finance.admin import _fmt_toman
        return f'{_fmt_toman(obj.calculated_salary)} تومان'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# The monkey‑patching section has been removed.