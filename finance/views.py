import datetime
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminOrFinanceUser

from common.dates import parse_jalali_date
from common.excel import build_excel, excel_file_response

from finance.filters import TransactionFilter
from finance.models import FinanceCategory, Transaction, TransactionPaymentStatus, TransactionType
from finance.serializers import (
    BalanceReportSerializer,
    FinanceCategorySerializer,
    TransactionListSerializer,
    TransactionSerializer,
)


# ---------------------------------------------------------------------------
# Shared computation helper — used by both the API view and the admin view
# ---------------------------------------------------------------------------

_MEDICINE_CAT     = 'هزینه دارو'
_EQUIPMENT_CAT    = 'هزینه تجهیزات'
_CENTER_INC_CAT   = 'کمیسیون مرکز از اعمال جراحی'
_ANESTHESIA_CAT   = 'هزینه ماهانه متخصصان بیهوشی'
_DAILY_CAT        = 'هزینه ماهانه ملزومات روزمره'


def compute_finance_summary(
    date_start=None, date_end=None, year_int=None, month_int=None
) -> dict:
    """Compute all finance dashboard summary numbers.

    Parameters may all be None (returns all-time totals).
    Always returns a dict with Decimal values — never None.
    """
    qs = Transaction.objects.exclude(
        payment_status=TransactionPaymentStatus.CANCELLED,
    )
    if date_start:
        qs = qs.filter(transaction_date__date__gte=date_start)
    if date_end:
        qs = qs.filter(transaction_date__date__lte=date_end)
    if year_int:
        qs = qs.filter(transaction_date__year=year_int)
    if month_int:
        qs = qs.filter(transaction_date__month=month_int)

    income_qs  = qs.filter(transaction_type=TransactionType.INCOME)
    expense_qs = qs.filter(transaction_type=TransactionType.EXPENSE)

    def _sum(queryset):
        return queryset.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    def _cat_ids(name, cat_type):
        return list(
            FinanceCategory.objects.filter(name=name, category_type=cat_type)
            .values_list('pk', flat=True)
        )

    medicine_ids    = _cat_ids(_MEDICINE_CAT,   'expense')
    equipment_ids   = _cat_ids(_EQUIPMENT_CAT,  'expense')
    center_inc_ids  = _cat_ids(_CENTER_INC_CAT, 'income')
    anesthesia_ids  = _cat_ids(_ANESTHESIA_CAT, 'expense')
    daily_ids       = _cat_ids(_DAILY_CAT,      'expense')

    total_income  = _sum(income_qs)
    total_expense = _sum(expense_qs)

    # ── Employee cost: query payroll models directly ──────────────────
    from payroll.models import CommissionTransaction, MonthlyWage

    wage_qs = MonthlyWage.objects.filter(is_active=True)
    if date_start:
        wage_qs = wage_qs.filter(Q(end_date__isnull=True) | Q(end_date__gte=date_start))
    if date_end:
        wage_qs = wage_qs.filter(start_date__lte=date_end)
    if year_int:
        wage_qs = wage_qs.filter(start_date__year=year_int)
    if month_int:
        wage_qs = wage_qs.filter(start_date__month=month_int)
    total_wages = wage_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    comm_qs = CommissionTransaction.objects.all()
    if date_start:
        comm_qs = comm_qs.filter(surgery__surgery_date__date__gte=date_start)
    if date_end:
        comm_qs = comm_qs.filter(surgery__surgery_date__date__lte=date_end)
    if year_int:
        comm_qs = comm_qs.filter(surgery__surgery_date__year=year_int)
    if month_int:
        comm_qs = comm_qs.filter(surgery__surgery_date__month=month_int)
    total_commissions = comm_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # ── Hourly work entries (new system — canonical source) ────────────
    # work_date is Gregorian, like MonthlyWage.start_date and
    # CommissionTransaction's surgery date above — year_int/month_int are
    # applied directly, the same way, for consistency with those.
    from payroll.models import HourlyWorkEntry
    hwe_qs = HourlyWorkEntry.objects.filter(amount__isnull=False)
    if date_start:
        hwe_qs = hwe_qs.filter(work_date__gte=date_start)
    if date_end:
        hwe_qs = hwe_qs.filter(work_date__lte=date_end)
    if year_int:
        hwe_qs = hwe_qs.filter(work_date__year=year_int)
    if month_int:
        hwe_qs = hwe_qs.filter(work_date__month=month_int)
    hourly_entry_employee_ids = set(
        hwe_qs.values_list('employee_id', flat=True).distinct()
    )
    total_hourly = hwe_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # ── Hourly work records (legacy) — only for employees with NO new-
    # system data in this same window, so an employee already migrated to
    # HourlyWorkEntry is never counted by both hourly systems at once. ────
    from payroll.models import HourlyWorkRecord
    hw_qs = HourlyWorkRecord.objects.exclude(employee_id__in=hourly_entry_employee_ids)
    if date_start:
        hw_qs = hw_qs.filter(record_date__gte=date_start)
    if date_end:
        hw_qs = hw_qs.filter(record_date__lte=date_end)
    if year_int:
        hw_qs = hw_qs.filter(jalali_year=year_int)
    if month_int:
        hw_qs = hw_qs.filter(jalali_month=month_int)
    total_hourly += hw_qs.aggregate(t=Sum('calculated_salary'))['t'] or Decimal('0')

    # ── Employee purchase commissions ─────────────────────────────────
    from employees.models import EmployeePurchaseCommission
    epc_qs = EmployeePurchaseCommission.objects.all()
    if date_start:
        epc_qs = epc_qs.filter(commission_date__gte=date_start)
    if date_end:
        epc_qs = epc_qs.filter(commission_date__lte=date_end)
    total_purchase_commissions = epc_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    total_employee_cost = total_wages + total_commissions + total_hourly + total_purchase_commissions

    # ── University commission: 45% of surgery amounts ─────────────────
    from surgeries.models import SurgeryHistory
    sh_qs = SurgeryHistory.objects.exclude(status='CANCELLED')
    if date_start:
        sh_qs = sh_qs.filter(surgery_date__date__gte=date_start)
    if date_end:
        sh_qs = sh_qs.filter(surgery_date__date__lte=date_end)
    if year_int:
        sh_qs = sh_qs.filter(surgery_date__year=year_int)
    if month_int:
        sh_qs = sh_qs.filter(surgery_date__month=month_int)
    total_surgery = sh_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    university_commission = (total_surgery * Decimal('45') / Decimal('100')).quantize(Decimal('1'))

    return {
        'total_income':             total_income,
        'total_expense':            total_expense,
        'final_balance':            total_income - total_expense,
        'total_employee_cost':      total_employee_cost,
        'total_equipment_cost':     _sum(expense_qs.filter(category_id__in=equipment_ids)),
        'total_medicine_cost':      _sum(expense_qs.filter(category_id__in=medicine_ids)),
        'center_commission_income': _sum(income_qs.filter(category_id__in=center_inc_ids)),
        'university_commission':    university_commission,
        'anesthesia_cost':          _sum(expense_qs.filter(category_id__in=anesthesia_ids)),
        'daily_supplies_cost':      _sum(expense_qs.filter(category_id__in=daily_ids)),
    }


