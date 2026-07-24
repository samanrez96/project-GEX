from decimal import Decimal

from rest_framework import serializers

from finance.models import FinanceCategory, Transaction


class BalanceReportSerializer(serializers.Serializer):
    """Read-only serializer for the balance report response."""

    total_income             = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_expense            = serializers.DecimalField(max_digits=20, decimal_places=2)
    final_balance            = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_employee_cost      = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_equipment_cost     = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_medicine_cost      = serializers.DecimalField(max_digits=20, decimal_places=2)
    center_commission_income = serializers.DecimalField(max_digits=20, decimal_places=2)
    university_commission    = serializers.DecimalField(max_digits=20, decimal_places=0)
    anesthesia_cost          = serializers.DecimalField(max_digits=20, decimal_places=2)
    daily_supplies_cost      = serializers.DecimalField(max_digits=20, decimal_places=2)


class FinanceCategorySerializer(serializers.ModelSerializer):
    category_type_display = serializers.CharField(source='get_category_type_display', read_only=True)

    class Meta:
        model = FinanceCategory
        fields = [
            'id', 'name', 'category_type', 'category_type_display',
            'description', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class TransactionListSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    payment_status_display   = serializers.CharField(source='get_payment_status_display', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)

    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_type', 'transaction_type_display',
            'category', 'category_name', 'amount', 'transaction_date',
            'payment_status', 'payment_status_display',
        ]


class TransactionSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    payment_status_display   = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_type', 'transaction_type_display',
            'category', 'amount', 'transaction_date',
            'description', 'payment_status', 'payment_status_display',
            'content_type', 'object_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        amount = attrs.get('amount')
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({'amount': 'مبلغ باید بزرگ‌تر از صفر باشد.'})
        category = attrs.get('category')
        transaction_type = attrs.get('transaction_type')
        if category and transaction_type and category.category_type != transaction_type:
            raise serializers.ValidationError({'category': 'دسته‌بندی باید با نوع تراکنش مطابقت داشته باشد.'})
        return attrs
