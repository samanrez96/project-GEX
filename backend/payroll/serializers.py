from decimal import Decimal

from django.db.models import Q
from rest_framework import serializers

from .models import (
    CommissionRule,
    CommissionTransaction,
    HourlyRate,
    HourlyWorkEntry,
    MonthlyWage,
    PayrollPeriod,
    PayrollTypeConfig,
)


class PayrollPeriodSerializer(serializers.ModelSerializer):
    display_name = serializers.ReadOnlyField()

    class Meta:
        model  = PayrollPeriod
        fields = [
            'id', 'year', 'month', 'display_name',
            'status', 'notes', 'created_at', 'closed_at',
        ]
        read_only_fields = ['status', 'created_at', 'closed_at']

    def validate(self, attrs):
        year  = attrs.get('year',  getattr(self.instance, 'year',  None))
        month = attrs.get('month', getattr(self.instance, 'month', None))
        if month is not None and not (1 <= month <= 12):
            raise serializers.ValidationError({'month': 'ماه باید بین ۱ تا ۱۲ باشد.'})
        return attrs


class PayrollTypeConfigSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = PayrollTypeConfig
        fields = [
            'id', 'employee', 'employee_name',
            'has_monthly_wage', 'has_commission', 'has_hourly_wage',
            'notes', 'updated_at',
        ]
        read_only_fields = ['updated_at']

    def get_employee_name(self, obj) -> str:
        return obj.employee.full_name

    def validate(self, attrs):
        has_monthly = attrs.get('has_monthly_wage', getattr(self.instance, 'has_monthly_wage', False))
        has_comm    = attrs.get('has_commission',   getattr(self.instance, 'has_commission',   False))
        has_hourly  = attrs.get('has_hourly_wage',   getattr(self.instance, 'has_hourly_wage',   False))
        # Mirror the model's clean() — only on updates (instance exists)
        if self.instance and not has_monthly and not has_comm and not has_hourly:
            raise serializers.ValidationError(
                'حداقل یکی از گزینه‌های حقوق ثابت، کمیسیون یا حقوق ساعتی باید فعال باشد.'
            )
        return attrs


class PayrollTypeSummarySerializer(serializers.ModelSerializer):
    payroll_type_label = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = PayrollTypeConfig
        fields = ['has_monthly_wage', 'has_commission', 'has_hourly_wage', 'payroll_type_label']

    def get_payroll_type_label(self, obj) -> str:
        # 'کمیسیونی' (not 'کمیسیون') when commission is the only active
        # component — preserves the exact pre-existing label string.
        parts = []
        if obj.has_monthly_wage:
            parts.append('ثابت')
        if obj.has_hourly_wage:
            parts.append('ساعتی')
        if obj.has_commission:
            parts.append('کمیسیونی' if not parts else 'کمیسیون')
        return ' + '.join(parts) if parts else 'تنظیم نشده'


# ---------------------------------------------------------------------------
# MonthlyWage serializers
# ---------------------------------------------------------------------------

class MonthlyWageListSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = MonthlyWage
        fields = ['id', 'employee_name', 'amount', 'start_date', 'end_date', 'is_active']

    def get_employee_name(self, obj) -> str:
        return obj.employee.full_name


class MonthlyWageSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = MonthlyWage
        fields = [
            'id', 'employee', 'employee_name',
            'amount', 'start_date', 'end_date',
            'is_active', 'notes',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_employee_name(self, obj) -> str:
        return obj.employee.full_name

    def validate(self, attrs):
        if self.instance is not None and 'amount' in attrs:
            raise serializers.ValidationError({'amount': 'مبلغ حقوق قابل ویرایش نیست.'})

        employee   = attrs.get('employee',   getattr(self.instance, 'employee',   None))
        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end_date   = attrs.get('end_date',   getattr(self.instance, 'end_date',   None))

        if end_date is not None and start_date and end_date < start_date:
            raise serializers.ValidationError(
                {'end_date': 'تاریخ پایان باید بعد از تاریخ شروع باشد.'}
            )

        if employee and start_date:
            cond_running = Q(end_date__isnull=True) | Q(end_date__gte=start_date)
            cond_started = Q(start_date__lte=end_date) if end_date else Q()
            qs = MonthlyWage.objects.filter(
                employee=employee, is_active=True,
            ).filter(cond_running).filter(cond_started)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'این کارمند در این بازه زمانی دارای حقوق فعال دیگری است.'
                )

        return attrs

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('مبلغ حقوق باید بزرگ‌تر از صفر باشد.')
        return value


