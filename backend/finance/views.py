import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
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
from finance.services import (
    SLUG_ANESTHESIA,
    SLUG_CENTER_COMMISSION,
    SLUG_COMMISSION,
    SLUG_DAILY_SUPPLIES,
    SLUG_EQUIPMENT,
    SLUG_MEDICINE,
    SLUG_SALARY,
    SLUG_UNIVERSITY,
)


# ---------------------------------------------------------------------------
# Shared computation helper — optimized with single GROUP BY queries
# ---------------------------------------------------------------------------

def compute_finance_summary(date_start=None, date_end=None, year_int=None, month_int=None) -> dict:
    """Compute finance summary with cumulative balance.

    If month is provided without year, raises ValueError.
    """
    # منطقی: اگر ماه بدون سال باشد، خطا بده
    if month_int is not None and year_int is None:
        raise ValueError("سال (year) همراه با ماه (month) الزامی است.")

    qs = Transaction.objects.exclude(payment_status=TransactionPaymentStatus.CANCELLED)

    # اعمال فیلترهای بازه زمانی
    if date_start:
        qs = qs.filter(transaction_date__date__gte=date_start)
    if date_end:
        qs = qs.filter(transaction_date__date__lte=date_end)
    if year_int and month_int:
        import calendar
        first = datetime.date(year_int, month_int, 1)
        last = datetime.date(year_int, month_int, calendar.monthrange(year_int, month_int)[1])
        qs = qs.filter(transaction_date__date__gte=first, transaction_date__date__lte=last)
    elif year_int:
        qs = qs.filter(transaction_date__year=year_int)
    elif month_int:
        # اگر ماه بدون سال باشد (قبلاً خطا دادیم، ولی برای امنیت باز هم چک می‌کنیم)
        pass

    # تفکیک کوئری‌های درآمد و هزینه
    income_qs = qs.filter(transaction_type=TransactionType.INCOME)
    expense_qs = qs.filter(transaction_type=TransactionType.EXPENSE)

    # --------------------------------------------------------------
    # بهینه‌سازی: محاسبه مجموع همه دسته‌بندی‌ها با دو کوئری GROUP BY
    # --------------------------------------------------------------
    income_agg = {
        item['category__slug']: item['total']
        for item in income_qs.values('category__slug').annotate(total=Sum('amount'))
        if item['category__slug']
    }
    expense_agg = {
        item['category__slug']: item['total']
        for item in expense_qs.values('category__slug').annotate(total=Sum('amount'))
        if item['category__slug']
    }

    def get_expense(slug):
        return expense_agg.get(slug, Decimal('0'))

    def get_income(slug):
        return income_agg.get(slug, Decimal('0'))

    # --------------------------------------------------------------
    # محاسبه مجموع کل درآمد و هزینه در بازه
    # --------------------------------------------------------------
    total_income_period = income_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    total_expense_period = expense_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # --------------------------------------------------------------
    # محاسبه بالانس تجمعی تا انتهای بازه (از ابتدای تاریخ)
    # --------------------------------------------------------------
    # تاریخ پایان بازه را مشخص می‌کنیم
    if date_end:
        end_date = date_end
    elif year_int and month_int:
        import calendar
        end_date = datetime.date(year_int, month_int, calendar.monthrange(year_int, month_int)[1])
    elif year_int:
        end_date = datetime.date(year_int, 12, 31)
    elif date_start:
        # اگر فقط start_date داده شده، تا امروز را محاسبه کن
        end_date = datetime.date.today()
    else:
        end_date = datetime.date.today()

    cumulative_qs = Transaction.objects.exclude(
        payment_status=TransactionPaymentStatus.CANCELLED
    ).filter(transaction_date__date__lte=end_date)

    total_income_cum = cumulative_qs.filter(transaction_type=TransactionType.INCOME).aggregate(
        t=Sum('amount')
    )['t'] or Decimal('0')

    total_expense_cum = cumulative_qs.filter(transaction_type=TransactionType.EXPENSE).aggregate(
        t=Sum('amount')
    )['t'] or Decimal('0')

    final_balance_cumulative = total_income_cum - total_expense_cum

    # --------------------------------------------------------------
    # استخراج مقادیر مورد نیاز از دیکشنری‌های aggregator
    # --------------------------------------------------------------
    return {
        'total_income_period': total_income_period,
        'total_expense_period': total_expense_period,
        'final_balance_cumulative': final_balance_cumulative,
        'total_employee_cost_period': get_expense(SLUG_SALARY) + get_expense(SLUG_COMMISSION),
        'total_equipment_cost_period': get_expense(SLUG_EQUIPMENT),
        'total_medicine_cost_period': get_expense(SLUG_MEDICINE),
        'center_commission_income_period': get_income(SLUG_CENTER_COMMISSION),
        'university_commission_period': get_expense(SLUG_UNIVERSITY),
        'anesthesia_cost_period': get_expense(SLUG_ANESTHESIA),
        'daily_supplies_cost_period': get_expense(SLUG_DAILY_SUPPLIES),
    }


