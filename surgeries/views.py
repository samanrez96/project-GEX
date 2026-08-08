import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, DecimalField as DBDecimalField, ExpressionWrapper, F, Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminOrFinanceUser
from common.excel import (
    EXCEL_MAX_ROWS,
    ExcelColumn,
    ExcelExportMixin,
    ExcelSheet,
    build_excel,
    build_workbook,
    describe_ordering,
    excel_file_response,
    get_display_name,
)
from common.dates import parse_jalali_date
from common.pagination import StandardPagination
from surgeries.filters import SurgeryHistoryFilter
from finance.models import CenterCommissionIncome, IncomeStatus
from payroll.models import CommissionTransaction
from surgeries.models import (
    Patient,
    PaymentStatus,
    Surgery,
    SurgeryConsumptionItem,
    SurgeryHistory,
    SurgeryStatus,
    SurgeryType,
    SurgeryUsedItem,
)
from surgeries.services import SurgeryFinanceService, SurgeryInventoryService
from surgeries.serializers import (
    PatientListSerializer,
    PatientSerializer,
    SurgeryConsumptionItemSerializer,
    SurgeryHistoryListSerializer,
    SurgeryHistorySerializer,
    SurgeryListSerializer,
    SurgeryProfitReportRowSerializer,
    SurgeryProfitReportSummarySerializer,
    SurgerySerializer,
    SurgeryTypeListSerializer,
    SurgeryTypeSerializer,
    SurgeryUsedItemSerializer,
)


