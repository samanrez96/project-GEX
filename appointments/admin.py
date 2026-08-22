import os

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import path

from common.admin import JALALI_FORMFIELD_OVERRIDES, JalaliAdminDatesMixin
from common.admin_site import register_extra_urls
from .models import Appointment, AppointmentStatus


def _asset_version(*relative_path_parts):
    """mtime-based cache-buster — mirrors contacts/admin.py::_asset_version."""
    path_ = os.path.join(settings.BASE_DIR, 'static', *relative_path_parts)
    try:
        return int(os.path.getmtime(path_))
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Calendar page — custom admin view (the primary UI for this app)
# ---------------------------------------------------------------------------

@staff_member_required
def appointments_calendar_view(request):
    context = {
        **admin.site.each_context(request),
        'title': 'نوبت‌دهی',
        'appointments_calendar_css_version': _asset_version('admin', 'css', 'appointments_calendar.css'),
        'appointments_calendar_js_version':  _asset_version('admin', 'js', 'appointments_calendar.js'),
        'has_add_permission': request.user.has_perm('appointments.add_appointment'),
    }
    return render(request, 'admin/appointments/calendar.html', context)


def _appointments_extra_urls(site):
    return [
        path(
            'appointments/calendar/',
            site.admin_view(appointments_calendar_view),
            name='appointments_calendar',
        ),
    ]


register_extra_urls(_appointments_extra_urls)


# ---------------------------------------------------------------------------
# Plain ModelAdmin — provides the add/change forms the calendar page links
# to (prefilled via GET params, same pattern as HourlyWorkEntry's quick-add
# link from the employee payroll tab). Not linked from the sidebar itself —
# the calendar page is the primary entry point.
# ---------------------------------------------------------------------------

@admin.register(Appointment)
class AppointmentAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = [
        'display_patient_name', 'doctor', 'visit_date_jalali', 'start_time',
        'duration_minutes', 'status', 'reason',
    ]
    list_filter     = ['status', 'doctor']
    search_fields   = ['patient__full_name', 'patient_name', 'reason']
    autocomplete_fields = ['doctor', 'patient']
    ordering        = ['-visit_date', '-start_time']
    readonly_fields = ['created_at_jalali', 'updated_at_jalali']
    formfield_overrides = JALALI_FORMFIELD_OVERRIDES
    fieldsets = (
        ('بیمار', {
            'fields': ('patient', 'patient_name', 'patient_phone'),
        }),
        ('زمان‌بندی', {
            'fields': ('doctor', 'visit_date', 'start_time', 'duration_minutes'),
        }),
        ('جزئیات', {
            'fields': ('status', 'reason', 'description'),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='تاریخ ویزیت', ordering='visit_date')
    def visit_date_jalali(self, obj):
        from common.dates import to_jalali_date
        return to_jalali_date(obj.visit_date)

    @admin.display(description='بیمار')
    def display_patient_name(self, obj):
        return obj.display_patient_name

    def response_add(self, request, obj, post_url_continue=None):
        """After adding from the calendar page, go back to the calendar
        instead of Django's default changelist — there is no changelist
        page anyone is expected to browse directly."""
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        if '_continue' not in request.POST and '_addanother' not in request.POST:
            return HttpResponseRedirect(reverse('admin:appointments_calendar'))
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        if '_continue' not in request.POST and '_addanother' not in request.POST:
            return HttpResponseRedirect(reverse('admin:appointments_calendar'))
        return super().response_change(request, obj)
