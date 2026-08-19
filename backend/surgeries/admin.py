import os
from decimal import Decimal

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import OuterRef, Subquery
from django.urls import path, reverse

from accounts.permissions import is_main_administrator
from common.admin import (
    DECIMAL_FORMFIELD_OVERRIDES as _DECIMAL_OVERRIDES,
    JALALI_FORMFIELD_OVERRIDES as _JALALI_DATE_OVERRIDES,
    JalaliAdminDatesMixin,
    JalaliDateWidget,
    JalaliFormDateForDateTimeField,
    MoneyInput,
    clean_decimal_display,
)
from common.dates import to_jalali_date, to_jalali_datetime
from common.excel import AdminExcelExportMixin, ExcelColumn
from surgeries.admin_views import (
    anesthesia_type_activate_view,
    anesthesia_type_create_view,
    anesthesia_type_deactivate_view,
    anesthesia_type_delete_view,
)
from surgeries.forms import PatientAdminForm, SurgeryHistoryAdminForm
from surgeries.models import (
    AnesthesiaType, Patient, Surgery, SurgeryConsumptionItem, SurgeryHistory, SurgeryType, SurgeryUsedItem,
)


# ---------------------------------------------------------------------------
# Custom AdminSite – replaces the default to avoid monkey‑patching
# ---------------------------------------------------------------------------

class SurgeriesAdminSite(admin.AdminSite):
    """Custom admin site for the surgeries app.

    Adds custom URLs for detail views and AnesthesiaType management.
    """
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'surgeryhistory/<int:surgery_id>/detail/',
                self.admin_view(surgery_history_detail_view),
                name='surgeries_surgeryhistory_detail',
            ),
            path(
                'anesthesia-type/create/',
                self.admin_view(anesthesia_type_create_view),
                name='surgeries_anesthesia_type_create',
            ),
            path(
                'anesthesia-type/<int:pk>/delete/',
                self.admin_view(anesthesia_type_delete_view),
                name='surgeries_anesthesia_type_delete',
            ),
            path(
                'anesthesia-type/<int:pk>/deactivate/',
                self.admin_view(anesthesia_type_deactivate_view),
                name='surgeries_anesthesia_type_deactivate',
            ),
            path(
                'anesthesia-type/<int:pk>/activate/',
                self.admin_view(anesthesia_type_activate_view),
                name='surgeries_anesthesia_type_activate',
            ),
        ]
        return custom + urls


# Replace the default admin site with our custom one
admin.site = SurgeriesAdminSite()


_PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹'


def _asset_version(*relative_path_parts):
    """mtime-based cache-buster for the AnesthesiaType widget's JS/CSS.

    Mirrors contacts/admin.py::_asset_version — browsers otherwise cache
    these static files indefinitely, so an edit here could silently keep
    serving an already-open Surgery edit tab its old script.
    """
    path_ = os.path.join(settings.BASE_DIR, 'static', *relative_path_parts)
    try:
        return int(os.path.getmtime(path_))
    except OSError:
        return 0


def _fmt_money(value):
    """Format a Decimal/int as Persian digits with ٬ thousands separator.

    e.g. 12000000 → ۱۲٬۰۰۰٬۰۰۰
    """
    try:
        n = int(Decimal(str(value)).quantize(Decimal('1')))
        raw = f'{abs(n):,}'.replace(',', '٬')
        persian = ''.join(_PERSIAN_DIGITS[int(c)] if c.isdigit() else c for c in raw)
        return ('-' + persian) if n < 0 else persian
    except Exception:
        return '—'


# ---------------------------------------------------------------------------
# Patient admin
# ---------------------------------------------------------------------------