def compute_finance_trend(year_int=None) -> list:
    """Return monthly income/expense with cumulative balance."""
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

    data = {}
    for row in rows:
        m = row['month'].strftime('%Y-%m') if row['month'] else None
        if not m:
            continue
        if m not in data:
            data[m] = {'month': m, 'income': Decimal('0'), 'expense': Decimal('0')}
        data[m][row['transaction_type']] = row['total'] or Decimal('0')

    sorted_months = sorted(data.keys())
    cumulative_balance = Decimal('0')
    result = []
    for m in sorted_months:
        income = data[m]['income']
        expense = data[m]['expense']
        cumulative_balance += income - expense
        result.append({
            'month': m,
            'income': float(income),
            'expense': float(expense),
            'cumulative_balance': float(cumulative_balance),
        })

    return result


# ---------------------------------------------------------------------------
# ViewSets with proper permissions
# ---------------------------------------------------------------------------

class FinanceCategoryViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category_type', 'is_active']
    search_fields = ['name', 'slug', 'description']
    ordering_fields = ['name', 'category_type', 'created_at']
    ordering = ['category_type', 'name']
    serializer_class = FinanceCategorySerializer

    def get_queryset(self):
        return FinanceCategory.objects.all()

    def get_permissions(self):
        # فقط کاربران مجاز (ادمین یا مالی) اجازه ایجاد/ویرایش/حذف دارند
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrFinanceUser()]
        return [IsAuthenticated()]


class TransactionViewSet(viewsets.ModelViewSet):
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

    def get_permissions(self):
        # فقط کاربران مجاز (ادمین یا مالی) اجازه ایجاد/ویرایش/حذف دارند
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrFinanceUser()]
        return [IsAuthenticated()]


# ---------------------------------------------------------------------------
# Balance Report
# ---------------------------------------------------------------------------

class BalanceReportView(APIView):
    """Financial balance report with date-range filtering."""
    permission_classes = [IsAdminOrFinanceUser]

    def get(self, request):
        params = request.query_params
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        year = params.get('year')
        month = params.get('month')

        date_start = None
        date_end = None
        year_int = None
        month_int = None

        # تبدیل تاریخ‌ها
        if start_date:
            try:
                date_start = parse_jalali_date(start_date)
            except ValueError:
                return Response(
                    {'error': 'فرمت start_date نامعتبر است.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date:
            try:
                date_end = parse_jalali_date(end_date)
            except ValueError:
                return Response(
                    {'error': 'فرمت end_date نامعتبر است.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if year:
            try:
                year_int = int(year)
            except ValueError:
                return Response(
                    {'error': 'فرمت year نامعتبر است.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if month:
            try:
                month_int = int(month)
                if not (1 <= month_int <= 12):
                    raise ValueError
            except ValueError:
                return Response(
                    {'error': 'فرمت month نامعتبر است. باید عددی بین ۱ تا ۱۲ باشد.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # منطقی: اگر ماه بدون سال باشد، خطا بده
        if month_int is not None and year_int is None:
            return Response(
                {'error': 'پارامتر year به همراه month الزامی است.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            data = compute_finance_summary(
                date_start=date_start,
                date_end=date_end,
                year_int=year_int,
                month_int=month_int,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response_data = {
            'total_income_period': data['total_income_period'],
            'total_expense_period': data['total_expense_period'],
            'final_balance_cumulative': data['final_balance_cumulative'],
            'total_employee_cost_period': data['total_employee_cost_period'],
            'total_equipment_cost_period': data['total_equipment_cost_period'],
            'total_medicine_cost_period': data['total_medicine_cost_period'],
            'center_commission_income_period': data['center_commission_income_period'],
            'university_commission_period': data['university_commission_period'],
            'anesthesia_cost_period': data['anesthesia_cost_period'],
            'daily_supplies_cost_period': data['daily_supplies_cost_period'],
        }

        if params.get('export') == 'excel':
            row = {
                'date_range': f"{start_date or '—'} تا {end_date or '—'}",
                **response_data
            }
            columns = [
                ('بازه زمانی', 'date_range'),
                ('مجموع درآمد (بازه)', 'total_income_period'),
                ('مجموع هزینه (بازه)', 'total_expense_period'),
                ('موجودی انباشته تا پایان بازه', 'final_balance_cumulative'),
                ('هزینه کارمندان (بازه)', 'total_employee_cost_period'),
                ('هزینه دارو (بازه)', 'total_medicine_cost_period'),
                ('هزینه تجهیزات (بازه)', 'total_equipment_cost_period'),
                ('درآمد کمیسیون مرکز (بازه)', 'center_commission_income_period'),
                ('هزینه متخصصان بیهوشی (بازه)', 'anesthesia_cost_period'),
                ('هزینه ملزومات روزمره (بازه)', 'daily_supplies_cost_period'),
            ]
            content = build_excel(columns=columns, rows=[row], sheet_title='گزارش مالی')
            return excel_file_response(content, filename='balance_report.xlsx')

        return Response(response_data)


# ---------------------------------------------------------------------------
# Finance Trend (for dashboard chart)
# ---------------------------------------------------------------------------

class FinanceTrendView(APIView):
    """Monthly income/expense trend for charts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        year_str = request.query_params.get('year')
        year_int = None
        if year_str:
            try:
                year_int = int(year_str)
            except ValueError:
                return Response(
                    {'error': 'فرمت year نامعتبر است.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(compute_finance_trend(year_int=year_int))