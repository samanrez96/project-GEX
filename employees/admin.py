import mimetypes
from decimal import Decimal

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path

from common.admin import (
    JALALI_FORMFIELD_OVERRIDES,
    JalaliAdminDatesMixin,
    JalaliFormDateField,
    MONEY_FORMFIELD_OVERRIDES,
    MoneyInput,
    clean_decimal_display,
)
from contacts.forms import DoctorDocumentWidget, ValidatedImageFormField
from employees.models import Employee, EmployeeDocument, EmployeePurchaseCommission, JobPosition


class EmployeeAdminForm(forms.ModelForm):
    """Standard employee ModelForm extended with optional wage configuration."""

    WAGE_CHOICES = [
        ('none',       'بدون تغییر / تنظیم نشده'),
        ('fixed',      'حقوق ثابت ماهیانه'),
        ('commission', 'کمیسیونی'),
        ('hourly',     'حقوق ساعتی'),
    ]

    wage_type = forms.ChoiceField(
        choices=WAGE_CHOICES,
        required=False,
        initial='none',
        label='نوع دستمزد',
    )
    monthly_amount = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=2,
        label='مبلغ حقوق ثابت ماهیانه (تومان)',
        help_text='برای نوع «حقوق ثابت» الزامی است.',
        widget=MoneyInput(),
    )
    hourly_rate_amount = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=2,
        label='نرخ هر ساعت (تومان)',
        help_text='برای نوع «حقوق ساعتی» الزامی است. می‌تواند صفر باشد.',
        widget=MoneyInput(),
    )
    wage_start_date = JalaliFormDateField(
        required=False,
        label='تاریخ شروع حقوق',
        help_text='پیش‌فرض: تاریخ شروع به کار کارمند. نمونه: ۱۴۰۵/۰۴/۰۳',
    )

    class Meta:
        model  = Employee
        fields = '__all__'
        exclude = ('first_name', 'last_name')

    def clean(self):
        cleaned  = super().clean()
        wage_type = cleaned.get('wage_type')
        if wage_type == 'fixed' and not cleaned.get('monthly_amount'):
            self.add_error('monthly_amount', 'مبلغ حقوق ماهیانه برای نوع «حقوق ثابت» الزامی است.')
        if wage_type == 'hourly' and cleaned.get('hourly_rate_amount') is None:
            self.add_error('hourly_rate_amount', 'نرخ هر ساعت برای نوع «حقوق ساعتی» الزامی است.')
        return cleaned