class MonthlyWagePeriodSummarySerializer(serializers.Serializer):
    year           = serializers.IntegerField()
    month          = serializers.IntegerField()
    total_amount   = serializers.DecimalField(max_digits=16, decimal_places=2)
    employee_count = serializers.IntegerField()
    wages          = MonthlyWageListSerializer(many=True)


# ---------------------------------------------------------------------------
# HourlyRate serializers — mirrors MonthlyWage's shape/rules exactly
# ---------------------------------------------------------------------------

class HourlyRateListSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = HourlyRate
        fields = ['id', 'employee_name', 'rate', 'start_date', 'end_date', 'is_active']

    def get_employee_name(self, obj) -> str:
        return obj.employee.full_name


class HourlyRateSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = HourlyRate
        fields = [
            'id', 'employee', 'employee_name',
            'rate', 'start_date', 'end_date',
            'is_active', 'notes',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_employee_name(self, obj) -> str:
        return obj.employee.full_name

    def validate(self, attrs):
        if self.instance is not None and 'rate' in attrs:
            raise serializers.ValidationError({'rate': 'نرخ ساعتی قابل ویرایش نیست.'})

        employee   = attrs.get('employee',   getattr(self.instance, 'employee',   None))
        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end_date   = attrs.get('end_date',   getattr(self.instance, 'end_date',   None))

        if end_date is not None and start_date and end_date < start_date:
            raise serializers.ValidationError(
                {'end_date': 'تاریخ پایان باید بعد از تاریخ شروع باشد.'}
            )

        if employee and start_date:
            cond_running = Q(end_date__isnull=True) | Q(end_date__gte=start_date)
            cond_started = Q(start_date__lte=end_date) if end_date else Q()
            qs = HourlyRate.objects.filter(
                employee=employee, is_active=True,
            ).filter(cond_running).filter(cond_started)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'این کارمند در این بازه زمانی دارای نرخ ساعتی فعال دیگری است.'
                )

        return attrs

    def validate_rate(self, value):
        if value < 0:
            raise serializers.ValidationError('نرخ هر ساعت نمی‌تواند منفی باشد.')
        return value


# ---------------------------------------------------------------------------
# HourlyWorkEntry serializers
# ---------------------------------------------------------------------------

class HourlyWorkEntryListSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = HourlyWorkEntry
        fields = [
            'id', 'employee_name', 'work_date', 'hours_worked',
            'rate_used', 'amount', 'payroll_period', 'is_processed',
        ]

    def get_employee_name(self, obj) -> str:
        return obj.employee.full_name


class HourlyWorkEntrySerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)
    is_processed  = serializers.BooleanField(read_only=True)

    class Meta:
        model  = HourlyWorkEntry
        fields = [
            'id', 'employee', 'employee_name',
            'work_date', 'hours_worked', 'description',
            'payroll_period', 'is_processed',
            'rate_used', 'amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'payroll_period', 'rate_used', 'amount',
            'created_at', 'updated_at',
        ]

    def validate_hours_worked(self, value):
        if value <= 0:
            raise serializers.ValidationError('ساعات کارکرد باید بزرگ‌تر از صفر باشد.')
        if value > 24:
            raise serializers.ValidationError('یک رکورد روزانه نمی‌تواند بیشتر از ۲۴ ساعت باشد.')
        return value

    def validate(self, attrs):
        if self.instance is not None and self.instance.is_processed:
            changed_fields = {'employee', 'work_date', 'hours_worked'} & set(attrs)
            if changed_fields:
                raise serializers.ValidationError(
                    'این رکورد در محاسبه حقوق پردازش شده و قابل ویرایش نیست. '
                    'برای ویرایش، ابتدا آن را از دوره حقوقی خارج کنید.'
                )
        return attrs


