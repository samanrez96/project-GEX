import os

from django.conf import settings
from django.contrib import admin
from django.urls import path, reverse

from common.admin import (
    DECIMAL_FORMFIELD_OVERRIDES,
    JALALI_FORMFIELD_OVERRIDES,
    JalaliAdminDatesMixin,
    MONEY_FORMFIELD_OVERRIDES,
    MoneyInput,
)
from contacts.admin_views import (
    doctor_medical_certificate_view,
    doctor_national_card_view,
    doctor_specialty_activate_view,
    doctor_specialty_create_view,
    doctor_specialty_deactivate_view,
    doctor_specialty_delete_view,
    doctorcontact_change_redirect,
    doctorcontact_changelist_redirect,
)
from contacts.forms import DoctorAdminForm, DoctorSurgeryRateInlineForm
from contacts.models import Doctor, DoctorSurgeryRate

def _asset_version(*relative_path_parts):
    """mtime-based cache-buster for the Specialty widget's JS/CSS.

    Browsers otherwise cache these static files indefinitely (no
    Cache-Control/ETag revalidation is configured for runserver's static
    handler), so an edit here could silently keep serving stale, already
    -open Doctor edit tabs their old script — this forces a fresh fetch
    whenever the source file actually changes.
    """
    path = os.path.join(settings.BASE_DIR, 'static', *relative_path_parts)
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0


# DoctorSpecialty is intentionally NOT registered as a standalone ModelAdmin.
# It has no sidebar entry, no app-index entry, and no changelist of its own —
# it is managed exclusively from inside the Doctor add/edit form via the
# protected JSON endpoints below (doctor_specialty_create_view / _delete_view).


class DoctorSurgeryRateInline(admin.TabularInline):
    """Per-Surgery-Type rate rows, managed directly inside the Doctor
    add/edit form — no standalone DoctorSurgeryRate admin page exists.

    Uses a dedicated template (rather than Django's default
    admin/edit_inline/tabular.html) because the project-wide
    `#content-main .form-row { display: flex; ... }` rule in
    rtl_responsive.css — written for the stacked field rows on the main
    change form — also matches the `tr.form-row` rows Django's default
    tabular-inline template emits, turning each row into a flex container
    and breaking column alignment. The custom template below avoids that
    class entirely instead of touching the shared, project-wide CSS.
    """
    model = DoctorSurgeryRate
    form = DoctorSurgeryRateInlineForm
    fk_name = 'doctor'
    extra = 1
    fields = ('surgery_type', 'rate')
    formfield_overrides = MONEY_FORMFIELD_OVERRIDES
    verbose_name = 'نرخ به ازای نوع عمل'
    verbose_name_plural = 'نرخ‌های پزشک به تفکیک نوع عمل'
    template = 'admin/contacts/doctor/doctor_surgery_rate_inline.html'