@admin.register(JobPosition)
class JobPositionAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ["name", "get_active_employee_count", "is_active", "created_at_jalali"]
    list_filter     = ["is_active"]
    search_fields   = ["name", "description"]
    readonly_fields = ["get_active_employee_count", "created_at_jalali", "updated_at_jalali"]

    fieldsets = (
        ("اطلاعات پوزیشن", {
            "fields": ("name", "description", "is_active"),
        }),
        ("آمار", {
            "fields": ("get_active_employee_count",),
        }),
        ("سیستم", {
            "fields": ("created_at_jalali", "updated_at_jalali"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _active_employee_count=Count(
                "employees", filter=Q(employees__is_active=True)
            )
        )

    @admin.display(description="کارمندان فعال", ordering="_active_employee_count")
    def get_active_employee_count(self, obj):
        return obj.get_active_employee_count()


class EmployeeDocumentInlineForm(forms.ModelForm):
    file = ValidatedImageFormField(
        required=False,
        label='مدرک',
        widget=DoctorDocumentWidget(url_name='admin:employees_employeedocument_file'),
    )

    class Meta:
        model  = EmployeeDocument
        fields = ('file',)


class EmployeeDocumentInline(admin.TabularInline):
    model               = EmployeeDocument
    form                = EmployeeDocumentInlineForm
    fk_name             = 'employee'
    extra               = 1
    fields              = ('file',)
    verbose_name        = 'مدرک'
    verbose_name_plural = 'مدارک'
    template            = 'admin/employees/employee/employee_document_inline.html'


@admin.register(Employee)
class EmployeeAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    form    = EmployeeAdminForm
    inlines = [EmployeeDocumentInline]

    change_list_template = "admin/employees/employee/change_list.html"
    change_form_template = "admin/employees/employee/employee_edit_form.html"
    formfield_overrides  = {**JALALI_FORMFIELD_OVERRIDES, **MONEY_FORMFIELD_OVERRIDES}

    list_display   = (
        "full_name", "job_position", "email",
        "personal_phone", "is_active", "start_date",
    )
    search_fields  = (
        "full_name", "email", "personal_phone",
        "national_id", "job_position__name",
    )
    list_filter    = ("is_active", "gender", "job_position")
    ordering       = ("full_name",)
    readonly_fields = ("created_at_jalali", "updated_at_jalali")
    date_hierarchy  = "start_date"

    @admin.display(description="حقوق / دستمزد فعلی")
    def current_wage_display(self, obj):
        if not obj or not obj.pk:
            return "—"
        import datetime
        from finance.admin import _fmt_toman
        from common.dates import to_jalali_date
        from payroll.models import HourlyRate, HourlyWorkRecord, MonthlyWage
        parts = []
        wage = MonthlyWage.objects.filter(employee=obj, is_active=True).first()
        if wage:
            parts.append(f"حقوق ثابت: {_fmt_toman(wage.amount)} تومان")

        hourly_current, hourly_future = HourlyRate.get_current_and_future(obj.pk, datetime.date.today())
        if hourly_current:
            parts.append(
                f"نرخ ساعتی: {_fmt_toman(hourly_current.rate)} تومان/ساعت"
                f" (از {to_jalali_date(hourly_current.start_date)})"
            )
        elif hourly_future:
            parts.append(
                f"نرخ ساعتی (آینده از {to_jalali_date(hourly_future.start_date)}): "
                f"{_fmt_toman(hourly_future.rate)} تومان/ساعت"
            )

        if obj.hourly_rate:
            last_rec = HourlyWorkRecord.objects.filter(employee=obj).first()
            if last_rec:
                parts.append(
                    f"آخرین ساعتی: {_fmt_toman(last_rec.calculated_salary)} تومان"
                    f" ({last_rec.hours_worked} ساعت × {_fmt_toman(obj.hourly_rate)} تومان/ساعت)"
                )
            else:
                parts.append(f"نرخ ساعتی (قدیمی): {_fmt_toman(obj.hourly_rate)} تومان/ساعت")
        try:
            cfg = obj.payroll_config
            if cfg.has_commission and not wage:
                parts.append("کمیسیونی (براساس قانون کمیسیون سمت شغلی)")
        except Exception:
            pass
        return " | ".join(parts) if parts else "تنظیم نشده"

    def get_readonly_fields(self, request, obj=None):
        base = list(super().get_readonly_fields(request, obj))
        if obj:
            base.append("current_wage_display")
        return base

    def get_fieldsets(self, request, obj=None):
        payroll_fields = []
        if obj:
            payroll_fields.append("current_wage_display")
        payroll_fields.extend(["wage_type", "monthly_amount", "hourly_rate_amount", "wage_start_date"])

        payroll_desc = (
            "برای ایجاد یا تغییر حقوق، نوع دستمزد را انتخاب و مبلغ/نرخ را وارد کنید. "
            "حقوق یا نرخ قبلی از همان نوع غیرفعال می‌شود و رکورد جدید ثبت می‌گردد."
            if obj else
            "نوع دستمزد اولیه کارمند را تنظیم کنید."
        )

        return [
            ("اطلاعات هویتی", {
                "fields": ("full_name", "national_id", "gender"),
            }),
            ("اطلاعات شغلی", {
                "fields": ("job_position", "start_date", "is_active"),
            }),
            ("اطلاعات تماس", {
                "fields": ("email", "personal_phone", "emergency_contact_phone", "address"),
            }),
            ("توضیحات", {
                "fields": ("description",),
            }),
            ("نرخ ساعتی (قدیمی / بایگانی)", {
                "fields": ("hourly_rate",),
                "classes": ("collapse",),
                "description": (
                    "این فیلد بخشی از سامانه قدیمی حقوق ساعتی است و فقط برای حفظ سازگاری با "
                    "رکوردهای قبلی («رکوردهای ساعات کاری ماهانه») نگه داشته شده است. "
                    "برای کارمندان جدید از بخش «حقوق و دستمزد» پایین (نوع دستمزد: «حقوق ساعتی») "
                    "استفاده کنید که نرخ‌های تاریخی و رکوردهای روزانه ساعت کار را پشتیبانی می‌کند."
                ),
            }),
            ("حقوق و دستمزد", {
                "fields": tuple(payroll_fields),
                "description": payroll_desc,
            }),
            ("زمان‌بندی", {
                "fields": ("created_at_jalali", "updated_at_jalali"),
                "classes": ("collapse",),
            }),
        ]

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)
        if obj and request.method == 'GET':
            import datetime
            from payroll.models import HourlyRate, MonthlyWage
            wage = MonthlyWage.objects.filter(employee=obj, is_active=True).first()
            hourly_current, hourly_future = HourlyRate.get_current_and_future(obj.pk, datetime.date.today())
            hourly = hourly_current or hourly_future

            if wage:
                wage_initial = {
                    'wage_type':        'fixed',
                    'monthly_amount':   wage.amount,
                    'wage_start_date':  wage.start_date,
                }
            elif hourly:
                wage_initial = {
                    'wage_type':           'hourly',
                    'hourly_rate_amount':  hourly.rate,
                    'wage_start_date':     hourly.start_date,
                }
            else:
                wage_initial = {}
                try:
                    if obj.payroll_config.has_commission:
                        wage_initial = {'wage_type': 'commission'}
                except Exception:
                    pass

            if wage_initial:
                class _FormWithWageInitial(form_class):
                    def __init__(self, *args, **kw):
                        kw.setdefault('initial', {}).update(wage_initial)
                        super().__init__(*args, **kw)
                return _FormWithWageInitial

        return form_class

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            self._save_payroll(request, obj, form)

    def _save_payroll(self, request, obj, form):
        wage_type  = form.cleaned_data.get('wage_type', 'none')
        wage_start = form.cleaned_data.get('wage_start_date') or obj.start_date

        if wage_type == 'fixed':
            self._save_monthly_wage(request, obj, form, wage_start)
        elif wage_type == 'hourly':
            self._save_hourly_rate(request, obj, form, wage_start)

    def _save_monthly_wage(self, request, obj, form, wage_start):
        from payroll.models import MonthlyWage

        monthly_amount = form.cleaned_data.get('monthly_amount')
        if not monthly_amount or monthly_amount <= 0:
            return

        existing = MonthlyWage.objects.filter(employee=obj, is_active=True).first()
        if existing and existing.amount == Decimal(str(monthly_amount)):
            return

        for old in MonthlyWage.objects.filter(employee=obj, is_active=True):
            old.is_active = False
            if not old.end_date:
                old.end_date = wage_start
            old.save(update_fields=['is_active', 'end_date', 'updated_at'])

        MonthlyWage.objects.create(
            employee=obj,
            amount=monthly_amount,
            start_date=wage_start,
            is_active=True,
            created_by=request.user,
        )

    def _save_hourly_rate(self, request, obj, form, wage_start):
        from payroll.models import HourlyRate

        hourly_rate_amount = form.cleaned_data.get('hourly_rate_amount')
        if hourly_rate_amount is None or hourly_rate_amount < 0:
            return
        new_rate = Decimal(str(hourly_rate_amount))

        existing = HourlyRate.objects.filter(employee=obj, is_active=True).first()
        if existing and existing.rate == new_rate and existing.start_date == wage_start:
            return

        for old in HourlyRate.objects.filter(employee=obj, is_active=True):
            old.is_active = False
            if not old.end_date:
                old.end_date = wage_start if wage_start > old.start_date else old.start_date
            old.save(update_fields=['is_active', 'end_date', 'updated_at'])

        HourlyRate.objects.create(
            employee=obj,
            rate=new_rate,
            start_date=wage_start,
            is_active=True,
            created_by=request.user,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:employee_id>/detail/",
                self.admin_site.admin_view(employee_detail_view),
                name="employees_employee_detail",
            ),
            path(
                "documents/<int:pk>/",
                self.admin_site.admin_view(employee_document_view),
                name="employees_employeedocument_file",
            ),
        ]
        return custom_urls + urls


def employee_document_view(request, pk):
    if not request.user.has_perm('employees.view_employee'):
        raise PermissionDenied
    document = get_object_or_404(EmployeeDocument, pk=pk)
    field_file = document.file
    if not field_file or not field_file.name:
        raise Http404('مدرکی با این شناسه ثبت نشده است.')
    try:
        handle = field_file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('فایل مربوطه در سرور یافت نشد.')
    content_type = mimetypes.guess_type(field_file.name)[0] or 'application/octet-stream'
    response = FileResponse(handle, content_type=content_type)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline'
    return response


@admin.register(EmployeePurchaseCommission)
class EmployeePurchaseCommissionAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ['employee', 'purchase', 'get_amount_display', 'commission_date_jalali', 'description_short']
    list_filter     = ['employee__job_position']
    search_fields   = ['employee__full_name', 'description']
    ordering        = ['-commission_date']
    readonly_fields = ['created_at_jalali', 'updated_at_jalali']
    formfield_overrides = {**JALALI_FORMFIELD_OVERRIDES, **MONEY_FORMFIELD_OVERRIDES}
    fieldsets = (
        ('اطلاعات کمیسیون', {
            'fields': ('employee', 'purchase', 'amount', 'commission_date', 'description'),
            'description': 'کمیسیون کارمند بر اساس صرفه‌جویی یا سود خرید. مستقل از کمیسیون جراحی است.',
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='مبلغ کمیسیون')
    def get_amount_display(self, obj):
        from finance.admin import _fmt_toman
        return f'{_fmt_toman(obj.amount)} تومان'

    @admin.display(description='تاریخ کمیسیون', ordering='commission_date')
    def commission_date_jalali(self, obj):
        from common.dates import to_jalali_date
        return to_jalali_date(obj.commission_date)

    @admin.display(description='توضیحات')
    def description_short(self, obj):
        return (obj.description[:50] + '…') if len(obj.description) > 50 else (obj.description or '—')


def employee_detail_view(request, employee_id):
    from django.shortcuts import get_object_or_404
    emp_admin = EmployeeAdmin(Employee, admin.site)
    if not emp_admin.has_view_or_change_permission(request):
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=employee_id)
    context = {
        **admin.site.each_context(request),
        "original":              employee,
        "has_add_permission":    emp_admin.has_add_permission(request),
        "has_change_permission": emp_admin.has_change_permission(request, employee),
        "opts":                  Employee._meta,
        "app_label":             Employee._meta.app_label,
        "media":                 emp_admin.media,
    }
    return TemplateResponse(
        request,
        "admin/employees/employee/change_form.html",
        context,
    )