# ---------------------------------------------------------------------------
# CommissionRule serializers
# ---------------------------------------------------------------------------

class CommissionRuleListSerializer(serializers.ModelSerializer):
    job_position_name = serializers.SerializerMethodField(read_only=True)
    surgery_type_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = CommissionRule
        fields = ['id', 'job_position_name', 'surgery_type_name', 'commission_percent', 'is_active']

    def get_job_position_name(self, obj) -> str:
        return obj.job_position.name

    def get_surgery_type_name(self, obj) -> str:
        return obj.surgery_type.name


class CommissionRuleSerializer(serializers.ModelSerializer):
    job_position_name = serializers.SerializerMethodField(read_only=True)
    surgery_type_name = serializers.SerializerMethodField(read_only=True)
    surgery_type_code = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = CommissionRule
        fields = [
            'id', 'job_position', 'job_position_name',
            'surgery_type', 'surgery_type_name', 'surgery_type_code',
            'commission_percent', 'start_date',
            'is_active', 'notes',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_job_position_name(self, obj) -> str:
        return obj.job_position.name

    def get_surgery_type_name(self, obj) -> str:
        return obj.surgery_type.name

    def get_surgery_type_code(self, obj) -> str:
        return obj.surgery_type.code

    def validate_commission_percent(self, value):
        if value <= 0:
            raise serializers.ValidationError('درصد کمیسیون باید بزرگ‌تر از صفر باشد.')
        if value > 100:
            raise serializers.ValidationError('درصد کمیسیون نمی‌تواند بیشتر از ۱۰۰ باشد.')
        return value

    def validate(self, attrs):
        if self.instance is not None and 'commission_percent' in attrs:
            raise serializers.ValidationError(
                {'commission_percent': 'درصد کمیسیون قابل ویرایش نیست.'}
            )

        job_position = attrs.get('job_position', getattr(self.instance, 'job_position', None))
        surgery_type = attrs.get('surgery_type', getattr(self.instance, 'surgery_type', None))
        is_active    = attrs.get('is_active',    getattr(self.instance, 'is_active',    True))

        if job_position and surgery_type and is_active:
            qs = CommissionRule.objects.filter(
                job_position=job_position,
                surgery_type=surgery_type,
                is_active=True,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'یک قانون کمیسیون فعال برای این ترکیب موقعیت شغلی و نوع عمل وجود دارد.'
                )

        return attrs


class CommissionRuleMatrixSerializer(serializers.Serializer):
    positions     = serializers.ListField(child=serializers.CharField())
    surgery_types = serializers.ListField(child=serializers.CharField())
    matrix        = serializers.DictField()


# ---------------------------------------------------------------------------
# CommissionTransaction serializers
# ---------------------------------------------------------------------------

class CommissionTransactionSerializer(serializers.ModelSerializer):
    employee_name       = serializers.CharField(source='employee.full_name',           read_only=True)
    job_position_name   = serializers.CharField(source='employee.job_position.name',   read_only=True)
    surgery_type_name   = serializers.CharField(source='commission_rule.surgery_type.name', read_only=True)
    commission_percent  = serializers.DecimalField(
        source='commission_rule.commission_percent',
        max_digits=5, decimal_places=2, read_only=True,
    )
    patient_name        = serializers.CharField(source='surgery.patient.full_name',    read_only=True)
    surgery_date        = serializers.SerializerMethodField(read_only=True)
    surgery_amount      = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = CommissionTransaction
        fields = [
            'id', 'surgery', 'patient_name',
            'employee', 'employee_name', 'job_position_name',
            'commission_rule', 'surgery_type_name', 'commission_percent',
            'surgery_date', 'surgery_amount',
            'amount', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['amount', 'created_at', 'updated_at']

    def get_surgery_date(self, obj) -> str | None:
        try:
            if obj.surgery and obj.surgery.surgery_date:
                d = obj.surgery.surgery_date
                return d.date().isoformat() if hasattr(d, 'date') else str(d)[:10]
        except Exception:
            pass
        return None

    def get_surgery_amount(self, obj) -> str | None:
        try:
            if obj.surgery and obj.surgery.amount is not None:
                from decimal import Decimal
                return str(obj.surgery.amount.quantize(Decimal('1')))
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Payroll Report serializers
# ---------------------------------------------------------------------------

class PayrollReportEmployeeSerializer(serializers.Serializer):
    """One payroll row. Every field here is named and always present —
    the frontend maps table cells by these names, never by dict order or
    array index (see static/admin/js/payroll_page.js)."""

    employee_id          = serializers.IntegerField()
    employee_name        = serializers.CharField()
    job_position         = serializers.CharField()
    fixed_salary         = serializers.DecimalField(max_digits=16, decimal_places=2)
    purchase_commission  = serializers.DecimalField(max_digits=16, decimal_places=2)
    surgery_commission   = serializers.DecimalField(max_digits=16, decimal_places=2)
    total_commission     = serializers.DecimalField(max_digits=16, decimal_places=2)
    has_commission       = serializers.BooleanField(default=False)
    # The employee's effective hourly figures for this period — from
    # HourlyWorkEntry (new, canonical) when the employee has any priced
    # entries in range, otherwise from HourlyWorkRecord (legacy) as a
    # fallback. Never a sum of both for the same employee — see
    # PayrollReportView.get() for the disambiguation. total_hours_worked is
    # always the hours paired with this exact hourly_salary figure, so the
    # two can never be inconsistent (one populated, the other blank).
    hourly_salary        = serializers.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    total_hours_worked   = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    total_payment        = serializers.DecimalField(max_digits=16, decimal_places=2)


class PayrollReportSerializer(serializers.Serializer):
    start_date                  = serializers.DateField(required=False, allow_null=True)
    end_date                    = serializers.DateField(required=False, allow_null=True)
    total_fixed_salary          = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_commission            = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_hourly_salary         = serializers.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    total_hours_worked          = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total_labor_cost            = serializers.DecimalField(max_digits=18, decimal_places=2)
    employee_count              = serializers.IntegerField()
    employees                   = PayrollReportEmployeeSerializer(many=True)


# ---------------------------------------------------------------------------
# Employee Cost Report serializers (CLI-52)
# ---------------------------------------------------------------------------

class EmployeeCostReportSummarySerializer(serializers.Serializer):
    """Metadata / grand-total block for the employee cost report."""

    start_date         = serializers.DateField(allow_null=True)
    end_date           = serializers.DateField(allow_null=True)
    wage_type          = serializers.CharField()
    employee_id        = serializers.IntegerField(allow_null=True)
    position_id        = serializers.IntegerField(allow_null=True)
    total_fixed_wages  = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_commissions  = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_hourly_wages = serializers.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    total_hours_worked = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total_payments     = serializers.DecimalField(max_digits=18, decimal_places=2)
    employee_count     = serializers.IntegerField()


class EmployeeCostReportRowSerializer(serializers.Serializer):
    """One row in the employee cost report — costs for a single employee."""

    employee_id        = serializers.IntegerField()
    employee_name      = serializers.CharField()
    position_name      = serializers.CharField()
    total_fixed_wages  = serializers.DecimalField(max_digits=16, decimal_places=2)
    total_commissions  = serializers.DecimalField(max_digits=16, decimal_places=2)
    total_hourly_wages = serializers.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    total_hours_worked = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    total_payments     = serializers.DecimalField(max_digits=16, decimal_places=2)