class PatientVisibilityFilter(admin.SimpleListFilter):
    """Superuser-only filter — only ever added to list_filter for the main
    administrator (see PatientAdmin.get_list_filter), since non-superusers
    never see hidden Patients regardless of this filter's value.

    Rendered with a custom compact <select> template (instead of Django's
    default sidebar <ul>) so it sits inline in the search/filter card,
    matching the Employee list page's filter presentation — see
    templates/admin/surgeries/patient/visibility_filter_select.html and
    the `search` block override in change_list.html. The filtering
    behavior itself (queryset(), value() via ?visibility=) is entirely
    Django's own SimpleListFilter machinery, unchanged.
    """

    title = 'وضعیت نمایش'
    parameter_name = 'visibility'
    template = 'admin/surgeries/patient/visibility_filter_select.html'

    def lookups(self, request, model_admin):
        return (
            ('visible', 'قابل مشاهده'),
            ('hidden',  'مخفی'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'visible':
            return queryset.filter(is_hidden=False)
        if self.value() == 'hidden':
            return queryset.filter(is_hidden=True)
        return queryset


@admin.register(Patient)
class PatientAdmin(AdminExcelExportMixin, JalaliAdminDatesMixin, admin.ModelAdmin):
    # Both templates only extend Django's own change_form.html/change_list.html
    # to inject a dedicated CSS file (and, for the list page, swap the
    # object-tools block for the shared adm-page-header component) — same
    # pattern as EmployeeAdmin.change_form_template /
    # SurgeryHistoryAdmin.change_list_template. Search, bulk actions, and
    # the add/edit form fields themselves are untouched Django rendering.
    change_form_template = 'admin/surgeries/patient/patient_edit_form.html'
    change_list_template = 'admin/surgeries/patient/change_list.html'
    form = PatientAdminForm

    list_display    = (
        'case_code', 'internal_code', 'full_name', 'national_id', 'phone_number',
        'get_latest_surgery_date', 'get_latest_doctor',
    )
    search_fields   = ('full_name', 'case_code', 'internal_code', 'national_id', 'phone_number')
    ordering        = ('-created_at',)
    actions         = ('hide_selected_patients', 'unhide_selected_patients')

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield and db_field.name == 'description':
            formfield.widget.attrs.update({'rows': 4})
        if formfield and db_field.name == 'is_hidden':
            formfield.label = 'مخفی کردن بیمار'
            formfield.help_text = (
                'بیمار مخفی فقط برای مدیر اصلی سیستم قابل مشاهده است '
                'و در خروجی‌های اکسل عادی قرار نمی‌گیرد.'
            )
        return formfield

    # ── Visibility (hidden Patient) ─────────────────────────────────────────
    #
    # Canonical rule lives on Patient.objects.visible_to(user) — this admin
    # (list, detail/change via get_object, search, autocomplete for other
    # admins' FK fields) all go through get_queryset() below, so there is
    # exactly one place enforcing it for the whole admin surface.

    def get_queryset(self, request):
        qs = super().get_queryset(request).visible_to(request.user)
        latest_date = (
            SurgeryHistory.objects
            .filter(patient=OuterRef('pk'))
            .exclude(status='CANCELLED')
            .order_by('-surgery_date')
            .values('surgery_date')[:1]
        )
        # clinical_doctor is the treating doctor (Doctor.full_name)
        latest_doctor = (
            SurgeryHistory.objects
            .filter(patient=OuterRef('pk'))
            .exclude(status='CANCELLED')
            .order_by('-surgery_date')
            .values('clinical_doctor__full_name')[:1]
        )
        return qs.annotate(
            _latest_surgery_date=Subquery(latest_date),
            _latest_doctor_name=Subquery(latest_doctor),
        )

    @admin.display(description='تاریخ آخرین عمل', ordering='_latest_surgery_date')
    def get_latest_surgery_date(self, obj):
        val = getattr(obj, '_latest_surgery_date', None)
        if val is None:
            return '—'
        return to_jalali_date(val)

    @admin.display(description='پزشک معالج', ordering='_latest_doctor_name')
    def get_latest_doctor(self, obj):
        return getattr(obj, '_latest_doctor_name', None) or '—'

    def get_list_filter(self, request):
        if is_main_administrator(request.user):
            return (PatientVisibilityFilter,)
        return ()

    def get_fieldsets(self, request, obj=None):
        base = [
            ('اطلاعات بیمار', {
                'classes': ('patient-form-card',),
                'fields': (
                    'full_name',
                    ('national_id', 'case_code', 'internal_code'),
                    ('age', 'gender'),
                    'phone_number',
                    'description',
                ),
            }),
            ('آخرین عمل', {
                'fields': ('get_latest_surgery_date', 'get_latest_doctor'),
            }),
        ]
        if is_main_administrator(request.user):
            base.append(('وضعیت و دسترسی', {
                'classes': ('patient-status-section',),
                'fields': ('is_hidden', 'get_hidden_audit_display'),
            }))
        base.append(('زمان‌بندی', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }))
        return tuple(base)

    def get_readonly_fields(self, request, obj=None):
        readonly = ['created_at_jalali', 'updated_at_jalali', 'get_latest_surgery_date', 'get_latest_doctor']
        if is_main_administrator(request.user):
            readonly.append('get_hidden_audit_display')
        return readonly

    @admin.display(description='مخفی‌سازی توسط')
    def get_hidden_audit_display(self, obj):
        if not obj or not obj.pk or not obj.is_hidden:
            return '—'
        who = obj.hidden_by.get_username() if obj.hidden_by else 'نامشخص'
        when = to_jalali_datetime(obj.hidden_at) if obj.hidden_at else '—'
        return f'{who} — {when}'

    def save_model(self, request, obj, form, change):
        if is_main_administrator(request.user) and change and 'is_hidden' in form.changed_data:
            if obj.is_hidden:
                obj.hide(request.user)
                self.message_user(request, 'بیمار با موفقیت مخفی شد.')
            else:
                obj.unhide()
                self.message_user(request, 'بیمار با موفقیت از حالت مخفی خارج شد.')
            return
        super().save_model(request, obj, form, change)

    # ── Bulk hide/restore actions ────────────────────────────────────────────

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not is_main_administrator(request.user):
            actions.pop('hide_selected_patients', None)
            actions.pop('unhide_selected_patients', None)
        return actions

    @admin.action(description='مخفی کردن بیماران انتخاب‌شده')
    def hide_selected_patients(self, request, queryset):
        if not is_main_administrator(request.user):
            raise PermissionDenied
        count = 0
        for patient in Patient.objects.visible_to(request.user).filter(pk__in=queryset.values_list('pk', flat=True)):
            if not patient.is_hidden:
                patient.hide(request.user)
                count += 1
        self.message_user(request, 'بیمار با موفقیت مخفی شد.' if count == 1 else f'{count} بیمار با موفقیت مخفی شد.')

    @admin.action(description='نمایش مجدد بیماران انتخاب‌شده')
    def unhide_selected_patients(self, request, queryset):
        if not is_main_administrator(request.user):
            raise PermissionDenied
        count = 0
        for patient in Patient.objects.visible_to(request.user).filter(pk__in=queryset.values_list('pk', flat=True)):
            if patient.is_hidden:
                patient.unhide()
                count += 1
        self.message_user(request, 'بیمار با موفقیت از حالت مخفی خارج شد.' if count == 1 else f'{count} بیمار با موفقیت از حالت مخفی خارج شدند.')

    # ── Excel export ──────────────────────────────────────────────────────────
    excel_filename_prefix = 'patient-list'
    excel_sheet_title      = 'بیماران'
    excel_report_title     = 'گزارش فهرست بیماران'

    def get_urls(self):
        return self.get_excel_urls() + super().get_urls()

    def get_excel_export_queryset(self, request, cl):
        return cl.queryset.filter(is_hidden=False)

    def get_excel_columns(self, request):
        return [
            ExcelColumn(key='row_number', label='ردیف', data_type='integer', width=6),
            ExcelColumn(key='case_code', label='کد پرونده', data_type='text', width=14),
            ExcelColumn(key='internal_code', label='کد داخلی بیمار', data_type='text', width=16),
            ExcelColumn(key='full_name', label='نام کامل', data_type='text', width=22),
            ExcelColumn(key='age', label='سن بیمار', data_type='integer', width=10),
            ExcelColumn(key='gender', label='جنسیت', data_type='text', width=10),
            ExcelColumn(key='national_id', label='کد ملی', data_type='text', width=14),
            ExcelColumn(key='phone_number', label='شماره موبایل', data_type='text', width=14),
            ExcelColumn(key='latest_surgery_date', label='تاریخ آخرین عمل', data_type='date', width=14),
            ExcelColumn(key='latest_doctor', label='پزشک معالج', data_type='text', width=18),
        ]

    def get_excel_rows(self, request, objects):
        return [
            {
                'row_number':          idx,
                'case_code':           p.case_code,
                'internal_code':       p.internal_code,
                'full_name':           p.full_name,
                'age':                 p.age,
                'gender':              p.get_gender_display() if p.gender else None,
                'national_id':         p.national_id,
                'phone_number':        p.phone_number,
                'latest_surgery_date': getattr(p, '_latest_surgery_date', None),
                'latest_doctor':       getattr(p, '_latest_doctor_name', None),
            }
            for idx, p in enumerate(objects, start=1)
        ]

    def get_excel_summary(self, request, objects):
        return [('تعداد کل بیماران', len(objects))]


# ---------------------------------------------------------------------------
# SurgeryConsumptionItem inline — embedded inside SurgeryAdmin
# ---------------------------------------------------------------------------

class SurgeryConsumptionItemInline(JalaliAdminDatesMixin, admin.TabularInline):
    model               = SurgeryConsumptionItem
    fk_name             = "surgery"
    extra               = 0
    formfield_overrides = _DECIMAL_OVERRIDES
    readonly_fields     = ("unit", "created_at_jalali", "updated_at_jalali")
    fields              = ("product", "quantity", "unit", "notes", "created_at_jalali", "updated_at_jalali")
    verbose_name        = "قلم مصرف"
    verbose_name_plural = "اقلام مصرف"


# ---------------------------------------------------------------------------
# Surgery admin (legacy — old model, keep intact)
# ---------------------------------------------------------------------------

@admin.register(Surgery)
class SurgeryAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ("pk", "patient_name", "surgeon_name", "surgery_date_jalali", "status", "stock_applied", "created_at_jalali")
    list_filter     = ("status", "stock_applied")
    search_fields   = ("patient_name", "surgeon_name", "notes")
    ordering        = ("-surgery_date", "-created_at")
    readonly_fields = ("stock_applied", "created_at_jalali", "updated_at_jalali")
    date_hierarchy  = "surgery_date"
    inlines         = [SurgeryConsumptionItemInline]
    formfield_overrides = {**_JALALI_DATE_OVERRIDES, **_DECIMAL_OVERRIDES}

    fieldsets = (
        ("اطلاعات عمل جراحی", {
            "fields": ("patient_name", "surgeon_name", "surgery_date", "status", "notes"),
        }),
        ("وضعیت موجودی", {
            "fields": ("stock_applied",),
            "description": "پس از تکمیل عمل، حرکات موجودی OUT برای هر قلم مصرف ایجاد می‌شوند.",
        }),
        ("زمان‌بندی", {
            "fields": ("created_at_jalali", "updated_at_jalali"),
            "classes": ("collapse",),
        }),
    )


# ---------------------------------------------------------------------------
# SurgeryConsumptionItem standalone admin
# ---------------------------------------------------------------------------

@admin.register(SurgeryConsumptionItem)
class SurgeryConsumptionItemAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ("pk", "surgery", "product", "get_quantity_display", "unit", "created_at_jalali")
    list_filter     = ("surgery__status",)
    search_fields   = ("surgery__patient_name", "product__name", "product__internal_code", "notes")
    ordering        = ("-created_at",)
    readonly_fields = ("unit", "created_at_jalali", "updated_at_jalali")
    formfield_overrides = _DECIMAL_OVERRIDES

    @admin.display(description='مقدار', ordering='quantity')
    def get_quantity_display(self, obj):
        return clean_decimal_display(obj.quantity)


# ---------------------------------------------------------------------------
# SurgeryType admin
# ---------------------------------------------------------------------------

@admin.register(SurgeryType)
class SurgeryTypeAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = ['name', 'code', 'get_base_rate_display', 'get_commission_rule_count', 'is_active', 'created_at_jalali']
    list_filter     = ['is_active']
    search_fields   = ['name', 'code']
    readonly_fields = ['get_commission_rule_count', 'created_at_jalali', 'updated_at_jalali']
    fieldsets = (
        ('اطلاعات عمل', {
            'fields': ('name', 'code', 'base_rate', 'description', 'is_active'),
        }),
        ('آمار', {
            'fields': ('get_commission_rule_count',),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    formfield_overrides = _DECIMAL_OVERRIDES

    @admin.display(description='نرخ پایه', ordering='base_rate')
    def get_base_rate_display(self, obj):
        return clean_decimal_display(obj.base_rate)

    @admin.display(description='قوانین کمیسیون فعال')
    def get_commission_rule_count(self, obj):
        return obj.get_active_commission_rule_count()


# ---------------------------------------------------------------------------
# SurgeryHistory admin
# ---------------------------------------------------------------------------

@admin.register(SurgeryHistory)
class SurgeryHistoryAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    change_list_template = 'admin/surgeries/surgeryhistory/change_list.html'
    change_form_template = 'admin/surgeries/surgeryhistory/edit_form.html'
    form = SurgeryHistoryAdminForm
    formfield_overrides  = {**_JALALI_DATE_OVERRIDES, **_DECIMAL_OVERRIDES}

    list_display    = (
        'patient', 'surgery_type', 'clinical_doctor',
        'surgery_date', 'get_amount_display',
        'get_university_share', 'get_doctor_share',
        'payment_status', 'status',
    )
    list_filter     = ('status', 'payment_status', 'surgery_type')
    search_fields   = (
        'patient__full_name', 'patient__case_code', 'patient__national_id',
        'case_code', 'medical_record_code', 'phone_number', 'description',
        'clinical_doctor__full_name', 'clinical_doctor__specialty__name',
    )
    ordering        = ('-surgery_date', '-created_at')
    readonly_fields = ('case_code', 'phone_number', 'created_at_jalali', 'updated_at_jalali', 'get_university_share', 'get_doctor_share')
    formfield_overrides = _JALALI_DATE_OVERRIDES
    autocomplete_fields = ('patient', 'clinical_doctor')
    date_hierarchy  = 'surgery_date'

    fieldsets = (
        ('اطلاعات عمومی عمل', {
            'fields': (
                'patient', 'surgery_type', 'surgery_date', 'clinical_doctor',
                'assistant_surgeon', 'second_assistant_surgeon',
                'scrub_employee', 'circulator_employee',
                'anesthesiologist', 'anesthesia_technician', 'anesthesia_type',
                'surgery_start_time', 'surgery_end_time',
                'operating_room_manager', 'service_employee',
                'postoperative_diagnosis', 'operation_description',
                'status',
            ),
        }),
        ('اطلاعات بیمار', {
            'fields': ('case_code', 'medical_record_code', 'phone_number'),
            'description': 'پس از انتخاب بیمار، ردیف و شماره موبایل خودکار پر می‌شود.',
        }),
        ('مالی', {
            'fields': ('amount', 'get_university_share', 'get_doctor_share', 'payment_status'),
            'description': 'سهم دانشگاه ۴۵٪ و کمیسیون مرکز جراحی ۵۵٪ از مبلغ عمل محاسبه می‌شود.',
        }),
        ('کمیسیون مرکز', {
            'fields': ('center_commission_percent', 'center_commission_amount'),
            'classes': ('collapse',),
        }),
        ('محاسبه کمیسیون پرسنل (حسابداری)', {
            'fields': ('doctor_or_therapist',),
            'classes': ('collapse',),
            'description': 'اگر کارمندی عمل را انجام داده و باید کمیسیون پرسنلی محاسبه شود، اینجا وارد کنید.',
        }),
        ('زمان‌بندی', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).visible_to(request.user)

    @admin.display(description='مبلغ', ordering='amount')
    def get_amount_display(self, obj):
        return clean_decimal_display(obj.amount)

    @admin.display(description='سهم دانشگاه (۴۵٪)')
    def get_university_share(self, obj):
        if obj and obj.amount:
            val = (obj.amount * Decimal('45') / Decimal('100')).quantize(Decimal('1'))
            return f'{_fmt_money(val)} تومان'
        return '—'

    @admin.display(description='کمیسیون مرکز جراحی (۵۵٪)')
    def get_doctor_share(self, obj):
        if obj and obj.amount:
            val = (obj.amount * Decimal('55') / Decimal('100')).quantize(Decimal('1'))
            return f'{_fmt_money(val)} تومان'
        return '—'

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'surgery_date':
            kwargs['form_class'] = JalaliFormDateForDateTimeField
            kwargs['widget'] = JalaliDateWidget
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield and db_field.name in ('amount', 'center_commission_amount'):
            formfield.widget = MoneyInput()
        if formfield and db_field.name == 'postoperative_diagnosis':
            formfield.widget.attrs.update({'rows': 4})
        if formfield and db_field.name == 'operation_description':
            formfield.widget.attrs.update({'rows': 8})
        return formfield

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context.update({
            'anesthesia_type_create_url': reverse('admin:surgeries_anesthesia_type_create'),
            'anesthesia_type_delete_url_template': reverse('admin:surgeries_anesthesia_type_delete', args=[0]),
            'anesthesia_type_deactivate_url_template': reverse('admin:surgeries_anesthesia_type_deactivate', args=[0]),
            'anesthesia_type_activate_url_template': reverse('admin:surgeries_anesthesia_type_activate', args=[0]),
            'surgery_current_anesthesia_type_id': obj.anesthesia_type_id if obj else None,
            'can_add_anesthesiatype': request.user.has_perm('surgeries.add_anesthesiatype'),
            'can_delete_anesthesiatype': request.user.has_perm('surgeries.delete_anesthesiatype'),
            'can_change_anesthesiatype': request.user.has_perm('surgeries.change_anesthesiatype'),
            'anesthesia_type_css_version': _asset_version('admin', 'css', 'doctor_specialty.css'),
            'anesthesia_type_js_version': _asset_version('admin', 'js', 'anesthesia_type.js'),
            'patient_metadata_css_version': _asset_version('admin', 'css', 'patient_metadata.css'),
            'patient_metadata_js_version': _asset_version('admin', 'js', 'patient_metadata.js'),
        })
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    # get_urls is no longer needed; all custom URLs are now in SurgeriesAdminSite


# ---------------------------------------------------------------------------
# SurgeryHistory detail standalone view — read-only tab UI
# No @admin.site.admin_view here — already wrapped in get_urls.
# ---------------------------------------------------------------------------

def surgery_history_detail_view(request, surgery_id):
    from django.shortcuts import get_object_or_404
    from django.template.response import TemplateResponse
    sha = SurgeryHistoryAdmin(SurgeryHistory, admin.site)
    if not sha.has_view_or_change_permission(request):
        raise PermissionDenied
    surgery = get_object_or_404(
        SurgeryHistory.objects.visible_to(request.user)
        .select_related('patient', 'surgery_type', 'clinical_doctor', 'doctor_or_therapist'),
        pk=surgery_id,
    )
    context = {
        **admin.site.each_context(request),
        'original':              surgery,
        'has_add_permission':    sha.has_add_permission(request),
        'has_change_permission': sha.has_change_permission(request, surgery),
        'opts':                  SurgeryHistory._meta,
        'app_label':             SurgeryHistory._meta.app_label,
        'media':                 sha.media,
        'surgery_history_detail_js_version': _asset_version('admin', 'js', 'surgery_history_detail.js'),
        'surgery_history_detail_css_version': _asset_version('admin', 'css', 'surgery_history_detail.css'),
    }
    return TemplateResponse(request, 'admin/surgeries/surgeryhistory/change_form.html', context)


# ---------------------------------------------------------------------------
# SurgeryUsedItem inline + standalone admin
# ---------------------------------------------------------------------------

class SurgeryUsedItemInline(JalaliAdminDatesMixin, admin.TabularInline):
    model               = SurgeryUsedItem
    fk_name             = 'surgery'
    extra               = 0
    formfield_overrides = _DECIMAL_OVERRIDES
    readonly_fields     = ('unit', 'created_at_jalali', 'updated_at_jalali')
    fields              = ('product', 'quantity', 'unit', 'description', 'created_at_jalali', 'updated_at_jalali')


@admin.register(SurgeryUsedItem)
class SurgeryUsedItemAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    """View-only. Every stock-affecting change (create/edit quantity or
    product/delete) must go through SurgeryInventoryService — the ‘اقلام
    مصرفی’ tab on the SurgeryHistory detail page (backed by
    SurgeryUsedItemViewSet) is the only place that happens. Add/change/
    delete are disabled here so this page can never become a second,
    independent path that mutates stock without a compensating movement."""

    list_display    = ('pk', 'surgery', 'product', 'get_quantity_display', 'unit', 'created_at_jalali')
    list_filter     = ('surgery__status',)
    search_fields   = ('surgery__patient__full_name', 'product__name', 'product__internal_code', 'description')
    ordering        = ('-created_at',)
    readonly_fields = ('unit', 'created_at_jalali', 'updated_at_jalali')
    formfield_overrides = _DECIMAL_OVERRIDES

    @admin.display(description='مقدار', ordering='quantity')
    def get_quantity_display(self, obj):
        return clean_decimal_display(obj.quantity)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# The monkey‑patching section has been removed.
# Custom URLs are now added via SurgeriesAdminSite.get_urls().