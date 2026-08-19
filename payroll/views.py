import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, Sum
from rest_framework import mixins, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsAdminOrFinanceUser
from common.dates import parse_jalali_date
from common.excel import EXCEL_MAX_ROWS, build_excel, excel_file_response
from rest_framework.response import Response

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
    _jalali_days_in_month,
    _jalali_to_gregorian,
)
from .serializers import (
    CommissionRuleListSerializer,
    CommissionRuleSerializer,
    CommissionTransactionSerializer,
    EmployeeCostReportRowSerializer,
    EmployeeCostReportSummarySerializer,
    HourlyRateListSerializer,
    HourlyRateSerializer,
    HourlyWorkEntryListSerializer,
    HourlyWorkEntrySerializer,
    MonthlyWageListSerializer,
    MonthlyWageSerializer,
    PayrollPeriodSerializer,
    PayrollReportSerializer,
    PayrollTypeConfigSerializer,
)


class CommissionRuleViewSet(viewsets.ModelViewSet):
    """
    GET/POST   /api/v1/payroll/commission-rules/
    GET/PATCH  /api/v1/payroll/commission-rules/{id}/
    DELETE     /api/v1/payroll/commission-rules/{id}/ → 405
    GET        /api/v1/payroll/commission-rules/matrix/
    GET        /api/v1/payroll/commission-rules/by_position/?job_position={id}

    Filter: ?job_position={id}  ?surgery_type={id}  ?is_active=true|false
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    filterset_fields   = ['job_position', 'surgery_type', 'is_active']

    def get_serializer_class(self):
        if self.action == 'list':
            return CommissionRuleListSerializer
        return CommissionRuleSerializer

    def get_queryset(self):
        return CommissionRule.objects.select_related(
            'job_position', 'surgery_type', 'created_by',
        )

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminOrFinanceUser()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'حذف مجاز نیست. قانون را غیرفعال کنید.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=False, methods=['get'], url_path='matrix')
    def matrix(self, request):
        rules = CommissionRule.objects.filter(
            is_active=True,
        ).select_related('job_position', 'surgery_type').order_by(
            'job_position__name', 'surgery_type__name',
        )
        positions     = sorted(set(r.job_position.name for r in rules))
        surgery_types = sorted(set(r.surgery_type.name for r in rules))
        matrix        = {pos: {} for pos in positions}
        for rule in rules:
            matrix[rule.job_position.name][rule.surgery_type.name] = float(rule.commission_percent)
        return Response({
            'positions':     positions,
            'surgery_types': surgery_types,
            'matrix':        matrix,
        })

    @action(detail=False, methods=['get'], url_path='by_position')
    def by_position(self, request):
        job_position_id = request.query_params.get('job_position')
        if not job_position_id:
            return Response(
                {'detail': 'پارامتر job_position الزامی است.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = CommissionRule.objects.filter(
            job_position_id=job_position_id,
        ).select_related('job_position', 'surgery_type', 'created_by')
        return Response(CommissionRuleSerializer(qs, many=True).data)


class PayrollPeriodViewSet(viewsets.ModelViewSet):
    """
    GET/POST   /api/v1/payroll/periods/
    GET/PATCH  /api/v1/payroll/periods/{id}/
    POST       /api/v1/payroll/periods/{id}/close/

    Filter: ?status=OPEN|CLOSED|PROCESSED  ?year={year}
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    serializer_class   = PayrollPeriodSerializer
    filterset_fields   = ['status', 'year']

    def get_queryset(self):
        return PayrollPeriod.objects.all()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'close']:
            return [IsAuthenticated(), IsAdminOrFinanceUser()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        period = self.get_object()
        if period.status != PayrollStatus.OPEN:
            return Response(
                {'detail': 'فقط دوره‌های باز را می‌توان بست.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            period.close()
        except DjangoValidationError as e:
            return Response({'detail': str(e.message)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PayrollPeriodSerializer(period).data)


class PayrollTypeConfigViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    GET        /api/v1/payroll/configs/
    GET/PATCH  /api/v1/payroll/configs/{id}/
    GET        /api/v1/payroll/configs/by_employee/?employee={id}

    No create (signal handles it). No delete.
    Filter: ?has_monthly_wage=true|false  ?has_commission=true|false
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    serializer_class   = PayrollTypeConfigSerializer
    filterset_fields   = ['has_monthly_wage', 'has_commission']
    http_method_names  = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return PayrollTypeConfig.objects.select_related('employee')

    def get_permissions(self):
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsAdminOrFinanceUser()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='by_employee')
    def by_employee(self, request):
        employee_id = request.query_params.get('employee')
        if not employee_id:
            return Response(
                {'detail': 'پارامتر employee الزامی است.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            config = PayrollTypeConfig.objects.select_related('employee').get(
                employee_id=employee_id
            )
        except PayrollTypeConfig.DoesNotExist:
            return Response(
                {'detail': 'تنظیمات حقوقی برای این کارمند یافت نشد.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(PayrollTypeConfigSerializer(config).data)


class MonthlyWageViewSet(viewsets.ModelViewSet):
    """
    GET/POST   /api/v1/payroll/wages/
    GET/PATCH  /api/v1/payroll/wages/{id}/
    DELETE     /api/v1/payroll/wages/{id}/ → 405
    GET        /api/v1/payroll/wages/period_summary/?year=&month=

    Filter: ?employee={id}  ?is_active=true|false
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    filterset_fields   = ['employee', 'is_active']

    def get_queryset(self):
        return MonthlyWage.objects.select_related(
            'employee', 'employee__job_position', 'created_by'
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return MonthlyWageListSerializer
        return MonthlyWageSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminOrFinanceUser()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'حذف مجاز نیست. رکورد را غیرفعال کنید.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=False, methods=['get'], url_path='period_summary')
    def period_summary(self, request):
        year_str  = request.query_params.get('year')
        month_str = request.query_params.get('month')
        if not year_str or not month_str:
            return Response(
                {'detail': 'پارامترهای year و month الزامی هستند.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            year  = int(year_str)
            month = int(month_str)
            if not (1 <= month <= 12):
                raise ValueError
        except ValueError:
            return Response(
                {'detail': 'سال و ماه باید اعداد معتبر باشند.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        last_day   = _jalali_days_in_month(year, month)
        first_greg = datetime.date(*_jalali_to_gregorian(year, month, 1))
        last_greg  = datetime.date(*_jalali_to_gregorian(year, month, last_day))

        wages_qs = MonthlyWage.objects.filter(
            is_active=True,
            start_date__lte=last_greg,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=first_greg)
        ).select_related('employee', 'employee__job_position')

        total = wages_qs.aggregate(total=Sum('amount'))['total'] or 0

        return Response({
            'year':           year,
            'month':          month,
            'total_amount':   total,
            'employee_count': wages_qs.count(),
            'wages':          MonthlyWageListSerializer(wages_qs, many=True).data,
        })


class HourlyRateViewSet(viewsets.ModelViewSet):
    """
    GET/POST   /api/v1/payroll/hourly-rates/
    GET/PATCH  /api/v1/payroll/hourly-rates/{id}/
    DELETE     /api/v1/payroll/hourly-rates/{id}/ → 405

    Filter: ?employee={id}  ?is_active=true|false
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    filterset_fields   = ['employee', 'is_active']

    def get_queryset(self):
        return HourlyRate.objects.select_related(
            'employee', 'employee__job_position', 'created_by'
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return HourlyRateListSerializer
        return HourlyRateSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAdminOrFinanceUser()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'حذف مجاز نیست. رکورد را غیرفعال کنید.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class HourlyWorkEntryViewSet(viewsets.ModelViewSet):
    """
    GET/POST   /api/v1/payroll/hourly-work-entries/
    GET/PATCH  /api/v1/payroll/hourly-work-entries/{id}/
    DELETE     /api/v1/payroll/hourly-work-entries/{id}/ (blocked once processed)
    POST       /api/v1/payroll/hourly-work-entries/calculate/
               body: {"employee": <id>, "year": <jalali>, "month": <jalali 1-12>}
               Read-only preview: prices unprocessed entries for that
               employee/period the same way finalization would, but writes
               nothing — no entry is marked processed, no PayrollPeriod row
               is created, no Finance transaction is touched. Safe to call
               repeatedly (page opens, refreshes). Actual finalization only
               happens when the matching PayrollPeriod is closed/processed
               (see finance.services.PayrollFinanceService.sync_salary_expenses),
               never through this endpoint.

    Filter: ?employee={id}  ?work_date_after=  ?work_date_before=  ?payroll_period={id}
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    filterset_fields   = {
        'employee':       ['exact'],
        'work_date':      ['gte', 'lte'],
        'payroll_period': ['exact', 'isnull'],
    }

    def get_queryset(self):
        return HourlyWorkEntry.objects.select_related('employee', 'payroll_period')

    def get_serializer_class(self):
        if self.action == 'list':
            return HourlyWorkEntryListSerializer
        return HourlyWorkEntrySerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'calculate']:
            return [IsAuthenticated(), IsAdminOrFinanceUser()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_processed:
            return Response(
                {'detail': 'این رکورد در محاسبه حقوق پردازش شده و قابل حذف نیست.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request):
        """Pure preview — see the class docstring. Never calls
        finalize_hourly_payroll and never persists a PayrollPeriod."""
        from .services import preview_hourly_payroll

        employee_id = request.data.get('employee')
        year_str    = request.data.get('year')
        month_str   = request.data.get('month')
        if not employee_id or not year_str or not month_str:
            return Response(
                {'detail': 'پارامترهای employee، year و month الزامی هستند.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            year  = int(year_str)
            month = int(month_str)
            if not (1 <= month <= 12):
                raise ValueError
        except ValueError:
            return Response(
                {'detail': 'سال و ماه باید اعداد معتبر باشند.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from employees.models import Employee
        try:
            employee = Employee.objects.get(pk=employee_id)
        except (Employee.DoesNotExist, ValueError, TypeError):
            return Response(
                {'detail': 'کارمند یافت نشد.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        period = PayrollPeriod(year=year, month=month)

        try:
            result = preview_hourly_payroll(employee, period)
        except DjangoValidationError as e:
            return Response({'detail': str(e.message) if hasattr(e, 'message') else str(e)},
                             status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'employee':     employee.pk,
            'year':         year,
            'month':        month,
            'total_hours':  result['total_hours'],
            'total_amount': result['total_amount'],
            'entries':      result['entries'],
        })


class CommissionTransactionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    GET  /api/v1/payroll/commission-transactions/
    GET  /api/v1/payroll/commission-transactions/{id}/

    Read-only — created automatically by the commission service.
    Filter: employee, surgery, commission_rule
    Ordering: created_at, amount
    """

    permission_classes = [IsAuthenticated]
    serializer_class   = CommissionTransactionSerializer
    filterset_fields   = ['employee', 'surgery', 'commission_rule']
    ordering_fields    = ['created_at', 'amount']
    ordering           = ['-created_at']

    def get_queryset(self):
        return CommissionTransaction.objects.select_related(
            'surgery__patient',
            'employee__job_position',
            'commission_rule__surgery_type',
        )


class PayrollReportView(views.APIView):
    """Aggregate payroll report API.

    GET /api/v1/payroll/report/

    Query parameters (all optional):
      start_date   YYYY-MM-DD
      end_date     YYYY-MM-DD
      employee     employee pk
      position     job_position pk
      month        1-12 (Jalali — combined with year)
      year         Jalali year (required when month is provided)
      wage_type    "fixed" | "commission" | "both" (default "both")

    Returns:
      total_fixed_salary, total_commission, total_labor_cost,
      employee_count, per-employee breakdown.
    """

    permission_classes = [IsAdminOrFinanceUser]

    def get(self, request):
        params     = request.query_params
        start_date = params.get('start_date')
        end_date   = params.get('end_date')
        employee_id = params.get('employee')
        position_id = params.get('position')
        month_str   = params.get('month')
        year_str    = params.get('year')
        wage_type   = params.get('wage_type', 'both')

        # ── Date range from Jalali month/year ────────────────────────────
        if month_str and year_str:
            try:
                year  = int(year_str)
                month = int(month_str)
                if not (1 <= month <= 12):
                    raise ValueError
            except ValueError:
                return Response(
                    {'detail': 'year و month باید اعداد معتبر جلالی باشند.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            last_day   = _jalali_days_in_month(year, month)
            first_greg = datetime.date(*_jalali_to_gregorian(year, month, 1))
            last_greg  = datetime.date(*_jalali_to_gregorian(year, month, last_day))
            start_date = start_date or first_greg.isoformat()
            end_date   = end_date   or last_greg.isoformat()

        # ── Parse ISO dates ───────────────────────────────────────────────
        date_start = None
        date_end   = None
        try:
            if start_date:
                date_start = parse_jalali_date(start_date)   # Jalali or ISO
            if end_date:
                date_end = parse_jalali_date(end_date)        # Jalali or ISO
        except ValueError:
            return Response(
                {'detail': 'فرمت تاریخ نامعتبر است. نمونه: ۱۴۰۵/۰۴/۰۳'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Fixed wages aggregate ─────────────────────────────────────────
        wage_qs = MonthlyWage.objects.filter(is_active=True)
        if date_start:
            wage_qs = wage_qs.filter(
                Q(end_date__isnull=True) | Q(end_date__gte=date_start)
            )
        if date_end:
            wage_qs = wage_qs.filter(start_date__lte=date_end)
        if employee_id:
            wage_qs = wage_qs.filter(employee_id=employee_id)
        if position_id:
            wage_qs = wage_qs.filter(employee__job_position_id=position_id)

        # ── Commission transactions aggregate ─────────────────────────────
        ct_qs = CommissionTransaction.objects.all()
        if date_start:
            ct_qs = ct_qs.filter(created_at__date__gte=date_start)
        if date_end:
            ct_qs = ct_qs.filter(created_at__date__lte=date_end)
        if employee_id:
            ct_qs = ct_qs.filter(employee_id=employee_id)
        if position_id:
            ct_qs = ct_qs.filter(employee__job_position_id=position_id)

        # ── Per-employee breakdown ────────────────────────────────────────
        from employees.models import Employee
        emp_qs = Employee.objects.filter(is_active=True).select_related('job_position')
        if employee_id:
            emp_qs = emp_qs.filter(pk=employee_id)
        if position_id:
            emp_qs = emp_qs.filter(job_position_id=position_id)

        wage_totals = {
            row['employee_id']: row['total']
            for row in wage_qs.values('employee_id').annotate(total=Sum('amount'))
        }
        commission_totals = {
            row['employee_id']: row['total']
            for row in ct_qs.values('employee_id').annotate(total=Sum('amount'))
        }

        # Purchase-based employee commission totals
        from employees.models import EmployeePurchaseCommission
        epc_qs = EmployeePurchaseCommission.objects.all()
        if date_start:
            epc_qs = epc_qs.filter(commission_date__gte=date_start)
        if date_end:
            epc_qs = epc_qs.filter(commission_date__lte=date_end)
        if employee_id:
            epc_qs = epc_qs.filter(employee_id=employee_id)
        if position_id:
            epc_qs = epc_qs.filter(employee__job_position_id=position_id)
        purchase_commission_totals = {
            row['employee_id']: row['total']
            for row in epc_qs.values('employee_id').annotate(total=Sum('amount'))
        }

        # Hourly work records aggregate (legacy) — amount AND hours, so a
        # legacy-only employee's effective hourly figures are complete, not
        # just the salary half of the pair.
        hw_qs = HourlyWorkRecord.objects.all()
        if date_start:
            hw_qs = hw_qs.filter(record_date__gte=date_start)
        if date_end:
            hw_qs = hw_qs.filter(record_date__lte=date_end)
        if employee_id:
            hw_qs = hw_qs.filter(employee_id=employee_id)
        if position_id:
            hw_qs = hw_qs.filter(employee__job_position_id=position_id)
        hourly_totals = {
            row['employee_id']: row['total']
            for row in hw_qs.values('employee_id').annotate(total=Sum('calculated_salary'))
        }
        hourly_record_hours_totals = {
            row['employee_id']: row['total']
            for row in hw_qs.values('employee_id').annotate(total=Sum('hours_worked'))
        }

        # New hourly payroll (HourlyWorkEntry) — finalized entries (amount
        # set at finalization time) read their stored snapshot, exactly as
        # before: never recalculated from the latest HourlyRate.
        hwe_qs = HourlyWorkEntry.objects.filter(amount__isnull=False)
        if date_start:
            hwe_qs = hwe_qs.filter(work_date__gte=date_start)
        if date_end:
            hwe_qs = hwe_qs.filter(work_date__lte=date_end)
        if employee_id:
            hwe_qs = hwe_qs.filter(employee_id=employee_id)
        if position_id:
            hwe_qs = hwe_qs.filter(employee__job_position_id=position_id)
        hourly_entry_totals = {
            row['employee_id']: row['total']
            for row in hwe_qs.values('employee_id').annotate(total=Sum('amount'))
        }
        hourly_hours_totals = {
            row['employee_id']: row['total']
            for row in hwe_qs.values('employee_id').annotate(total=Sum('hours_worked'))
        }

        # Pending (unprocessed) HourlyWorkEntry rows in the same window —
        # amount/rate_used/payroll_period are still null by design until
        # finalization, so they never appear in hwe_qs above. Report them
        # via a read-only preview (never writes rate_used/amount/
        # payroll_period, never touches Finance) so newly recorded work
        # shows up before the payroll period is closed. `amount__isnull=False`
        # and `payroll_period__isnull=True` are mutually exclusive by
        # construction (finalize_hourly_payroll sets both together in the
        # same save), so this can never double-count an hwe_qs row above.
        # With no explicit end_date (an unbounded "all periods" report),
        # cap the window at today so a mis-dated future work entry can
        # never appear as already-earned hourly salary.
        pending_qs = HourlyWorkEntry.objects.filter(payroll_period__isnull=True)
        if date_start:
            pending_qs = pending_qs.filter(work_date__gte=date_start)
        pending_qs = pending_qs.filter(work_date__lte=date_end or datetime.date.today())
        if employee_id:
            pending_qs = pending_qs.filter(employee_id=employee_id)
        if position_id:
            pending_qs = pending_qs.filter(employee__job_position_id=position_id)

        from .services import preview_pending_hourly_totals
        pending_hourly_totals = preview_pending_hourly_totals(pending_qs)
        for emp_id, bucket in pending_hourly_totals.items():
            hourly_entry_totals[emp_id] = hourly_entry_totals.get(emp_id, Decimal('0')) + bucket['salary']
            hourly_hours_totals[emp_id] = hourly_hours_totals.get(emp_id, Decimal('0')) + bucket['hours']

        # ── Configured-but-possibly-zero employees ─────────────────────────
        def _config_eligible_ids(flag_name, related_name):
            qs = Employee.objects.filter(is_active=True, **{f'payroll_config__{flag_name}': True})
            if employee_id:
                qs = qs.filter(pk=employee_id)
            if position_id:
                qs = qs.filter(job_position_id=position_id)
            cond = Q(**{f'{related_name}__is_active': True})
            if date_start:
                cond &= (
                    Q(**{f'{related_name}__end_date__isnull': True})
                    | Q(**{f'{related_name}__end_date__gte': date_start})
                )
            if date_end:
                cond &= Q(**{f'{related_name}__start_date__lte': date_end})
            if date_start or date_end:
                qs = qs.filter(cond)
            return set(qs.values_list('pk', flat=True))

        monthly_config_eligible_ids = _config_eligible_ids('has_monthly_wage', 'monthly_wages')
        hourly_config_eligible_ids = _config_eligible_ids('has_hourly_wage', 'hourly_rates')
        commission_qs = Employee.objects.filter(is_active=True, payroll_config__has_commission=True)
        if employee_id:
            commission_qs = commission_qs.filter(pk=employee_id)
        if position_id:
            commission_qs = commission_qs.filter(job_position_id=position_id)
        commission_config_eligible_ids = set(commission_qs.values_list('pk', flat=True))

        relevant_ids = (
            set(wage_totals) | set(commission_totals)
            | set(hourly_totals) | set(purchase_commission_totals)
            | set(hourly_entry_totals)
            | monthly_config_eligible_ids
            | commission_config_eligible_ids
            | hourly_config_eligible_ids
        )
        if wage_type == 'fixed':
            relevant_ids = set(wage_totals) | set(hourly_totals) | monthly_config_eligible_ids
        elif wage_type == 'commission':
            relevant_ids = (
                set(commission_totals) | set(purchase_commission_totals)
                | commission_config_eligible_ids
            )
        elif wage_type == 'hourly':
            relevant_ids = set(hourly_entry_totals) | set(hourly_totals) | hourly_config_eligible_ids

        employee_rows = []
        for emp in emp_qs.filter(pk__in=relevant_ids):
            fixed         = wage_totals.get(emp.pk, Decimal('0'))
            surgery_comm  = commission_totals.get(emp.pk, Decimal('0'))
            purchase_comm = purchase_commission_totals.get(emp.pk, Decimal('0'))

            if emp.pk in hourly_entry_totals:
                hourly_salary = hourly_entry_totals[emp.pk]
                total_hours   = hourly_hours_totals.get(emp.pk, Decimal('0'))
            else:
                hourly_salary = hourly_totals.get(emp.pk, Decimal('0'))
                total_hours   = hourly_record_hours_totals.get(emp.pk, Decimal('0'))

            if wage_type == 'fixed':
                surgery_comm  = Decimal('0')
                purchase_comm = Decimal('0')
                hourly_salary = Decimal('0')
                total_hours   = Decimal('0')
            elif wage_type == 'commission':
                fixed         = Decimal('0')
                hourly_salary = Decimal('0')
                total_hours   = Decimal('0')
            elif wage_type == 'hourly':
                fixed         = Decimal('0')
                surgery_comm  = Decimal('0')
                purchase_comm = Decimal('0')
            total_comm = surgery_comm + purchase_comm
            employee_rows.append({
                'employee_id':         emp.pk,
                'employee_name':       emp.full_name,
                'job_position':        emp.job_position.name,
                'fixed_salary':        fixed,
                'surgery_commission':  surgery_comm,
                'purchase_commission': purchase_comm,
                'total_commission':    total_comm,
                'has_commission':      bool(surgery_comm or purchase_comm),
                'hourly_salary':       hourly_salary,
                'total_hours_worked':  total_hours,
                'total_payment':       fixed + total_comm + hourly_salary,
            })

        total_fixed      = sum(r['fixed_salary']        for r in employee_rows) or Decimal('0')
        total_commission = sum(r['total_commission']    for r in employee_rows) or Decimal('0')
        total_hourly     = sum(r['hourly_salary']       for r in employee_rows) or Decimal('0')
        total_hours      = sum(r['total_hours_worked']  for r in employee_rows) or Decimal('0')

        data = {
            'start_date':          start_date,
            'end_date':            end_date,
            'total_fixed_salary':  total_fixed,
            'total_commission':    total_commission,
            'total_hourly_salary': total_hourly,
            'total_hours_worked':  total_hours,
            'total_labor_cost':    total_fixed + total_commission + total_hourly,
            'employee_count':      len(employee_rows),
            'employees':           employee_rows,
        }
        return Response(PayrollReportSerializer(data).data)


# ---------------------------------------------------------------------------
# Employee Cost Report (CLI-52)
# ---------------------------------------------------------------------------

class EmployeeCostReportView(views.APIView):
    """Per-employee payroll cost report.

    GET /api/v1/payroll/reports/employee-cost/

    Query parameters (all optional):
        start_date    YYYY-MM-DD
        end_date      YYYY-MM-DD
        employee_id   employee PK
        position_id   job_position PK
        wage_type     'monthly' | 'commission' | 'all' (default 'all')
        page          page number (default 1)
        page_size     items per page, 1-100 (default 50)

    Commissions are dated by the linked surgery's surgery_date.
    Fixed wages are dated by their start_date/end_date overlap with the range.
    Only active (is_active=True) MonthlyWage records are counted.
    Employees with no payroll in the period are excluded from results.

    Response:
        {
            "metadata": { start_date, end_date, wage_type, employee_id,
                          position_id, total_fixed_wages, total_commissions,
                          total_payments, employee_count },
            "count": N,
            "next": "...",
            "previous": "...",
            "results": [ { employee_id, employee_name, position_name,
                           total_fixed_wages, total_commissions,
                           total_payments }, ... ]
        }

    Access: admin or finance_user roles only.
    """

    permission_classes = [IsAdminOrFinanceUser]
    _VALID_WAGE_TYPES  = frozenset({'monthly', 'commission', 'hourly', 'all'})

    def get(self, request):
        params = request.query_params

        start_date_str  = params.get('start_date')
        end_date_str    = params.get('end_date')
        employee_id_str = params.get('employee_id')
        position_id_str = params.get('position_id')
        wage_type       = params.get('wage_type', 'all').strip().lower()

        if wage_type not in self._VALID_WAGE_TYPES:
            wage_type = 'all'

        date_start = None
        date_end   = None
        try:
            if start_date_str:
                date_start = datetime.date.fromisoformat(start_date_str)
            if end_date_str:
                date_end = datetime.date.fromisoformat(end_date_str)
        except ValueError:
            return Response(
                {'detail': 'فرمت تاریخ نامعتبر است. از YYYY-MM-DD استفاده کنید.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        employee_id = None
        position_id = None
        try:
            if employee_id_str:
                employee_id = int(employee_id_str)
            if position_id_str:
                position_id = int(position_id_str)
        except (ValueError, TypeError):
            return Response(
                {'detail': 'شناسه نامعتبر است.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Fixed wages ───────────────────────────────────────────────────
        wage_qs = MonthlyWage.objects.filter(is_active=True)
        if date_start:
            wage_qs = wage_qs.filter(
                Q(end_date__isnull=True) | Q(end_date__gte=date_start)
            )
        if date_end:
            wage_qs = wage_qs.filter(start_date__lte=date_end)
        if employee_id:
            wage_qs = wage_qs.filter(employee_id=employee_id)
        if position_id:
            wage_qs = wage_qs.filter(employee__job_position_id=position_id)

        # ── Commission transactions ───────────────────────────────────────
        ct_qs = CommissionTransaction.objects.all()
        if date_start:
            ct_qs = ct_qs.filter(surgery__surgery_date__date__gte=date_start)
        if date_end:
            ct_qs = ct_qs.filter(surgery__surgery_date__date__lte=date_end)
        if employee_id:
            ct_qs = ct_qs.filter(employee_id=employee_id)
        if position_id:
            ct_qs = ct_qs.filter(employee__job_position_id=position_id)

        # ── Hourly work entries (already-priced only) ────────────────────
        hwe_qs = HourlyWorkEntry.objects.filter(amount__isnull=False)
        if date_start:
            hwe_qs = hwe_qs.filter(work_date__gte=date_start)
        if date_end:
            hwe_qs = hwe_qs.filter(work_date__lte=date_end)
        if employee_id:
            hwe_qs = hwe_qs.filter(employee_id=employee_id)
        if position_id:
            hwe_qs = hwe_qs.filter(employee__job_position_id=position_id)

        # ── Per-employee DB aggregation ───────────────────────────────────
        wage_totals = {
            row['employee_id']: row['total']
            for row in wage_qs.values('employee_id').annotate(total=Sum('amount'))
        }
        commission_totals = {
            row['employee_id']: row['total']
            for row in ct_qs.values('employee_id').annotate(total=Sum('amount'))
        }
        hourly_totals = {
            row['employee_id']: row['total']
            for row in hwe_qs.values('employee_id').annotate(total=Sum('amount'))
        }
        hours_totals = {
            row['employee_id']: row['total']
            for row in hwe_qs.values('employee_id').annotate(total=Sum('hours_worked'))
        }

        if wage_type == 'monthly':
            relevant_ids = set(wage_totals)
        elif wage_type == 'commission':
            relevant_ids = set(commission_totals)
        elif wage_type == 'hourly':
            relevant_ids = set(hourly_totals)
        else:
            relevant_ids = set(wage_totals) | set(commission_totals) | set(hourly_totals)

        grand_fixed = sum(
            wage_totals.get(eid, Decimal('0')) for eid in relevant_ids
        )
        grand_commissions = sum(
            commission_totals.get(eid, Decimal('0')) for eid in relevant_ids
        )
        grand_hourly = sum(
            hourly_totals.get(eid, Decimal('0')) for eid in relevant_ids
        )
        grand_hours = sum(
            hours_totals.get(eid, Decimal('0')) for eid in relevant_ids
        )
        if wage_type == 'monthly':
            grand_commissions = Decimal('0')
            grand_hourly      = Decimal('0')
            grand_hours       = Decimal('0')
        elif wage_type == 'commission':
            grand_fixed  = Decimal('0')
            grand_hourly = Decimal('0')
            grand_hours  = Decimal('0')
        elif wage_type == 'hourly':
            grand_fixed       = Decimal('0')
            grand_commissions = Decimal('0')

        from employees.models import Employee
        emp_qs = (
            Employee.objects
            .filter(pk__in=relevant_ids)
            .select_related('job_position')
            .order_by('full_name')
        )

        total_count = emp_qs.count()

        metadata = {
            'start_date':         date_start,
            'end_date':           date_end,
            'wage_type':          wage_type,
            'employee_id':        employee_id,
            'position_id':        position_id,
            'total_fixed_wages':  grand_fixed,
            'total_commissions':  grand_commissions,
            'total_hourly_wages': grand_hourly,
            'total_hours_worked': grand_hours,
            'total_payments':     grand_fixed + grand_commissions + grand_hourly,
            'employee_count':     total_count,
        }

        if params.get('export') == 'excel':
            if total_count > EXCEL_MAX_ROWS:
                return Response(
                    {'detail': f'تعداد نتایج ({total_count:,}) بیشتر از حد مجاز است.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            all_emps = list(emp_qs)
            excel_rows = []
            for emp in all_emps:
                fixed = wage_totals.get(emp.pk, Decimal('0'))
                comm  = commission_totals.get(emp.pk, Decimal('0'))
                hourly = hourly_totals.get(emp.pk, Decimal('0'))
                hours  = hours_totals.get(emp.pk, Decimal('0'))
                if wage_type == 'monthly':
                    comm, hourly, hours = Decimal('0'), Decimal('0'), Decimal('0')
                elif wage_type == 'commission':
                    fixed, hourly, hours = Decimal('0'), Decimal('0'), Decimal('0')
                elif wage_type == 'hourly':
                    fixed, comm = Decimal('0'), Decimal('0')
                excel_rows.append({
                    'employee_name':      emp.full_name,
                    'position_name':      emp.job_position.name if emp.job_position else '',
                    'total_fixed_wages':  fixed,
                    'total_commissions':  comm,
                    'total_hourly_wages': hourly,
                    'total_hours_worked': hours,
                    'total_payments':     fixed + comm + hourly,
                })
            columns = [
                ('کارمند',            'employee_name'),
                ('پوزیشن',            'position_name'),
                ('حقوق ثابت',         'total_fixed_wages'),
                ('کمیسیون',           'total_commissions'),
                ('حقوق ساعتی',        'total_hourly_wages'),
                ('ساعات کارکرد',      'total_hours_worked'),
                ('مجموع پرداختی',     'total_payments'),
            ]
            meta_rows = [
                ('از تاریخ',  str(date_start or '')),
                ('تا تاریخ',  str(date_end   or '')),
                ('نوع حقوق',  wage_type),
            ]
            content = build_excel(columns=columns, rows=excel_rows,
                                   sheet_title='هزینه کارمندان', meta_rows=meta_rows)
            return excel_file_response(content, filename='employee_cost_report.xlsx')

        try:
            page      = max(1, int(params.get('page', 1)))
            page_size = min(max(1, int(params.get('page_size', 50))), 100)
        except (ValueError, TypeError):
            page, page_size = 1, 50

        offset     = (page - 1) * page_size
        page_emps  = list(emp_qs[offset:offset + page_size])

        results = []
        for emp in page_emps:
            fixed  = wage_totals.get(emp.pk, Decimal('0'))
            comm   = commission_totals.get(emp.pk, Decimal('0'))
            hourly = hourly_totals.get(emp.pk, Decimal('0'))
            hours  = hours_totals.get(emp.pk, Decimal('0'))
            if wage_type == 'monthly':
                comm, hourly, hours = Decimal('0'), Decimal('0'), Decimal('0')
            elif wage_type == 'commission':
                fixed, hourly, hours = Decimal('0'), Decimal('0'), Decimal('0')
            elif wage_type == 'hourly':
                fixed, comm = Decimal('0'), Decimal('0')
            results.append({
                'employee_id':        emp.pk,
                'employee_name':      emp.full_name,
                'position_name':      emp.job_position.name if emp.job_position else '',
                'total_fixed_wages':  fixed,
                'total_commissions':  comm,
                'total_hourly_wages': hourly,
                'total_hours_worked': hours,
                'total_payments':     fixed + comm + hourly,
            })

        def _page_url(p):
            p_copy = dict(params)
            p_copy['page']      = str(p)
            p_copy['page_size'] = str(page_size)
            return (
                request.build_absolute_uri(request.path)
                + '?' + '&'.join(f'{k}={v}' for k, v in p_copy.items())
            )

        next_url = _page_url(page + 1) if offset + page_size < total_count else None
        prev_url = _page_url(page - 1) if page > 1 else None

        return Response({
            'metadata': EmployeeCostReportSummarySerializer(metadata).data,
            'count':    total_count,
            'next':     next_url,
            'previous': prev_url,
            'results':  EmployeeCostReportRowSerializer(results, many=True).data,
        })