def compute_finance_trend(year_int=None) -> list:
    """Return monthly income/expense trend for the chart."""
    qs = Transaction.objects.exclude(payment_status=TransactionPaymentStatus.CANCELLED)
    if year_int:
        qs = qs.filter(transaction_date__year=year_int)
    rows = (
        qs
        .annotate(month=TruncMonth('transaction_date'))
        .values('month', 'transaction_type')
        .annotate(total=Sum('amount'))
        .order_by('month', 'transaction_type')
    )
    result = {}
    for row in rows:
        m = row['month'].strftime('%Y-%m') if row['month'] else None
        if not m:
            continue
        if m not in result:
            result[m] = {'month': m, 'income': 0, 'expense': 0}
        result[m][row['transaction_type']] = float(row['total'] or 0)
    return sorted(result.values(), key=lambda x: x['month'])


class FinanceCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category_type', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'category_type', 'created_at']
    ordering = ['category_type', 'name']
    serializer_class = FinanceCategorySerializer

    def get_queryset(self):
        return FinanceCategory.objects.all()


class TransactionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TransactionFilter
    search_fields = ['description']
    ordering_fields = ['transaction_date', 'amount', 'created_at']
    ordering = ['-transaction_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return TransactionListSerializer
        return TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.select_related('category', 'content_type').all()


# ---------------------------------------------------------------------------
# Balance Report
# ---------------------------------------------------------------------------

class BalanceReportView(APIView):
    """Financial balance report with date-range filtering.

    GET /api/v1/finance/reports/balance/

    Query parameters:
      start_date  — YYYY-MM-DD  (inclusive lower bound on transaction_date)
      end_date    — YYYY-MM-DD  (inclusive upper bound on transaction_date)
      year        — Gregorian year integer filter on transaction_date
      month       — Gregorian month (1-12) filter on transaction_date

    Returns zero values (not null) when no Transactions match.
    Cancelled Transactions are excluded from all totals.

    Returned fields:
      total_income             — sum of all income Transactions
      total_expense            — sum of all expense Transactions
      final_balance            — total_income − total_expense
      total_employee_cost      — salary + commission category expenses
      total_equipment_cost     — equipment cost category expenses
      total_medicine_cost      — medicine cost category expenses
      center_commission_income — center commission income category
    """

    permission_classes = [IsAdminOrFinanceUser]

    # Seeded category names — must match the data migrations exactly
    _MEDICINE_CAT  = 'هزینه دارو'
    _EQUIPMENT_CAT = 'هزینه تجهیزات'
    _SALARY_CAT    = 'حقوق ثابت کارمندان'
    _COMMISSION_CAT = 'کمیسیون کارمندان'
    _CENTER_INC_CAT = 'کمیسیون مرکز از اعمال جراحی'

    @staticmethod
    def _cat_ids(name: str, cat_type: str) -> list:
        return list(
            FinanceCategory.objects.filter(name=name, category_type=cat_type)
            .values_list('pk', flat=True)
        )

    @staticmethod
    def _sum(qs) -> Decimal:
        return qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    def get(self, request):
        params = request.query_params

        start_date = params.get('start_date')
        end_date   = params.get('end_date')
        year       = params.get('year')
        month      = params.get('month')

        date_start: datetime.date | None = None
        date_end:   datetime.date | None = None
        if start_date:
            try:
                date_start = parse_jalali_date(start_date)   # accepts Jalali or ISO
            except ValueError:
                pass
        if end_date:
            try:
                date_end = parse_jalali_date(end_date)        # accepts Jalali or ISO
            except ValueError:
                pass
        year_int  = None
        month_int = None
        try:
            year_int  = int(year)  if year  else None
            month_int = int(month) if month else None
        except (ValueError, TypeError):
            pass

        data = compute_finance_summary(
            date_start=date_start,
            date_end=date_end,
            year_int=year_int,
            month_int=month_int,
        )

        serializer = BalanceReportSerializer(data)

        if params.get('export') == 'excel':
            date_range = f"{start_date or '—'} تا {end_date or '—'}"
            row = {
                'date_range':              date_range,
                'total_income':            data['total_income'],
                'total_expense':           data['total_expense'],
                'final_balance':           data['final_balance'],
                'total_employee_cost':     data['total_employee_cost'],
                'total_medicine_cost':     data['total_medicine_cost'],
                'total_equipment_cost':    data['total_equipment_cost'],
                'center_commission_income': data['center_commission_income'],
                'anesthesia_cost':         data['anesthesia_cost'],
                'daily_supplies_cost':     data['daily_supplies_cost'],
            }
            columns = [
                ('بازه زمانی',                     'date_range'),
                ('مجموع درآمد',                    'total_income'),
                ('مجموع هزینه',                    'total_expense'),
                ('سود / زیان نهایی',               'final_balance'),
                ('هزینه کارمندان',                 'total_employee_cost'),
                ('هزینه دارو',                     'total_medicine_cost'),
                ('هزینه تجهیزات',                  'total_equipment_cost'),
                ('درآمد کمیسیون مرکز',             'center_commission_income'),
                ('هزینه متخصصان بیهوشی',           'anesthesia_cost'),
                ('هزینه ملزومات روزمره',            'daily_supplies_cost'),
            ]
            content = build_excel(columns=columns, rows=[row], sheet_title='گزارش مالی')
            return excel_file_response(content, filename='balance_report.xlsx')

        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Finance Trend (for dashboard chart)
# ---------------------------------------------------------------------------

class FinanceTrendView(APIView):
    """Monthly income/expense trend for charts.

    GET /api/v1/finance/reports/trend/

    Query parameters:
      year  — Gregorian year to limit the trend (optional)

    Returns a list ordered by month:
      [{month: "YYYY-MM", income: "…", expense: "…"}, …]
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        year_int = None
        try:
            year_int = int(request.query_params.get('year', '') or 0) or None
        except (ValueError, TypeError):
            pass
        return Response(compute_finance_trend(year_int=year_int))