class PatientViewSet(viewsets.ModelViewSet):
    """
    GET/POST             /api/v1/surgeries/patients/
    GET/PUT/PATCH/DELETE /api/v1/surgeries/patients/{id}/

    Search: full_name, case_code, internal_code, national_id, phone_number
    Ordering: full_name, created_at
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields      = ['full_name', 'case_code', 'internal_code', 'national_id', 'phone_number']
    ordering_fields    = ['full_name', 'created_at']
    ordering           = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return PatientListSerializer
        return PatientSerializer

    def get_queryset(self):
        return Patient.objects.visible_to(self.request.user)

    def perform_update(self, serializer):
        # is_hidden only ever reaches validated_data for the main
        # administrator (PatientSerializer drops the field for everyone
        # else) — route a real transition through hide()/unhide() so the
        # audit fields stay correct for API-driven changes too, not just
        # the admin change form.
        is_hidden_changing = (
            'is_hidden' in serializer.validated_data
            and serializer.validated_data['is_hidden'] != serializer.instance.is_hidden
        )
        if is_hidden_changing:
            new_value = serializer.validated_data.pop('is_hidden')
            patient = serializer.save()
            if new_value:
                patient.hide(self.request.user)
            else:
                patient.unhide()
            return
        serializer.save()


class SurgeryViewSet(viewsets.ModelViewSet):
    """CRUD viewset for surgical procedures with a complete action.

    GET/POST             /api/v1/surgeries/surgeries/
    GET/PUT/PATCH/DELETE /api/v1/surgeries/surgeries/{id}/
    POST                 /api/v1/surgeries/surgeries/{id}/complete/

    complete/ — transitions status to COMPLETED and creates OUT StockMovements
    for every SurgeryConsumptionItem.  The operation is idempotent: completing
    an already-completed surgery does not create duplicate movements.
    If any product has insufficient stock, HTTP 400 is returned and no stock
    changes are made (the transaction is rolled back atomically).

    Filters (?status=&stock_applied=):
      status, stock_applied

    Search (?search=):
      patient_name, surgeon_name, notes

    Ordering (?ordering=):
      surgery_date, created_at, status  (default: -surgery_date)
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields   = ["status", "stock_applied"]
    search_fields      = ["patient_name", "surgeon_name", "notes"]
    ordering_fields    = ["surgery_date", "created_at", "status"]
    ordering           = ["-surgery_date", "-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return SurgeryListSerializer
        return SurgerySerializer

    def get_queryset(self):
        if self.action == "list":
            return Surgery.objects.prefetch_related("consumption_items")
        return Surgery.objects.prefetch_related("consumption_items__product")

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Mark surgery as COMPLETED and apply OUT stock movements for all items."""
        surgery = self.get_object()
        try:
            surgery.complete()
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)
        serializer = SurgerySerializer(surgery)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SurgeryTypeViewSet(viewsets.ModelViewSet):
    """
    GET/POST             /api/v1/surgeries/types/
    GET/PUT/PATCH/DELETE /api/v1/surgeries/types/{id}/

    Filter: ?is_active=true|false  (manual — avoids DjangoFilterBackend dependency)
    Search: ?search=  (name, code, description)
    Ordering: ?ordering=  (name, base_rate, created_at)

    DELETE is blocked when active CommissionRules exist (CLI-30 stub).
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [SearchFilter, OrderingFilter]
    search_fields      = ['name', 'code', 'description']
    ordering_fields    = ['name', 'base_rate', 'created_at']
    ordering           = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return SurgeryTypeListSerializer
        return SurgeryTypeSerializer

    def get_queryset(self):
        qs = SurgeryType.objects.all()
        is_active = self.request.query_params.get('is_active')
        if is_active == 'true':
            return qs.filter(is_active=True)
        if is_active == 'false':
            return qs.filter(is_active=False)
        return qs

    def destroy(self, request, *args, **kwargs):
        surgery_type = self.get_object()
        if surgery_type.get_active_commission_rule_count() > 0:
            return Response(
                {'detail': 'این نوع عمل دارای قوانین کمیسیون فعال است و قابل حذف نیست.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class SurgeryConsumptionItemViewSet(viewsets.ModelViewSet):
    """CRUD viewset for surgery consumption line items.

    GET/POST             /api/v1/surgeries/consumption-items/
    GET/PUT/PATCH/DELETE /api/v1/surgeries/consumption-items/{id}/

    Items can only be created/modified while the parent Surgery is PLANNED or
    IN_PROGRESS.  The serializer enforces this rule via validate().

    Filters (?surgery=&product=):
      surgery, product

    Ordering (?ordering=):
      created_at  (default: surgery, product name)
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ["surgery", "product"]
    ordering_fields    = ["created_at"]
    ordering           = ["surgery", "product__name"]
    serializer_class   = SurgeryConsumptionItemSerializer

    def get_queryset(self):
        return SurgeryConsumptionItem.objects.select_related("surgery", "product")


class SurgeryHistoryOrderingFilter(OrderingFilter):
    """OrderingFilter with a stable secondary key when sorting by surgery_date.

    Multiple surgeries commonly share the same surgery_date (several
    operations on the same day), so ``ordering=surgery_date``/``-surgery_date``
    alone leaves same-date rows in a database-dependent, unstable order —
    pagination can then show a row twice (or skip it) across page loads.
    Appending ``id`` (same direction) as a tiebreaker makes the order
    deterministic without altering the primary sort the user requested.
    """

    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if not ordering:
            return ordering
        expanded = []
        for term in ordering:
            expanded.append(term)
            if term == 'surgery_date':
                expanded.append('id')
            elif term == '-surgery_date':
                expanded.append('-id')
        return expanded


class SurgeryHistoryViewSet(ExcelExportMixin, viewsets.ModelViewSet):
    """
    GET/POST             /api/v1/surgeries/history/
    GET/PUT/PATCH/DELETE /api/v1/surgeries/history/{id}/

    Filter: patient, surgery_type, status, payment_status, doctor_or_therapist
    Search: patient name, case_code, phone_number, description
    Ordering: surgery_date, amount, created_at

    POST and PUT/PATCH automatically create/update the CenterCommissionIncome
    record in finance via SurgeryFinanceService — both saves are atomic.
    """

    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination
    filterset_class    = SurgeryHistoryFilter
    filter_backends    = [DjangoFilterBackend, SearchFilter, SurgeryHistoryOrderingFilter]
    search_fields      = ['patient__full_name', 'case_code', 'medical_record_code', 'phone_number', 'description']
    ordering_fields    = [
        'surgery_date', 'amount', 'patient__full_name',
        'surgery_type__name', 'status', 'payment_status', 'created_at',
    ]
    ordering           = ['-surgery_date', '-id']

    def get_serializer_class(self):
        if self.action == 'list':
            return SurgeryHistoryListSerializer
        return SurgeryHistorySerializer

    def get_queryset(self):
        return SurgeryHistory.objects.visible_to(self.request.user).select_related(
            'patient', 'surgery_type', 'clinical_doctor',
            'doctor_or_therapist', 'center_commission_income',
            'assistant_surgeon', 'second_assistant_surgeon',
            'scrub_employee', 'circulator_employee',
            'anesthesiologist', 'anesthesia_technician', 'anesthesia_type',
            'operating_room_manager', 'service_employee',
        )

    @transaction.atomic
    def perform_create(self, serializer):
        surgery = serializer.save()
        SurgeryFinanceService.sync_center_commission_income(surgery)
        try:
            SurgeryFinanceService.sync_doctor_fee_expense(surgery)
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)

    @transaction.atomic
    def perform_update(self, serializer):
        surgery = serializer.save()
        SurgeryFinanceService.sync_center_commission_income(surgery)
        try:
            SurgeryFinanceService.sync_doctor_fee_expense(surgery)
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)

    # ── Excel export ──────────────────────────────────────────────────────────
    #
    # Two-sheet workbook: "فهرست عمل‌ها" (one row per surgery, with a compact
    # اقلام مصرفی summary column) + "اقلام مصرفی" (one row per consumed item,
    # for anyone who needs the detailed breakdown). Both sheets come from the
    # exact same filtered/ordered queryset _handle_excel_export builds below
    # — filters/search/ordering are never re-implemented for export.

    excel_filename_prefix = 'surgery-list'
    excel_sheet_title      = 'فهرست عمل‌ها'
    excel_report_title     = 'گزارش فهرست عمل‌های جراحی'

    _ORDERING_LABELS = {
        'surgery_date':       'تاریخ عمل',
        'amount':             'مبلغ عمل',
        'patient__full_name': 'نام بیمار',
        'surgery_type__name': 'نوع عمل',
        'status':             'وضعیت عمل',
        'payment_status':     'وضعیت پرداخت',
        'created_at':         'تاریخ ثبت',
    }

    def get_export_queryset(self):
        # Excludes surgeries belonging to a hidden Patient unconditionally
        # — even for the main administrator, whose normal list view may
        # otherwise include them. A separate, superuser-only "include hidden"
        # export is not implemented since nothing currently requires it.
        return SurgeryHistory.objects.filter(patient__is_hidden=False).select_related(
            'patient', 'surgery_type', 'clinical_doctor', 'clinical_doctor__specialty',
            'assistant_surgeon', 'second_assistant_surgeon',
            'scrub_employee', 'circulator_employee',
            'anesthesiologist', 'anesthesia_technician', 'anesthesia_type',
        ).prefetch_related('used_items__product')

    def get_excel_meta_rows(self, request):
        from contacts.models import Doctor

        params = request.query_params
        meta = []

        date_from = params.get('surgery_date_from')
        date_to   = params.get('surgery_date_to')
        if date_from or date_to:
            meta.append(('بازه تاریخ عمل', f"{date_from or '—'} تا {date_to or '—'}"))

        surgery_type_id = params.get('surgery_type')
        if surgery_type_id:
            st = SurgeryType.objects.filter(pk=surgery_type_id).first()
            meta.append(('نوع عمل', st.name if st else surgery_type_id))

        status_val = params.get('status')
        if status_val:
            meta.append(('وضعیت عمل', dict(SurgeryStatus.choices).get(status_val, status_val)))

        payment_status_val = params.get('payment_status')
        if payment_status_val:
            meta.append(('وضعیت پرداخت', dict(PaymentStatus.choices).get(payment_status_val, payment_status_val)))

        doctor_id = params.get('clinical_doctor')
        if doctor_id:
            doctor = Doctor.objects.filter(pk=doctor_id).first()
            meta.append(('جراح', doctor.full_name if doctor else doctor_id))

        patient_id = params.get('patient')
        if patient_id:
            # Scoped to visible_to() so a non-superuser filtering by a
            # hidden Patient's id (the underlying export data is already
            # empty for them) doesn't still leak the patient's name through
            # this metadata line.
            patient = Patient.objects.visible_to(request.user).filter(pk=patient_id).first()
            meta.append(('بیمار', patient.full_name if patient else patient_id))

        min_amount = params.get('min_amount')
        max_amount = params.get('max_amount')
        if min_amount or max_amount:
            meta.append(('بازه مبلغ عمل', f"{min_amount or '—'} تا {max_amount or '—'}"))

        search_val = params.get('search')
        if search_val:
            meta.append(('جستجو', search_val))

        ordering_desc = describe_ordering(params.get('ordering'), self._ORDERING_LABELS)
        if ordering_desc:
            meta.append(('مرتب‌سازی', ordering_desc))

        return meta

    def get_excel_columns(self, request):
        return [
            ExcelColumn(key='row_number',      label='ردیف',                    data_type='integer', width=6),
            ExcelColumn(key='medical_record',   label='کد داخلی عمل',            data_type='text',   width=16),
            ExcelColumn(key='patient_name',     label='نام بیمار',               data_type='text',   width=20),
            ExcelColumn(key='case_code',        label='کد پرونده',               data_type='text',   width=14),
            ExcelColumn(key='internal_code',    label='کد داخلی بیمار',          data_type='text',   width=16),
            ExcelColumn(key='patient_age',      label='سن بیمار',                data_type='integer', width=10),
            ExcelColumn(key='patient_gender',   label='جنسیت بیمار',             data_type='text',   width=12),
            ExcelColumn(key='national_id',      label='کد ملی بیمار',            data_type='text',   width=14),
            ExcelColumn(key='phone_number',     label='شماره موبایل بیمار',      data_type='text',   width=15),
            ExcelColumn(key='doctor_name',      label='نام جراح/درمانگر',        data_type='text',   width=18),
            ExcelColumn(key='doctor_specialty', label='تخصص جراح',               data_type='text',   width=16),
            ExcelColumn(key='assistant1',       label='کمک اول جراح',            data_type='text',   width=16),
            ExcelColumn(key='assistant2',       label='کمک دوم جراح',            data_type='text',   width=16),
            ExcelColumn(key='anesthesiologist', label='متخصص بیهوشی',            data_type='text',   width=16),
            ExcelColumn(key='anesthesia_tech',  label='تکنسین بیهوشی',           data_type='text',   width=16),
            ExcelColumn(key='scrub',            label='اسکراب',                  data_type='text',   width=14),
            ExcelColumn(key='circulator',       label='سیرکولر',                 data_type='text',   width=14),
            ExcelColumn(key='surgery_type_name', label='نوع عمل',                data_type='text',   width=18),
            ExcelColumn(key='anesthesia_type',  label='نوع بیهوشی',              data_type='text',   width=14),
            ExcelColumn(key='surgery_date',     label='تاریخ عمل',               data_type='date',   width=13),
            ExcelColumn(key='amount',           label='مبلغ عمل (تومان)',        data_type='money',  width=16),
            ExcelColumn(key='status_display',   label='وضعیت عمل',               data_type='text',   width=14),
            ExcelColumn(key='payment_status_display', label='وضعیت پرداخت',      data_type='text',   width=14),
            ExcelColumn(key='center_commission', label='کمیسیون مرکز (تومان)',   data_type='money',  width=16),
            ExcelColumn(key='used_items',       label='اقلام مصرفی',             data_type='text',   width=40, wrap=True),
            ExcelColumn(key='postop_diagnosis', label='تشخیص بعد از عمل',        data_type='text',   width=30, wrap=True),
            ExcelColumn(key='operation_desc',   label='شرح عمل و مشاهدات',       data_type='text',   width=30, wrap=True),
            ExcelColumn(key='description',      label='توضیحات',                 data_type='text',   width=25, wrap=True),
        ]

    @staticmethod
    def _used_items_summary(surgery):
        parts = [
            f'{item.product.name}: {item.quantity} {item.unit}'
            for item in surgery.used_items.all()
        ]
        return '؛ '.join(parts) if parts else ''

    def queryset_to_excel_rows(self, queryset):
        for idx, s in enumerate(queryset, start=1):
            yield {
                'row_number':       idx,
                'medical_record':   s.medical_record_code,
                'patient_name':     s.patient.full_name,
                'case_code':        s.patient.case_code,
                'internal_code':    s.patient.internal_code,
                'patient_age':      s.patient.age,
                'patient_gender':   s.patient.get_gender_display() if s.patient.gender else None,
                'national_id':      s.patient.national_id,
                'phone_number':     s.patient.phone_number,
                'doctor_name':      s.clinical_doctor.full_name if s.clinical_doctor else None,
                'doctor_specialty': s.clinical_doctor.specialty.name if s.clinical_doctor and s.clinical_doctor.specialty_id else None,
                'assistant1':       s.assistant_surgeon.full_name if s.assistant_surgeon else None,
                'assistant2':       s.second_assistant_surgeon.full_name if s.second_assistant_surgeon else None,
                'anesthesiologist': s.anesthesiologist.full_name if s.anesthesiologist else None,
                'anesthesia_tech':  s.anesthesia_technician.full_name if s.anesthesia_technician else None,
                'scrub':            s.scrub_employee.full_name if s.scrub_employee else None,
                'circulator':       s.circulator_employee.full_name if s.circulator_employee else None,
                'surgery_type_name': s.surgery_type.name,
                'anesthesia_type':  s.anesthesia_type.name if s.anesthesia_type else None,
                'surgery_date':     s.surgery_date,
                'amount':           s.amount,
                'status_display':   s.get_status_display(),
                'payment_status_display': s.get_payment_status_display(),
                'center_commission': SurgeryFinanceService.calculate_center_commission(s),
                'used_items':       self._used_items_summary(s),
                'postop_diagnosis': s.postoperative_diagnosis,
                'operation_desc':   s.operation_description,
                'description':      s.description,
            }

    @staticmethod
    def _used_item_detail_columns():
        return [
            ExcelColumn(key='medical_record', label='کد عمل',          data_type='text',   width=16),
            ExcelColumn(key='patient_name',   label='بیمار',           data_type='text',   width=20),
            ExcelColumn(key='product_name',   label='محصول',           data_type='text',   width=22),
            ExcelColumn(key='product_type',   label='نوع محصول',        data_type='text',   width=12),
            ExcelColumn(key='quantity',       label='مقدار',           data_type='number', width=10),
            ExcelColumn(key='unit',           label='واحد',            data_type='text',   width=10),
            ExcelColumn(key='cost',           label='هزینه ثبت‌شده (تومان)', data_type='money', width=18),
        ]

    @staticmethod
    def _used_item_detail_rows(surgeries):
        for s in surgeries:
            for item in s.used_items.all():
                product = item.product
                yield {
                    'medical_record': s.medical_record_code,
                    'patient_name':   s.patient.full_name,
                    'product_name':   product.name,
                    'product_type':   product.get_product_type_display(),
                    'quantity':       item.quantity,
                    'unit':           item.unit,
                    'cost':           (item.quantity * product.purchase_price) if product.purchase_price else Decimal('0'),
                }

    def get_excel_summary(self, request, surgeries):
        total        = len(surgeries)
        total_amount = sum((s.amount for s in surgeries), Decimal('0'))
        total_commission = sum(
            (SurgeryFinanceService.calculate_center_commission(s) for s in surgeries), Decimal('0'),
        )
        completed = sum(1 for s in surgeries if s.status == SurgeryStatus.COMPLETED)
        planned   = sum(1 for s in surgeries if s.status == SurgeryStatus.PLANNED)
        paid      = sum(1 for s in surgeries if s.payment_status == PaymentStatus.PAID)
        pending   = sum(1 for s in surgeries if s.payment_status == PaymentStatus.PENDING)
        return [
            ('تعداد کل عمل‌ها',              total),
            ('مجموع مبلغ عمل‌ها',            total_amount),
            ('مجموع کمیسیون مرکز',           total_commission),
            ('تعداد عمل‌های انجام‌شده',       completed),
            ('تعداد عمل‌های برنامه‌ریزی‌شده', planned),
            ('تعداد پرداخت‌شده',              paid),
            ('تعداد در انتظار پرداخت',        pending),
        ]

    def _handle_excel_export(self, request):
        """Override the single-sheet default: build the same filtered/
        ordered queryset the mixin would, then materialize it once so both
        the per-surgery sheet and the per-item detail sheet (and the
        summary, which needs the same data) share one query pass instead of
        three."""
        qs = self.filter_queryset(self.get_export_queryset())
        count = qs.count()
        if count > EXCEL_MAX_ROWS:
            return Response(
                {
                    'detail': (
                        f'تعداد نتایج ({count:,}) بیشتر از حد مجاز ({EXCEL_MAX_ROWS:,}) است. '
                        'لطفاً فیلترها را محدودتر کنید.'
                    ),
                    'count': count,
                    'max':   EXCEL_MAX_ROWS,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        surgeries = list(qs)

        main_sheet = ExcelSheet(
            name=self.excel_sheet_title,
            columns=self.get_excel_columns(request),
            rows=list(self.queryset_to_excel_rows(surgeries)),
            summary=self.get_excel_summary(request, surgeries),
        )
        items_sheet = ExcelSheet(
            name='اقلام مصرفی',
            columns=self._used_item_detail_columns(),
            rows=list(self._used_item_detail_rows(surgeries)),
            empty_message='برای عمل‌های این گزارش هیچ قلم مصرفی ثبت نشده است.',
        )
        content = build_workbook(
            [main_sheet, items_sheet],
            report_title=self.get_excel_report_title(request),
            meta_rows=self.get_excel_meta_rows(request),
            generated_by=get_display_name(request.user),
        )
        return excel_file_response(content, filename=self.get_excel_filename())


class SurgeryUsedItemViewSet(viewsets.ModelViewSet):
    """
    GET/POST             /api/v1/surgeries/used-items/
    GET/PUT/PATCH/DELETE /api/v1/surgeries/used-items/{id}/

    Filter: surgery, product
    Ordering: created_at

    POST creates the item and an immediate OUT StockMovement.
    PUT/PATCH changing product and/or quantity creates a compensating
    movement for the difference (or a full reverse+re-consume pair if the
    product itself changed) via SurgeryInventoryService.adjust_consumption.
    DELETE creates a compensating IN/RETURN movement that restores the
    item's current quantity before removing the row.
    All three go through SurgeryInventoryService — the only place stock is
    ever mutated for this model.
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ['surgery', 'product']
    ordering_fields    = ['created_at']
    ordering           = ['surgery', 'product__name']
    serializer_class   = SurgeryUsedItemSerializer

    def get_queryset(self):
        return SurgeryUsedItem.objects.select_related(
            'surgery__patient', 'surgery__surgery_type', 'product',
        )

    @transaction.atomic
    def perform_create(self, serializer):
        """Save item and immediately apply OUT stock movement atomically.

        Both the item INSERT and the StockMovement INSERT (+ stock delta) are
        wrapped in a single savepoint.  If stock is insufficient, Django
        ValidationError propagates, the savepoint is rolled back, and DRF
        returns HTTP 400 — the item is never persisted.
        """
        used_item = serializer.save()
        try:
            SurgeryInventoryService.consume_product(used_item)
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)

    @transaction.atomic
    def perform_update(self, serializer):
        """Capture the pre-update (product, quantity) from the database,
        save the new values, then reconcile stock for exactly the
        difference. If reconciliation fails (insufficient stock), the whole
        savepoint — including the field update above — rolls back, so the
        row keeps its previous product/quantity.

        Retrying the identical PATCH twice is a no-op the second time: by
        then the stored quantity/product already equal the "new" values, so
        adjust_consumption computes a zero diff and creates no movement.
        """
        instance       = serializer.instance
        old_product_id = instance.product_id
        old_quantity   = instance.quantity

        used_item = serializer.save()
        try:
            SurgeryInventoryService.adjust_consumption(used_item, old_product_id, old_quantity)
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)

    @transaction.atomic
    def perform_destroy(self, instance):
        """Restore the item's current quantity via a compensating IN/RETURN
        movement, then remove the row. If the reversal fails (should not
        happen — IN movements never go negative), the delete never happens
        either, since both run in one savepoint.

        Naturally idempotent: once this succeeds the row is gone, so a
        retried DELETE for the same id gets 404 from get_object() and never
        reaches this method again.
        """
        SurgeryInventoryService.reverse_consumption(instance)
        instance.delete()


# ---------------------------------------------------------------------------
# Surgery Profit Report (CLI-53)
# ---------------------------------------------------------------------------

class SurgeryProfitReportView(APIView):
    """Per-surgery (or grouped) profitability report.

    GET /api/v1/surgeries/reports/profit/

    Query parameters (all optional):
        start_date         YYYY-MM-DD
        end_date           YYYY-MM-DD
        surgery_type_id    integer PK
        doctor_id          integer PK
        patient_id         integer PK
        status             SurgeryStatus value
        payment_status     PaymentStatus value
        group_by           surgery (default) | surgery_type | doctor
        min_profit         decimal — post-filter on approximate_profit
        max_profit         decimal — post-filter on approximate_profit
        page               integer, default 1
        page_size          integer, 1-100, default 50

    Center income: CenterCommissionIncome.amount where status=CONFIRMED.
    Consumed items cost: sum(SurgeryUsedItem.quantity × product.purchase_price).
    Employee commission cost: sum(CommissionTransaction.amount) per surgery.
    Approximate profit: center_income − consumed_items_cost − employee_commission_cost.

    Access: admin or finance_user roles only.
    """

    permission_classes = [IsAdminOrFinanceUser]
    _VALID_GROUP_BY    = frozenset({'surgery', 'surgery_type', 'doctor'})

    # ── ORM expression ───────────────────────────────────────────────────────

    @staticmethod
    def _item_cost_expr():
        return ExpressionWrapper(
            F('quantity') * F('product__purchase_price'),
            output_field=DBDecimalField(max_digits=20, decimal_places=2),
        )

    # ── Batch aggregation helpers (all accept a surgery queryset) ────────────

    @staticmethod
    def _center_income_map(surgery_qs):
        """Return {surgery_id: income_amount} for CONFIRMED incomes only."""
        return {
            row['surgery_id']: row['amount']
            for row in CenterCommissionIncome.objects.filter(
                surgery__in=surgery_qs, status=IncomeStatus.CONFIRMED,
            ).values('surgery_id', 'amount')
        }

    @classmethod
    def _item_cost_map(cls, surgery_qs):
        """Return {surgery_id: total_item_cost} using product.purchase_price."""
        return {
            row['surgery_id']: (row['total'] or Decimal('0'))
            for row in SurgeryUsedItem.objects.filter(surgery__in=surgery_qs)
            .values('surgery_id')
            .annotate(total=Sum(cls._item_cost_expr()))
        }

    @staticmethod
    def _commission_map(surgery_qs):
        """Return {surgery_id: total_commission_amount}."""
        return {
            row['surgery_id']: (row['total'] or Decimal('0'))
            for row in CommissionTransaction.objects.filter(surgery__in=surgery_qs)
            .values('surgery_id')
            .annotate(total=Sum('amount'))
        }

    @staticmethod
    def _profit_margin(profit, income):
        """Return profit/income × 100, or None when income is zero."""
        if income and income != Decimal('0'):
            return (profit / income * Decimal('100')).quantize(Decimal('0.01'))
        return None

    @staticmethod
    def _page_url(request, params, p, page_size):
        p_copy = dict(params)
        p_copy['page']      = str(p)
        p_copy['page_size'] = str(page_size)
        return (
            request.build_absolute_uri(request.path)
            + '?' + '&'.join(f'{k}={v}' for k, v in p_copy.items())
        )

    # ── Main entry point ─────────────────────────────────────────────────────

    def get(self, request):
        params = request.query_params

        start_date_str        = params.get('start_date')
        end_date_str          = params.get('end_date')
        surgery_type_id_str   = params.get('surgery_type_id')
        doctor_id_str         = params.get('doctor_id')
        patient_id_str        = params.get('patient_id')
        status_filter         = params.get('status', '').strip().upper() or None
        payment_status_filter = params.get('payment_status', '').strip().upper() or None
        group_by              = params.get('group_by', 'surgery').strip().lower()
        min_profit_str        = params.get('min_profit')
        max_profit_str        = params.get('max_profit')

        # Validate group_by
        if group_by not in self._VALID_GROUP_BY:
            return Response(
                {'detail': 'group_by نامعتبر است. مقادیر مجاز: doctor, surgery, surgery_type'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse dates
        date_start = date_end = None
        try:
            if start_date_str:
                date_start = parse_jalali_date(start_date_str)   # Jalali or ISO
            if end_date_str:
                date_end = parse_jalali_date(end_date_str)        # Jalali or ISO
        except ValueError:
            return Response(
                {'detail': 'فرمت تاریخ نامعتبر است. نمونه: ۱۴۰۵/۰۴/۰۳'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date_start and date_end and date_start > date_end:
            return Response(
                {'detail': 'تاریخ شروع باید قبل از تاریخ پایان باشد.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse integer IDs
        surgery_type_id = doctor_id = patient_id = None
        try:
            if surgery_type_id_str:
                surgery_type_id = int(surgery_type_id_str)
            if doctor_id_str:
                doctor_id = int(doctor_id_str)
            if patient_id_str:
                patient_id = int(patient_id_str)
        except (ValueError, TypeError):
            return Response(
                {'detail': 'شناسه نامعتبر است.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate FK existence
        if surgery_type_id and not SurgeryType.objects.filter(pk=surgery_type_id).exists():
            return Response(
                {'detail': f'نوع عمل با شناسه {surgery_type_id} یافت نشد.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if patient_id and not Patient.objects.visible_to(request.user).filter(pk=patient_id).exists():
            return Response(
                {'detail': f'بیمار با شناسه {patient_id} یافت نشد.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if doctor_id:
            from employees.models import Employee as EmployeeModel
            if not EmployeeModel.objects.filter(pk=doctor_id).exists():
                return Response(
                    {'detail': f'دکتر/درمانگر با شناسه {doctor_id} یافت نشد.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Parse min/max profit
        min_profit = max_profit = None
        try:
            if min_profit_str:
                min_profit = Decimal(min_profit_str)
            if max_profit_str:
                max_profit = Decimal(max_profit_str)
        except Exception:
            return Response(
                {'detail': 'مقادیر min_profit و max_profit باید عدد معتبر باشند.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate status/payment_status
        valid_statuses         = {c[0] for c in SurgeryStatus.choices}
        valid_payment_statuses = {c[0] for c in PaymentStatus.choices}
        if status_filter and status_filter not in valid_statuses:
            return Response(
                {'detail': f'وضعیت نامعتبر است. مقادیر مجاز: {", ".join(sorted(valid_statuses))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if payment_status_filter and payment_status_filter not in valid_payment_statuses:
            return Response(
                {'detail': f'وضعیت پرداخت نامعتبر است. مقادیر مجاز: {", ".join(sorted(valid_payment_statuses))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Pagination params
        try:
            page      = max(1, int(params.get('page', 1)))
            page_size = min(max(1, int(params.get('page_size', 50))), 100)
        except (ValueError, TypeError):
            page, page_size = 1, 50

        # Build base surgery queryset
        # IsAdminOrFinanceUser (admin/finance_user group) is not the same
        # as the main administrator (is_superuser) — a hidden Patient's
        # surgeries must stay excluded from this report for group members
        # too, same rule as everywhere else.
        surgery_qs = SurgeryHistory.objects.visible_to(request.user)
        if date_start:
            surgery_qs = surgery_qs.filter(surgery_date__date__gte=date_start)
        if date_end:
            surgery_qs = surgery_qs.filter(surgery_date__date__lte=date_end)
        if surgery_type_id:
            surgery_qs = surgery_qs.filter(surgery_type_id=surgery_type_id)
        if doctor_id:
            surgery_qs = surgery_qs.filter(doctor_or_therapist_id=doctor_id)
        if patient_id:
            surgery_qs = surgery_qs.filter(patient_id=patient_id)
        if status_filter:
            surgery_qs = surgery_qs.filter(status=status_filter)
        if payment_status_filter:
            surgery_qs = surgery_qs.filter(payment_status=payment_status_filter)

        filter_ctx = dict(
            start_date=date_start, end_date=date_end, group_by=group_by,
            surgery_type_id=surgery_type_id, doctor_id=doctor_id,
            patient_id=patient_id, status=status_filter,
            payment_status=payment_status_filter,
        )

        if params.get('export') == 'excel':
            return self._excel_export(request, surgery_qs, group_by, min_profit, max_profit, filter_ctx)

        if group_by == 'surgery':
            return self._by_surgery(
                request, surgery_qs, page, page_size, filter_ctx, min_profit, max_profit,
            )
        if group_by == 'surgery_type':
            return self._by_group(
                request, surgery_qs, page, page_size, filter_ctx,
                min_profit, max_profit, group_key='surgery_type',
            )
        return self._by_group(
            request, surgery_qs, page, page_size, filter_ctx,
            min_profit, max_profit, group_key='doctor',
        )

    # ── group_by=surgery ─────────────────────────────────────────────────────

    def _by_surgery(self, request, surgery_qs, page, page_size, filter_ctx, min_profit, max_profit):
        Z = Decimal('0')

        # Load all matching surgeries (with display fields) in one query
        all_surgeries = list(
            surgery_qs
            .select_related('patient', 'surgery_type', 'doctor_or_therapist')
            .order_by()
        )
        if not all_surgeries:
            return self._empty_response(filter_ctx)

        # Batch-fetch financial aggregates — all via subquery on surgery_qs
        income_map     = self._center_income_map(surgery_qs)
        cost_map       = self._item_cost_map(surgery_qs)
        commission_map = self._commission_map(surgery_qs)

        # Per-surgery item counts
        items_count_map = {
            row['surgery_id']: row['cnt']
            for row in SurgeryUsedItem.objects.filter(surgery__in=surgery_qs)
            .values('surgery_id').annotate(cnt=Count('id'))
        }
        commission_count_map = {
            row['surgery_id']: row['cnt']
            for row in CommissionTransaction.objects.filter(surgery__in=surgery_qs)
            .values('surgery_id').annotate(cnt=Count('id'))
        }

        # Missing-cost flag per surgery (purchase_price = 0)
        missing_cost_ids = set(
            SurgeryUsedItem.objects.filter(surgery__in=surgery_qs, product__purchase_price=0)
            .values_list('surgery_id', flat=True).distinct()
        )

        # Grand missing-cost item count (before profit filter)
        missing_cost_items_count = SurgeryUsedItem.objects.filter(
            surgery__in=surgery_qs, product__purchase_price=0,
        ).count()

        # Compute per-surgery profits in Python
        per_surgery = []
        for s in all_surgeries:
            income     = income_map.get(s.id, Z) or Z
            cost       = cost_map.get(s.id, Z) or Z
            commission = commission_map.get(s.id, Z) or Z
            profit     = income - cost - commission
            per_surgery.append({
                'obj':        s,
                'income':     income,
                'cost':       cost,
                'commission': commission,
                'profit':     profit,
                'has_missing': s.id in missing_cost_ids,
                'items_count': items_count_map.get(s.id, 0),
                'comm_count':  commission_count_map.get(s.id, 0),
            })

        # Apply profit range filter
        if min_profit is not None:
            per_surgery = [d for d in per_surgery if d['profit'] >= min_profit]
        if max_profit is not None:
            per_surgery = [d for d in per_surgery if d['profit'] <= max_profit]

        # Sort by approximate_profit DESC
        per_surgery.sort(key=lambda d: d['profit'], reverse=True)

        # Grand totals over the final filtered+sorted set
        total_count       = len(per_surgery)
        grand_income      = sum(d['income']     for d in per_surgery)
        grand_cost        = sum(d['cost']        for d in per_surgery)
        grand_commission  = sum(d['commission']  for d in per_surgery)
        grand_profit      = sum(d['profit']      for d in per_surgery)
        profitable_count  = sum(1 for d in per_surgery if d['profit'] > Z)
        loss_count        = sum(1 for d in per_surgery if d['profit'] < Z)

        metadata = {
            **filter_ctx,
            'total_surgeries':               total_count,
            'total_center_income':           grand_income,
            'total_consumed_items_cost':     grand_cost,
            'total_employee_commission_cost': grand_commission,
            'total_approximate_profit':      grand_profit,
            'average_profit_per_surgery':    (
                (grand_profit / total_count).quantize(Decimal('0.01'))
                if total_count else None
            ),
            'profitable_surgeries_count':    profitable_count,
            'loss_surgeries_count':          loss_count,
            'missing_cost_items_count':      missing_cost_items_count,
        }

        # Paginate
        offset    = (page - 1) * page_size
        page_data = per_surgery[offset:offset + page_size]

        results = []
        for d in page_data:
            s = d['obj']
            results.append({
                'surgery_id':                  s.id,
                'patient_name':                s.patient.full_name,
                'case_code':                   s.case_code,
                'phone_number':                s.phone_number,
                'doctor_name':                 (
                    s.doctor_or_therapist.full_name if s.doctor_or_therapist else None
                ),
                'surgery_type_name':           s.surgery_type.name,
                'surgery_date':                s.surgery_date,
                'surgery_amount':              s.amount,
                'payment_status':              s.payment_status,
                'surgery_status':              s.status,
                'center_income':               d['income'],
                'consumed_items_cost':         d['cost'],
                'employee_commission_cost':    d['commission'],
                'approximate_profit':          d['profit'],
                'profit_margin_percent':       self._profit_margin(d['profit'], d['income']),
                'used_items_count':            d['items_count'],
                'commission_transactions_count': d['comm_count'],
                'has_missing_cost_data':       d['has_missing'],
            })

        next_url = (
            self._page_url(request, request.query_params, page + 1, page_size)
            if offset + page_size < total_count else None
        )
        prev_url = (
            self._page_url(request, request.query_params, page - 1, page_size)
            if page > 1 else None
        )

        return Response({
            'metadata': SurgeryProfitReportSummarySerializer(metadata).data,
            'count':    total_count,
            'next':     next_url,
            'previous': prev_url,
            'results':  SurgeryProfitReportRowSerializer(results, many=True).data,
        })

    # ── group_by=surgery_type or group_by=doctor ─────────────────────────────

    def _by_group(
        self, request, surgery_qs, page, page_size,
        filter_ctx, min_profit, max_profit, *, group_key,
    ):
        Z = Decimal('0')

        if group_key == 'surgery_type':
            grp_id_field   = 'surgery_type_id'
            grp_name_field = 'surgery_type__name'
            grp_filt_id    = 'surgery__surgery_type_id'
            qs = surgery_qs
        else:  # doctor
            grp_id_field   = 'doctor_or_therapist_id'
            grp_name_field = 'doctor_or_therapist__full_name'
            grp_filt_id    = 'surgery__doctor_or_therapist_id'
            # Exclude surgeries with no doctor assigned
            qs = surgery_qs.filter(doctor_or_therapist__isnull=False)

        # Surgery count + name per group
        group_meta = {
            row[grp_id_field]: {
                'id':    row[grp_id_field],
                'name':  row[grp_name_field],
                'count': row['cnt'],
            }
            for row in qs
            .values(grp_id_field, grp_name_field)
            .annotate(cnt=Count('id'))
        }

        if not group_meta:
            return self._empty_response(filter_ctx)

        # Financial aggregates per group
        income_by_group = {
            row[grp_filt_id]: (row['total'] or Z)
            for row in CenterCommissionIncome.objects.filter(
                surgery__in=qs, status=IncomeStatus.CONFIRMED,
            ).values(grp_filt_id).annotate(total=Sum('amount'))
        }
        cost_by_group = {
            row[grp_filt_id]: (row['total'] or Z)
            for row in SurgeryUsedItem.objects.filter(surgery__in=qs)
            .values(grp_filt_id)
            .annotate(total=Sum(self._item_cost_expr()))
        }
        commission_by_group = {
            row[grp_filt_id]: (row['total'] or Z)
            for row in CommissionTransaction.objects.filter(surgery__in=qs)
            .values(grp_filt_id)
            .annotate(total=Sum('amount'))
        }

        # Global missing-cost count (items with purchase_price=0)
        missing_cost_items_count = SurgeryUsedItem.objects.filter(
            surgery__in=qs, product__purchase_price=0,
        ).count()

        # Build one row per group
        rows = []
        for gid, gmeta in group_meta.items():
            income     = income_by_group.get(gid, Z)
            cost       = cost_by_group.get(gid, Z)
            commission = commission_by_group.get(gid, Z)
            profit     = income - cost - commission
            cnt        = gmeta['count']
            avg_profit = (profit / cnt).quantize(Decimal('0.01')) if cnt else Z
            row = {
                'surgeries_count':               cnt,
                'total_center_income':           income,
                'total_consumed_items_cost':     cost,
                'total_employee_commission_cost': commission,
                'total_approximate_profit':      profit,
                'average_profit_per_surgery':    avg_profit,
                'average_profit_margin_percent': self._profit_margin(profit, income),
            }
            if group_key == 'surgery_type':
                row['surgery_type_id']   = gid
                row['surgery_type_name'] = gmeta['name']
            else:
                row['doctor_id']   = gid
                row['doctor_name'] = gmeta['name']
            rows.append(row)

        # Apply profit range filter
        if min_profit is not None:
            rows = [r for r in rows if r['total_approximate_profit'] >= min_profit]
        if max_profit is not None:
            rows = [r for r in rows if r['total_approximate_profit'] <= max_profit]

        # Sort by total_approximate_profit DESC
        rows.sort(key=lambda r: r['total_approximate_profit'], reverse=True)

        # Grand totals over final filtered set
        total_count      = len(rows)
        grand_income     = sum(r['total_center_income']            for r in rows)
        grand_cost       = sum(r['total_consumed_items_cost']      for r in rows)
        grand_commission = sum(r['total_employee_commission_cost'] for r in rows)
        grand_profit     = sum(r['total_approximate_profit']       for r in rows)
        grand_surgeries  = sum(r['surgeries_count']                for r in rows)
        profitable_count = sum(1 for r in rows if r['total_approximate_profit'] > Z)
        loss_count       = sum(1 for r in rows if r['total_approximate_profit'] < Z)

        metadata = {
            **filter_ctx,
            'total_surgeries':               grand_surgeries,
            'total_center_income':           grand_income,
            'total_consumed_items_cost':     grand_cost,
            'total_employee_commission_cost': grand_commission,
            'total_approximate_profit':      grand_profit,
            'average_profit_per_surgery':    (
                (grand_profit / grand_surgeries).quantize(Decimal('0.01'))
                if grand_surgeries else None
            ),
            'profitable_surgeries_count':    profitable_count,
            'loss_surgeries_count':          loss_count,
            'missing_cost_items_count':      missing_cost_items_count,
        }

        # Paginate
        offset    = (page - 1) * page_size
        page_rows = rows[offset:offset + page_size]

        next_url = (
            self._page_url(request, request.query_params, page + 1, page_size)
            if offset + page_size < total_count else None
        )
        prev_url = (
            self._page_url(request, request.query_params, page - 1, page_size)
            if page > 1 else None
        )

        return Response({
            'metadata': SurgeryProfitReportSummarySerializer(metadata).data,
            'count':    total_count,
            'next':     next_url,
            'previous': prev_url,
            'results':  SurgeryProfitReportRowSerializer(page_rows, many=True).data,
        })

    # ── Helper: empty response ────────────────────────────────────────────────

    @staticmethod
    def _empty_response(filter_ctx):
        Z = Decimal('0')
        metadata = {
            **filter_ctx,
            'total_surgeries':               0,
            'total_center_income':           Z,
            'total_consumed_items_cost':     Z,
            'total_employee_commission_cost': Z,
            'total_approximate_profit':      Z,
            'average_profit_per_surgery':    None,
            'profitable_surgeries_count':    0,
            'loss_surgeries_count':          0,
            'missing_cost_items_count':      0,
        }
        return Response({
            'metadata': SurgeryProfitReportSummarySerializer(metadata).data,
            'count':    0,
            'next':     None,
            'previous': None,
            'results':  [],
        })

    # ── Excel export ──────────────────────────────────────────────────────────

    def _excel_export(self, request, surgery_qs, group_by, min_profit, max_profit, filter_ctx):
        """Build and return an Excel file for the surgery profit report."""
        # Reuse the full computation from the normal handlers but without pagination.
        # We call the same helpers and collect ALL rows.
        dummy_page      = 1
        dummy_page_size = EXCEL_MAX_ROWS + 1   # large enough to get everything

        if group_by == 'surgery':
            resp = self._by_surgery(
                request, surgery_qs, dummy_page, dummy_page_size,
                filter_ctx, min_profit, max_profit,
            )
        elif group_by == 'surgery_type':
            resp = self._by_group(
                request, surgery_qs, dummy_page, dummy_page_size,
                filter_ctx, min_profit, max_profit, group_key='surgery_type',
            )
        else:
            resp = self._by_group(
                request, surgery_qs, dummy_page, dummy_page_size,
                filter_ctx, min_profit, max_profit, group_key='doctor',
            )

        # If the normal handler returned a non-200 (empty response is 200 with 0 rows),
        # just return it as-is.
        if hasattr(resp, 'status_code') and resp.status_code != 200:
            return resp

        total_count = resp.data.get('count', 0)
        if total_count > EXCEL_MAX_ROWS:
            return Response(
                {'detail': f'تعداد نتایج ({total_count:,}) بیشتر از حد مجاز ({EXCEL_MAX_ROWS:,}) است.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows    = resp.data.get('results', [])
        columns = self._profit_excel_columns(group_by)
        meta_rows = [
            ('از تاریخ',  filter_ctx.get('start_date') or ''),
            ('تا تاریخ',  filter_ctx.get('end_date')   or ''),
            ('گروه‌بندی', group_by),
        ]
        content = build_excel(columns=columns, rows=rows,
                               sheet_title='سودآوری عمل', meta_rows=meta_rows)
        return excel_file_response(content, filename='surgery_profit_report.xlsx')

    @staticmethod
    def _profit_excel_columns(group_by):
        if group_by == 'surgery_type':
            return [
                ('نوع عمل',                 'surgery_type_name'),
                ('تعداد عمل',               'surgeries_count'),
                ('مجموع درآمد مرکز',        'total_center_income'),
                ('مجموع هزینه اقلام',       'total_consumed_items_cost'),
                ('مجموع کمیسیون کارمندان',  'total_employee_commission_cost'),
                ('مجموع سود تقریبی',        'total_approximate_profit'),
                ('میانگین سود هر عمل',      'average_profit_per_surgery'),
            ]
        if group_by == 'doctor':
            return [
                ('پزشک یا درمانگر',         'doctor_name'),
                ('تعداد عمل',               'surgeries_count'),
                ('مجموع درآمد مرکز',        'total_center_income'),
                ('مجموع هزینه اقلام',       'total_consumed_items_cost'),
                ('مجموع کمیسیون کارمندان',  'total_employee_commission_cost'),
                ('مجموع سود تقریبی',        'total_approximate_profit'),
                ('میانگین سود هر عمل',      'average_profit_per_surgery'),
            ]
        # surgery (default)
        return [
            ('بیمار',               'patient_name'),
            ('ردیف',                'case_code'),
            ('پزشک یا درمانگر',    'doctor_name'),
            ('نوع عمل',             'surgery_type_name'),
            ('تاریخ پرداخت',       'surgery_date'),
            ('درآمد مرکز',         'center_income'),
            ('هزینه اقلام مصرفی',  'consumed_items_cost'),
            ('کمیسیون کارمندان',   'employee_commission_cost'),
            ('سود تقریبی',         'approximate_profit'),
            ('درصد سود',           'profit_margin_percent'),
        ]
