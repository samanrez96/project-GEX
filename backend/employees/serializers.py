from rest_framework import serializers

from employees.models import Employee, EmployeePurchaseCommission, JobPosition


# ---------------------------------------------------------------------------
# JobPosition serializers
# ---------------------------------------------------------------------------

class JobPositionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for dropdowns."""

    class Meta:
        model  = JobPosition
        fields = ["id", "name", "is_active"]


class JobPositionSerializer(serializers.ModelSerializer):
    """Full serializer — for detail / create / update views."""

    active_employee_count = serializers.SerializerMethodField()

    class Meta:
        model  = JobPosition
        fields = [
            "id", "name", "description",
            "is_active", "active_employee_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_active_employee_count(self, obj) -> int:
        return obj.get_active_employee_count()

    def validate(self, attrs):
        """Block deactivation if active employees exist (API-level guard)."""
        is_active = attrs.get("is_active")
        if is_active is False and self.instance and self.instance.pk:
            count = self.instance.get_active_employee_count()
            if count > 0:
                raise serializers.ValidationError(
                    "این پوزیشن دارای کارمندان فعال است و نمی‌توان آن را غیرفعال کرد."
                )
        return attrs


# ---------------------------------------------------------------------------
# Employee serializers
# ---------------------------------------------------------------------------

class EmployeeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for list views and dropdowns."""

    gender_display       = serializers.CharField(source="get_gender_display", read_only=True)
    job_position_name    = serializers.CharField(source="job_position.name",  read_only=True)

    class Meta:
        model  = Employee
        fields = [
            "id", "full_name", "national_id",
            "job_position", "job_position_name",
            "gender", "gender_display",
            "personal_phone", "email",
            "is_active", "start_date",
        ]


class EmployeeSerializer(serializers.ModelSerializer):
    """Full serializer — for create / retrieve / update views.

    Hourly-rate data is exposed two ways, deliberately never merged:
      - `legacy_hourly_rate` — the archived Employee.hourly_rate column,
        read-only, kept only so old HourlyWorkRecord rows stay interpretable.
      - `current_hourly_rate` / `future_hourly_rate` (+ their date fields) —
        computed from the canonical payroll.HourlyRate model, using real
        date comparisons against today (see HourlyRate.get_current_and_future).
        These are what any screen showing "current hourly rate" must read.
    """

    gender_display    = serializers.CharField(source="get_gender_display", read_only=True)
    job_position_name = serializers.CharField(source="job_position.name",  read_only=True)
    legacy_hourly_rate = serializers.DecimalField(
        source="hourly_rate", max_digits=14, decimal_places=2,
        read_only=True, allow_null=True,
    )
    current_hourly_rate            = serializers.SerializerMethodField(read_only=True)
    current_hourly_rate_start_date = serializers.SerializerMethodField(read_only=True)
    current_hourly_rate_end_date   = serializers.SerializerMethodField(read_only=True)
    future_hourly_rate             = serializers.SerializerMethodField(read_only=True)
    future_hourly_rate_start_date  = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = Employee
        fields = [
            "id",
            "full_name", "national_id", "gender", "gender_display",
            "job_position", "job_position_name",
            "start_date", "is_active",
            "email", "personal_phone", "emergency_contact_phone",
            "address", "description",
            "legacy_hourly_rate",
            "current_hourly_rate", "current_hourly_rate_start_date", "current_hourly_rate_end_date",
            "future_hourly_rate", "future_hourly_rate_start_date",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def _current_and_future_rate(self, obj):
        import datetime
        from payroll.models import HourlyRate
        if not hasattr(self, "_hourly_rate_cache"):
            self._hourly_rate_cache = {}
        if obj.pk not in self._hourly_rate_cache:
            self._hourly_rate_cache[obj.pk] = HourlyRate.get_current_and_future(
                obj.pk, datetime.date.today(),
            )
        return self._hourly_rate_cache[obj.pk]

    def get_current_hourly_rate(self, obj) -> 'str | None':
        current, _ = self._current_and_future_rate(obj)
        return str(current.rate) if current else None

    def get_current_hourly_rate_start_date(self, obj):
        current, _ = self._current_and_future_rate(obj)
        return current.start_date if current else None

    def get_current_hourly_rate_end_date(self, obj):
        current, _ = self._current_and_future_rate(obj)
        return current.end_date if current else None

    def get_future_hourly_rate(self, obj) -> 'str | None':
        _, future = self._current_and_future_rate(obj)
        return str(future.rate) if future else None

    def get_future_hourly_rate_start_date(self, obj):
        _, future = self._current_and_future_rate(obj)
        return future.start_date if future else None

    def validate_national_id(self, value):
        """Enforce uniqueness with a clear Persian error message."""
        qs = Employee.objects.filter(national_id=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "کارمندی با این کد ملی قبلاً ثبت شده است."
            )
        return value


# ---------------------------------------------------------------------------
# EmployeePurchaseCommission serializers
# ---------------------------------------------------------------------------

class EmployeePurchaseCommissionSerializer(serializers.ModelSerializer):
    employee_name   = serializers.CharField(source='employee.full_name', read_only=True)
    purchase_pk     = serializers.SerializerMethodField(read_only=True)
    purchase_ref    = serializers.SerializerMethodField(read_only=True)
    purchase_date   = serializers.SerializerMethodField(read_only=True)
    purchase_amount = serializers.SerializerMethodField(read_only=True)
    items_summary   = serializers.SerializerMethodField(read_only=True)
    vendor_name     = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = EmployeePurchaseCommission
        fields = [
            'id', 'employee', 'employee_name',
            'purchase', 'purchase_pk', 'purchase_ref',
            'purchase_date', 'purchase_amount', 'items_summary',
            'vendor_name',
            'amount', 'commission_date',
            'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_purchase_pk(self, obj) -> int | None:
        return obj.purchase_id

    def get_purchase_ref(self, obj) -> str | None:
        if not obj.purchase_id:
            return None
        try:
            p = obj.purchase
            return p.reference_number if p.reference_number else f'#{p.pk}'
        except Exception:
            return f'#{obj.purchase_id}'

    def get_purchase_date(self, obj) -> str | None:
        try:
            if obj.purchase and obj.purchase.purchase_date:
                d = obj.purchase.purchase_date
                return d.date().isoformat() if hasattr(d, 'date') else str(d)[:10]
        except Exception:
            pass
        return None

    def get_purchase_amount(self, obj) -> str | None:
        try:
            if obj.purchase:
                from decimal import Decimal
                items = list(obj.purchase.items.all())
                if not items:
                    return None
                total = sum(item.unit_price * item.quantity for item in items)
                return str(total.quantize(Decimal('1')))
        except Exception:
            pass
        return None

    def get_items_summary(self, obj) -> str | None:
        _PERSIAN = '۰۱۲۳۴۵۶۷۸۹'
        try:
            if obj.purchase:
                items = list(obj.purchase.items.select_related('product').all())
                if not items:
                    return None
                first_name = items[0].product.name
                if len(items) == 1:
                    return first_name
                rest = len(items) - 1
                rest_persian = ''.join(_PERSIAN[int(c)] for c in str(rest))
                return f'{first_name} + {rest_persian} قلم دیگر'
        except Exception:
            pass
        return None

    def get_vendor_name(self, obj) -> str | None:
        try:
            return obj.purchase.vendor.name if obj.purchase and obj.purchase.vendor else None
        except Exception:
            return None

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('مبلغ کمیسیون باید بزرگ‌تر از صفر باشد.')
        return value
