from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from common.excel import ExcelColumn, ExcelExportMixin, describe_ordering
from contacts.models import CooperationStatus, Doctor, DoctorSpecialty
from contacts.serializers import (
    DoctorListSerializer,
    DoctorSerializer,
    EmployeeContactSerializer,
)
from employees.models import Employee


class DoctorViewSet(ExcelExportMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'cooperation_status', 'specialty']
    search_fields = [
        'full_name', 'specialty__name', 'phone_number', 'clinic_phone',
        'email', 'national_id', 'medical_system_number',
    ]
    ordering_fields = ['full_name', 'specialty__name', 'created_at']
    ordering = ['full_name']

    def get_serializer_class(self):
        if self.action == 'list':
            return DoctorListSerializer
        return DoctorSerializer

    def get_queryset(self):
        return Doctor.objects.select_related('specialty').all().distinct()

    # ── Excel export ──────────────────────────────────────────────────────────
    #
    # General doctor directory export — no commission percentage or
    # per-surgery rate is exported here, since those are financial figures
    # that belong to a permission-gated financial report, not the general
    # contacts directory. Document image paths are never exported.

    excel_filename_prefix = 'doctor-list'
    excel_sheet_title      = 'پزشکان'
    excel_report_title     = 'گزارش فهرست پزشکان'

    _ORDERING_LABELS = {
        'full_name':       'نام و نام خانوادگی',
        'specialty__name': 'تخصص',
        'created_at':       'تاریخ ثبت',
    }

    def get_excel_meta_rows(self, request):
        params = request.query_params
        meta = []

        is_active_val = params.get('is_active')
        if is_active_val:
            meta.append(('وضعیت', {'true': 'فعال', 'false': 'غیرفعال'}.get(is_active_val, is_active_val)))

        coop_val = params.get('cooperation_status')
        if coop_val:
            meta.append(('وضعیت همکاری', dict(CooperationStatus.choices).get(coop_val, coop_val)))

        specialty_id = params.get('specialty')
        if specialty_id:
            specialty = DoctorSpecialty.objects.filter(pk=specialty_id).first()
            meta.append(('تخصص', specialty.name if specialty else specialty_id))

        search_val = params.get('search')
        if search_val:
            meta.append(('جستجو', search_val))

        ordering_desc = describe_ordering(params.get('ordering'), self._ORDERING_LABELS)
        if ordering_desc:
            meta.append(('مرتب‌سازی', ordering_desc))

        return meta

    def get_excel_columns(self, request):
        return [
            ExcelColumn(key='row_number',  label='ردیف',                data_type='integer', width=6),
            ExcelColumn(key='full_name',    label='نام و نام خانوادگی', data_type='text', width=24),
            ExcelColumn(key='specialty_name', label='تخصص',              data_type='text', width=18),
            ExcelColumn(key='national_id',  label='کد ملی',              data_type='text', width=14),
            ExcelColumn(key='medical_system_number', label='شماره نظام پزشکی', data_type='text', width=16),
            ExcelColumn(key='phone_number', label='شماره تلفن همراه',    data_type='text', width=14),
            ExcelColumn(key='clinic_phone', label='تلفن مطب/کلینیک',    data_type='text', width=16),
            ExcelColumn(key='email',        label='ایمیل',               data_type='text', width=22),
            ExcelColumn(key='cooperation_status_display', label='وضعیت همکاری', data_type='text', width=12),
            ExcelColumn(key='collaboration_start_date', label='تاریخ شروع همکاری', data_type='date', width=13),
            ExcelColumn(key='is_active_display', label='وضعیت',          data_type='text', width=10),
        ]

    def get_excel_summary(self, request, queryset):
        doctors = list(queryset)
        total  = len(doctors)
        active = sum(1 for d in doctors if d.is_active)
        return [
            ('تعداد کل پزشکان', total),
            ('تعداد فعال',       active),
            ('تعداد غیرفعال',    total - active),
        ]

    def queryset_to_excel_rows(self, queryset):
        for idx, doctor in enumerate(queryset, start=1):
            yield {
                'row_number':                idx,
                'full_name':                 doctor.full_name,
                'specialty_name':            doctor.specialty.name if doctor.specialty_id else None,
                'national_id':               doctor.national_id,
                'medical_system_number':     doctor.medical_system_number,
                'phone_number':              doctor.phone_number,
                'clinic_phone':              doctor.clinic_phone,
                'email':                     doctor.email,
                'cooperation_status_display': doctor.get_cooperation_status_display(),
                'collaboration_start_date':  doctor.collaboration_start_date,
                'is_active_display':         'فعال' if doctor.is_active else 'غیرفعال',
            }


class EmployeeContactViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """Read-only contact view for employees.
    GET /api/v1/contacts/employees/
    GET /api/v1/contacts/employees/{id}/
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'job_position']
    search_fields = ['full_name', 'personal_phone', 'email', 'job_position__name']
    ordering_fields = ['full_name', 'job_position__name']
    ordering = ['full_name']
    serializer_class = EmployeeContactSerializer

    def get_queryset(self):
        return Employee.objects.select_related('job_position').all()
