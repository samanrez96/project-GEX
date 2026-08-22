import re

from django.urls import reverse
from rest_framework import serializers

from accounts.permissions import is_main_administrator
from surgeries.models import Patient, Surgery, SurgeryConsumptionItem, SurgeryHistory, SurgeryStatus, SurgeryType, SurgeryUsedItem


# ---------------------------------------------------------------------------
# Patient serializers
# ---------------------------------------------------------------------------

def _drop_is_hidden_for_non_admin(serializer):
    """Remove ``is_hidden`` from a Patient serializer entirely (not just
    read-only) unless the requesting user is the main administrator — this
    is what actually stops a forged PATCH/POST from a non-superuser from
    ever reaching validated_data, not merely hiding the field in responses.
    """
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    if not is_main_administrator(user):
        serializer.fields.pop('is_hidden', None)


class PatientListSerializer(serializers.ModelSerializer):
    gender_display = serializers.CharField(source='get_gender_display', read_only=True, default=None)

    class Meta:
        model  = Patient
        fields = [
            'id', 'full_name', 'national_id', 'case_code', 'internal_code', 'phone_number',
            'age', 'gender', 'gender_display', 'marital_status', 'is_hidden', 'created_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _drop_is_hidden_for_non_admin(self)


class PatientSerializer(serializers.ModelSerializer):
    gender_display = serializers.CharField(source='get_gender_display', read_only=True, default=None)

    class Meta:
        model  = Patient
        fields = [
            'id', 'full_name', 'national_id', 'case_code', 'internal_code', 'phone_number',
            'age', 'gender', 'gender_display', 'marital_status',
            'description', 'is_hidden', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
        # Disable auto-generated UniqueValidator so our methods return a
        # contextual Persian message instead.
        extra_kwargs = {
            'case_code':     {'validators': []},
            'internal_code': {'validators': [], 'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _drop_is_hidden_for_non_admin(self)

    def validate_case_code(self, value):
        qs = Patient.objects.filter(case_code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "بیماری با این کد پرونده قبلاً ثبت شده است."
            )
        return value

    def validate_internal_code(self, value):
        # Blank means "not set" — normalize to None so it is stored as NULL
        # (never as an empty string) and never treated as a duplicate of
        # another blank code.
        if value is not None:
            value = value.strip() or None
        if value:
            qs = Patient.objects.filter(internal_code=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "کد داخلی بیمار باید یکتا باشد."
                )
        return value


# ---------------------------------------------------------------------------
# SurgeryType serializers
# ---------------------------------------------------------------------------

class SurgeryTypeListSerializer(serializers.ModelSerializer):
    """Lightweight — for list views and dropdowns."""

    class Meta:
        model  = SurgeryType
        fields = ['id', 'name', 'code', 'base_rate', 'is_active']


class SurgeryTypeSerializer(serializers.ModelSerializer):
    """Full serializer — create / retrieve / update."""

    active_commission_rule_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = SurgeryType
        fields = [
            'id', 'name', 'code', 'base_rate',
            'description', 'is_active',
            'active_commission_rule_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_active_commission_rule_count(self, obj) -> int:
        return obj.get_active_commission_rule_count()

    def validate_code(self, value):
        normalized = value.lower()
        if not re.match(r'^[a-z0-9_]+$', normalized):
            raise serializers.ValidationError(
                'کد باید فقط شامل حروف کوچک انگلیسی، اعداد و زیرخط باشد.'
            )
        return normalized

    def validate_base_rate(self, value):
        if value < 0:
            raise serializers.ValidationError('نرخ پایه نمی‌تواند منفی باشد.')
        return value


# ---------------------------------------------------------------------------
# Surgery / SurgeryConsumptionItem serializers
# ---------------------------------------------------------------------------

class SurgeryConsumptionItemSerializer(serializers.ModelSerializer):
    """Full serializer for surgery consumption line items."""

    product_name = serializers.CharField(source="product.name",         read_only=True)
    product_code = serializers.CharField(source="product.internal_code", read_only=True)

    class Meta:
        model  = SurgeryConsumptionItem
        fields = [
            "id",
            "surgery",
            "product", "product_name", "product_code",
            "quantity", "unit", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["unit", "created_at", "updated_at"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("مقدار باید بزرگ‌تر از صفر باشد.")
        return value

    def validate(self, attrs):
        """Prevent adding items to a completed or cancelled surgery."""
        surgery = attrs.get("surgery", getattr(self.instance, "surgery", None))
        if surgery and surgery.status in (
            SurgeryStatus.COMPLETED, SurgeryStatus.CANCELLED
        ):
            raise serializers.ValidationError(
                "اقلام مصرف عمل تکمیل‌شده یا لغو‌شده را نمی‌توان تغییر داد."
            )
        return attrs


class SurgeryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for list view."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    item_count     = serializers.IntegerField(
        source="consumption_items.count", read_only=True
    )

    class Meta:
        model  = Surgery
        fields = [
            "id", "patient_name", "surgeon_name",
            "surgery_date", "status", "status_display",
            "stock_applied", "item_count",
            "created_at",
        ]


class SurgerySerializer(serializers.ModelSerializer):
    """Full serializer — for create / retrieve / update views."""

    status_display    = serializers.CharField(source="get_status_display", read_only=True)
    consumption_items = SurgeryConsumptionItemSerializer(many=True, read_only=True)

    class Meta:
        model  = Surgery
        fields = [
            "id", "patient_name", "surgeon_name",
            "surgery_date", "status", "status_display",
            "notes", "stock_applied",
            "consumption_items",
            "created_at", "updated_at",
        ]
        read_only_fields = ["stock_applied", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# SurgeryHistory serializers
# ---------------------------------------------------------------------------

class SurgeryHistoryListSerializer(serializers.ModelSerializer):
    patient_name            = serializers.CharField(source='patient.full_name',       read_only=True)
    patient_national_id     = serializers.CharField(source='patient.national_id',     read_only=True, default='')
    patient_age             = serializers.IntegerField(source='patient.age',          read_only=True, default=None)
    patient_gender          = serializers.CharField(source='patient.gender',          read_only=True, default=None)
    patient_gender_display  = serializers.CharField(source='patient.get_gender_display', read_only=True, default=None)
    surgery_type_name       = serializers.CharField(source='surgery_type.name',       read_only=True)
    doctor_name             = serializers.CharField(source='clinical_doctor.full_name', read_only=True, default=None)
    status_display          = serializers.CharField(source='get_status_display',       read_only=True)
    payment_status_display  = serializers.CharField(source='get_payment_status_display', read_only=True)
    center_commission_income_amount = serializers.SerializerMethodField(read_only=True)
    university_share        = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    doctor_share            = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)

    class Meta:
        model  = SurgeryHistory
        fields = [
            'id', 'patient_name', 'patient_national_id',
            'patient_age', 'patient_gender', 'patient_gender_display',
            'case_code', 'medical_record_code', 'phone_number',
            'surgery_type_name', 'doctor_name',
            'surgery_date', 'amount',
            'university_share', 'doctor_share',
            'payment_status', 'payment_status_display',
            'status', 'status_display',
            'center_commission_income_amount',
            'description',
            'created_at',
        ]

    def get_center_commission_income_amount(self, obj) -> str | None:
        try:
            return str(obj.center_commission_income.amount)
        except Exception:
            return None


class SurgeryHistorySerializer(serializers.ModelSerializer):
    patient_name           = serializers.CharField(source='patient.full_name', read_only=True)
    surgery_type_name      = serializers.CharField(source='surgery_type.name', read_only=True)
    doctor_name            = serializers.CharField(source='clinical_doctor.full_name', read_only=True, default=None)
    status_display         = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    center_commission_income_amount = serializers.SerializerMethodField(read_only=True)

    # ── General-information roles (Task 2 detail-tab display) — names
    # only, never the raw FK id, per "do not display numeric ForeignKey
    # IDs to users".
    assistant_surgeon_name        = serializers.CharField(source='assistant_surgeon.full_name', read_only=True, default=None)
    second_assistant_surgeon_name = serializers.CharField(source='second_assistant_surgeon.full_name', read_only=True, default=None)
    scrub_employee_name           = serializers.CharField(source='scrub_employee.full_name', read_only=True, default=None)
    circulator_employee_name      = serializers.CharField(source='circulator_employee.full_name', read_only=True, default=None)
    anesthesiologist_name         = serializers.CharField(source='anesthesiologist.full_name', read_only=True, default=None)
    anesthesia_technician_name    = serializers.CharField(source='anesthesia_technician.full_name', read_only=True, default=None)
    anesthesia_type_name          = serializers.CharField(source='anesthesia_type.name', read_only=True, default=None)
    operating_room_manager_name   = serializers.CharField(source='operating_room_manager.full_name', read_only=True, default=None)
    service_employee_name         = serializers.CharField(source='service_employee.full_name', read_only=True, default=None)

    patient_age             = serializers.IntegerField(source='patient.age', read_only=True, default=None)
    patient_gender          = serializers.CharField(source='patient.gender', read_only=True, default=None)
    patient_gender_display  = serializers.CharField(source='patient.get_gender_display', read_only=True, default=None)
    patient_admin_url  = serializers.SerializerMethodField(read_only=True)
    previous_surgeries = serializers.SerializerMethodField(read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The auto-generated `patient` field otherwise validates against
        # Patient.objects.all() (unfiltered) — without this, a non-superuser
        # could still attach a hidden Patient to a *new* SurgeryHistory by
        # guessing its id, even though they can never see or select it
        # through search/autocomplete.
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if 'patient' in self.fields:
            self.fields['patient'].queryset = Patient.objects.visible_to(user)

    class Meta:
        model  = SurgeryHistory
        fields = [
            'id', 'patient', 'patient_name', 'patient_age', 'patient_gender', 'patient_gender_display', 'patient_admin_url',
            'case_code', 'medical_record_code', 'phone_number',
            'clinical_doctor', 'doctor_name',
            'assistant_surgeon_name', 'second_assistant_surgeon_name',
            'scrub_employee_name', 'circulator_employee_name',
            'anesthesiologist_name', 'anesthesia_technician_name',
            'anesthesia_type_name',
            'surgery_start_time', 'surgery_end_time',
            'operating_room_manager_name', 'service_employee_name',
            'postoperative_diagnosis', 'operation_description',
            'previous_surgeries',
            'surgery_type', 'surgery_type_name',
            'surgery_date', 'amount',
            'center_commission_percent', 'center_commission_amount',
            'center_commission_income_amount',
            'payment_status', 'payment_status_display',
            'description', 'status', 'status_display',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['case_code', 'phone_number', 'created_at', 'updated_at']

    def get_center_commission_income_amount(self, obj) -> str | None:
        try:
            return str(obj.center_commission_income.amount)
        except Exception:
            return None

    def get_patient_admin_url(self, obj) -> str | None:
        if not obj.patient_id:
            return None
        return reverse('admin:surgeries_patient_change', args=[obj.patient_id])

    def get_previous_surgeries(self, obj) -> list:
        others = (
            SurgeryHistory.objects
            .filter(patient_id=obj.patient_id)
            .exclude(pk=obj.pk)
            .select_related('surgery_type')
            .order_by('-surgery_date', '-created_at')
        )
        return [
            {
                'id': s.pk,
                'surgery_date': s.surgery_date,
                'surgery_type_name': s.surgery_type.name if s.surgery_type_id else None,
                'detail_url': reverse('admin:surgeries_surgeryhistory_detail', args=[s.pk]),
            }
            for s in others
        ]

    def validate_amount(self, value):
        if value < 0:
            raise serializers.ValidationError('مبلغ نمی‌تواند منفی باشد.')
        return value

    def validate_center_commission_percent(self, value):
        if value is not None and (value < 0 or value > 100):
            raise serializers.ValidationError('درصد کمیسیون مرکز باید بین ۰ تا ۱۰۰ باشد.')
        return value

    def validate_center_commission_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('مبلغ کمیسیون مرکز نمی‌تواند منفی باشد.')
        return value


# ---------------------------------------------------------------------------
# SurgeryUsedItem serializers
# ---------------------------------------------------------------------------

class SurgeryUsedItemSerializer(serializers.ModelSerializer):
    """product and quantity are fully editable — changing either one is
    reconciled against real stock by SurgeryInventoryService.adjust_consumption
    (called from SurgeryUsedItemViewSet.perform_update), which creates a
    compensating movement for the difference rather than touching the
    original OUT movement. Client-submitted fields that would let the
    frontend dictate stock impact directly (movement type/id, computed
    remaining stock, computed cost) are deliberately not accepted here —
    the backend alone decides them."""

    product_name         = serializers.CharField(source='product.name',                    read_only=True)
    product_code         = serializers.CharField(source='product.internal_code',            read_only=True)
    product_type         = serializers.CharField(source='product.product_type',             read_only=True)
    product_type_display = serializers.CharField(source='product.get_product_type_display', read_only=True)
    product_is_active    = serializers.BooleanField(source='product.is_active',              read_only=True)
    current_stock        = serializers.DecimalField(
        source='product.current_stock', max_digits=12, decimal_places=3, read_only=True,
    )

    class Meta:
        model  = SurgeryUsedItem
        fields = [
            'id', 'surgery',
            'product', 'product_name', 'product_code',
            'product_type', 'product_type_display', 'product_is_active',
            'quantity', 'unit', 'current_stock', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['unit', 'created_at', 'updated_at']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError('مقدار باید بزرگ‌تر از صفر باشد.')
        return value

    def validate(self, attrs):
        # Non-locking, user-facing early check — the authoritative check is
        # in Product._apply_stock_delta() via SELECT FOR UPDATE, run inside
        # SurgeryInventoryService (consume_product / adjust_consumption).
        product  = attrs.get('product',  getattr(self.instance, 'product',  None))
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', None))
        if not product or quantity is None:
            return attrs

        # Negative stock is intentionally allowed for surgery consumables.
        # The stock service remains the authoritative writer and keeps the
        # inventory audit trail intact.
        return attrs


# ---------------------------------------------------------------------------
# Surgery Profit Report serializers (CLI-53)
# ---------------------------------------------------------------------------

class SurgeryProfitReportSummarySerializer(serializers.Serializer):
    """Metadata and grand totals for the surgery profit report."""

    start_date                     = serializers.DateField(allow_null=True)
    end_date                       = serializers.DateField(allow_null=True)
    group_by                       = serializers.CharField()
    surgery_type_id                = serializers.IntegerField(allow_null=True)
    doctor_id                      = serializers.IntegerField(allow_null=True)
    patient_id                     = serializers.IntegerField(allow_null=True)
    status                         = serializers.CharField(allow_null=True)
    payment_status                 = serializers.CharField(allow_null=True)
    total_surgeries                = serializers.IntegerField()
    total_center_income            = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_consumed_items_cost      = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_employee_commission_cost = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_approximate_profit       = serializers.DecimalField(max_digits=20, decimal_places=2)
    average_profit_per_surgery     = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    profitable_surgeries_count     = serializers.IntegerField()
    loss_surgeries_count           = serializers.IntegerField()
    missing_cost_items_count       = serializers.IntegerField()


class SurgeryProfitReportRowSerializer(serializers.Serializer):
    """One row in the surgery profit report (shape depends on group_by).

    group_by=surgery:
        surgery_id, patient_name, case_code, phone_number, doctor_name,
        surgery_type_name, surgery_date, surgery_amount, payment_status,
        surgery_status, center_income, consumed_items_cost,
        employee_commission_cost, approximate_profit, profit_margin_percent,
        used_items_count, commission_transactions_count, has_missing_cost_data.

    group_by=surgery_type:
        surgery_type_id, surgery_type_name, surgeries_count,
        total_center_income, total_consumed_items_cost,
        total_employee_commission_cost, total_approximate_profit,
        average_profit_per_surgery, average_profit_margin_percent.

    group_by=doctor:
        doctor_id, doctor_name, surgeries_count, total_center_income,
        total_consumed_items_cost, total_employee_commission_cost,
        total_approximate_profit, average_profit_per_surgery.
    """

    # -- group_by=surgery: per-surgery identifier fields --
    surgery_id                    = serializers.IntegerField(required=False, allow_null=True)
    patient_name                  = serializers.CharField(required=False, allow_null=True)
    case_code                     = serializers.CharField(required=False, allow_null=True)
    phone_number                  = serializers.CharField(required=False, allow_null=True)
    doctor_name                   = serializers.CharField(required=False, allow_null=True)
    surgery_type_name             = serializers.CharField(required=False, allow_null=True)
    surgery_date                  = serializers.DateTimeField(required=False, allow_null=True)
    surgery_amount                = serializers.DecimalField(
                                        max_digits=14, decimal_places=2,
                                        required=False, allow_null=True)
    payment_status                = serializers.CharField(required=False, allow_null=True)
    surgery_status                = serializers.CharField(required=False, allow_null=True)
    used_items_count              = serializers.IntegerField(required=False, allow_null=True)
    commission_transactions_count = serializers.IntegerField(required=False, allow_null=True)
    has_missing_cost_data         = serializers.BooleanField(required=False, allow_null=True)
    # per-surgery financial fields
    center_income                 = serializers.DecimalField(
                                        max_digits=20, decimal_places=2,
                                        required=False, allow_null=True)
    consumed_items_cost           = serializers.DecimalField(
                                        max_digits=20, decimal_places=2,
                                        required=False, allow_null=True)
    employee_commission_cost      = serializers.DecimalField(
                                        max_digits=20, decimal_places=2,
                                        required=False, allow_null=True)
    approximate_profit            = serializers.DecimalField(
                                        max_digits=20, decimal_places=2,
                                        required=False, allow_null=True)
    profit_margin_percent         = serializers.DecimalField(
                                        max_digits=10, decimal_places=2,
                                        required=False, allow_null=True)

    # -- group_by=surgery_type --
    surgery_type_id               = serializers.IntegerField(required=False, allow_null=True)
    surgeries_count               = serializers.IntegerField(required=False, allow_null=True)
    average_profit_per_surgery    = serializers.DecimalField(
                                        max_digits=20, decimal_places=2,
                                        required=False, allow_null=True)
    average_profit_margin_percent = serializers.DecimalField(
                                        max_digits=10, decimal_places=2,
                                        required=False, allow_null=True)

    # -- group_by=doctor --
    doctor_id                      = serializers.IntegerField(required=False, allow_null=True)

    # -- group totals (surgery_type or doctor) --
    total_center_income            = serializers.DecimalField(
                                         max_digits=20, decimal_places=2,
                                         required=False, allow_null=True)
    total_consumed_items_cost      = serializers.DecimalField(
                                         max_digits=20, decimal_places=2,
                                         required=False, allow_null=True)
    total_employee_commission_cost = serializers.DecimalField(
                                         max_digits=20, decimal_places=2,
                                         required=False, allow_null=True)
    total_approximate_profit       = serializers.DecimalField(
                                         max_digits=20, decimal_places=2,
                                         required=False, allow_null=True)