@admin.register(Doctor)
class DoctorAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    change_list_template = 'admin/contacts/doctor/change_list.html'
    change_form_template = 'admin/contacts/doctor/change_form.html'
    form = DoctorAdminForm
    formfield_overrides = JALALI_FORMFIELD_OVERRIDES
    inlines = [DoctorSurgeryRateInline]

    list_display = [
        'full_name', 'specialty', 'phone_number', 'clinic_phone',
        'medical_system_number', 'cooperation_status', 'is_active',
    ]
    list_filter = ['cooperation_status', 'is_active', 'specialty']
    search_fields = [
        'full_name', 'specialty__name', 'phone_number', 'clinic_phone',
        'email', 'national_id', 'medical_system_number',
    ]
    ordering = ['full_name']
    readonly_fields = ['created_at_jalali', 'updated_at_jalali']

    fieldsets = (
        ('اطلاعات پایه', {
            'fields': (
                'full_name', 'national_id', 'medical_system_number', 'specialty',
                'collaboration_start_date', 'license_last_renewal_date',
            ),
        }),
        ('اطلاعات تماس', {
            'fields': ('phone_number', 'clinic_phone', 'email', 'address'),
        }),
        ('مدارک پزشک', {
            'fields': ('medical_certificate_image', 'national_card_image'),
        }),
        ('مالی', {
            'fields': ('rate_per_surgery', 'center_commission_percent'),
            'description': 'نرخ هر عمل: مبلغ ثابت دستمزد پزشک به ازای هر عمل جراحی.',
        }),
        ('همکاری', {
            'fields': ('cooperation_status', 'is_active'),
        }),
        ('یادداشت', {
            'fields': ('notes',),
        }),
        ('زمان‌بندی', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield and db_field.name == 'rate_per_surgery':
            formfield.widget = MoneyInput()
        return formfield

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['contacts_directory_js_version'] = _asset_version('admin', 'js', 'contacts_directory.js')
        return super().changelist_view(request, extra_context=extra_context)

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context.update({
            'doctor_specialty_create_url': reverse('admin:contacts_doctor_specialty_create'),
            'doctor_specialty_delete_url_template': reverse('admin:contacts_doctor_specialty_delete', args=[0]),
            'doctor_specialty_deactivate_url_template': reverse('admin:contacts_doctor_specialty_deactivate', args=[0]),
            'doctor_specialty_activate_url_template': reverse('admin:contacts_doctor_specialty_activate', args=[0]),
            'doctor_current_specialty_id': obj.specialty_id if obj else None,
            'can_add_doctorspecialty': request.user.has_perm('contacts.add_doctorspecialty'),
            'can_delete_doctorspecialty': request.user.has_perm('contacts.delete_doctorspecialty'),
            'can_change_doctorspecialty': request.user.has_perm('contacts.change_doctorspecialty'),
            'doctor_specialty_js_version': _asset_version('admin', 'js', 'doctor_specialty.js'),
            'doctor_specialty_css_version': _asset_version('admin', 'css', 'doctor_specialty.css'),
            'doctor_documents_css_version': _asset_version('admin', 'css', 'doctor_documents.css'),
            'doctor_surgery_rate_css_version': _asset_version('admin', 'css', 'doctor_surgery_rate.css'),
            'doctor_surgery_rate_js_version': _asset_version('admin', 'js', 'doctor_surgery_rate.js'),
        })
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)


# ---------------------------------------------------------------------------
# Monkey-patch admin site URLs:
#   - compat redirects for the pre-rename DoctorContact admin URLs
#   - protected JSON utility endpoints for Specialty management from the
#     Doctor form (no standalone Specialty admin page)
# Chains after any previously-applied get_urls patch (finance/misc_expenses).
# ---------------------------------------------------------------------------

_original_get_urls = admin.site.__class__.get_urls


def _patched_get_urls(self):
    base = _original_get_urls(self)
    extra = [
        path(
            'contacts/doctorcontact/',
            self.admin_view(doctorcontact_changelist_redirect),
            name='contacts_doctorcontact_changelist_redirect',
        ),
        path(
            'contacts/doctorcontact/<int:pk>/change/',
            self.admin_view(doctorcontact_change_redirect),
            name='contacts_doctorcontact_change_redirect',
        ),
        path(
            'contacts/doctor-specialties/create/',
            self.admin_view(doctor_specialty_create_view),
            name='contacts_doctor_specialty_create',
        ),
        path(
            'contacts/doctor-specialties/<int:pk>/delete/',
            self.admin_view(doctor_specialty_delete_view),
            name='contacts_doctor_specialty_delete',
        ),
        path(
            'contacts/doctor-specialties/<int:pk>/deactivate/',
            self.admin_view(doctor_specialty_deactivate_view),
            name='contacts_doctor_specialty_deactivate',
        ),
        path(
            'contacts/doctor-specialties/<int:pk>/activate/',
            self.admin_view(doctor_specialty_activate_view),
            name='contacts_doctor_specialty_activate',
        ),
        path(
            'contacts/doctor/<int:pk>/documents/medical-certificate/',
            self.admin_view(doctor_medical_certificate_view),
            name='contacts_doctor_medical_certificate',
        ),
        path(
            'contacts/doctor/<int:pk>/documents/national-card/',
            self.admin_view(doctor_national_card_view),
            name='contacts_doctor_national_card',
        ),
    ]
    return extra + base


admin.site.__class__.get_urls = _patched_get_urls
