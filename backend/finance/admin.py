from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import path

from common.admin import DECIMAL_FORMFIELD_OVERRIDES, JALALI_FORMFIELD_OVERRIDES, JalaliAdminDatesMixin, MONEY_FORMFIELD_OVERRIDES, clean_decimal_display
from .models import CenterCommissionIncome, ExpenseCategory, FinanceCategory, IncomeCategory, Transaction


# ---------------------------------------------------------------------------
# Finance dashboard — custom admin view
# ---------------------------------------------------------------------------

def _fmt_toman(value):
    """Format a Decimal/float with Persian digits and Persian thousands separator."""
    _PERSIAN = '۰۱۲۳۴۵۶۷۸۹'
    from decimal import Decimal
    try:
        n = int(Decimal(str(value)).quantize(Decimal('1')))
        is_neg = n < 0
        raw = f'{abs(n):,}'.replace(',', '٬')
        persian = ''.join(_PERSIAN[int(c)] if c.isdigit() else c for c in raw)
        return ('-' + persian) if is_neg else persian
    except Exception:
        return '—'


@staff_member_required
def finance_dashboard_view(request):
    """Render the finance dashboard page — pre-computes summary server-side."""
    import json
    from finance.views import compute_finance_summary, compute_finance_trend

    summary = compute_finance_summary()
    trend = compute_finance_trend()

    context = {
        **admin.site.each_context(request),
        'title': 'داشبورد مالی',
        'ss_total_income': _fmt_toman(summary['total_income_period']),
        'ss_total_expense': _fmt_toman(summary['total_expense_period']),
        'ss_final_balance': _fmt_toman(summary['final_balance_cumulative']),
        'ss_total_employee_cost': _fmt_toman(summary['total_employee_cost_period']),
        'ss_total_equipment_cost': _fmt_toman(summary['total_equipment_cost_period']),
        'ss_total_medicine_cost': _fmt_toman(summary['total_medicine_cost_period']),
        'ss_center_commission_income': _fmt_toman(summary['center_commission_income_period']),
        'ss_university_commission': _fmt_toman(summary['university_commission_period']),
        'ss_anesthesia_cost': _fmt_toman(summary['anesthesia_cost_period']),
        'ss_daily_supplies_cost': _fmt_toman(summary['daily_supplies_cost_period']),
        'ss_is_negative': summary['final_balance_cumulative'] < 0,
        'ss_trend_json': json.dumps(trend),
    }
    return render(request, 'admin/finance/dashboard.html', context)


@staff_member_required
def finance_transactions_view(request):
    """Render the finance transactions page inside the Django admin shell."""
    context = {
        **admin.site.each_context(request),
        'title': 'تراکنش‌های مالی',
    }
    return render(request, 'admin/finance/transactions.html', context)


# ---------------------------------------------------------------------------
# Custom Admin Site (Standard approach, replacing monkey patching)
# ---------------------------------------------------------------------------

class FinanceAdminSite(admin.AdminSite):
    """Custom admin site to inject finance dashboard and transactions URLs."""

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'finance/dashboard/',
                self.admin_view(finance_dashboard_view),
                name='finance_dashboard',
            ),
            path(
                'finance/transactions/',
                self.admin_view(finance_transactions_view),
                name='finance_transactions',
            ),
        ]
        return custom + urls


# Replace the default admin site with our custom one
admin.site = FinanceAdminSite()


# ---------------------------------------------------------------------------
# ModelAdmins (Registered after assigning custom admin site)
# ---------------------------------------------------------------------------

@admin.register(CenterCommissionIncome)
class CenterCommissionIncomeAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display = ['surgery', 'get_amount_display', 'status', 'income_date_jalali', 'created_at_jalali']
    list_filter = ['status']
    search_fields = ['surgery__patient__full_name', 'description']
    readonly_fields = ['surgery', 'created_at_jalali', 'updated_at_jalali']
    ordering = ['-income_date']
    formfield_overrides = {**JALALI_FORMFIELD_OVERRIDES, **MONEY_FORMFIELD_OVERRIDES}

    @admin.display(description='مبلغ', ordering='amount')
    def get_amount_display(self, obj):
        return clean_decimal_display(obj.amount)

    fieldsets = (
        ('درآمد کمیسیون مرکز', {
            'fields': ('surgery', 'amount', 'status', 'income_date', 'description'),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )


@admin.register(FinanceCategory)
class FinanceCategoryAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display = ['name', 'slug', 'category_type', 'is_active', 'created_at_jalali']
    list_filter = ['category_type', 'is_active']
    search_fields = ['name', 'slug', 'description']
    ordering = ['category_type', 'name']
    readonly_fields = ['created_at_jalali', 'updated_at_jalali']
    prepopulated_fields = {'slug': ('name',)}  # اتوماتیک پر شدن slug از name
    fieldsets = (
        ('اطلاعات دسته‌بندی', {
            'fields': ('name', 'slug', 'category_type', 'description', 'is_active'),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at_jalali']
    list_filter = ['is_active']
    search_fields = ['name', 'slug', 'description']
    ordering = ['name']
    readonly_fields = ['created_at_jalali', 'updated_at_jalali']
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        ('اطلاعات دسته‌بندی هزینه', {
            'fields': ('name', 'slug', 'description', 'is_active'),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    def save_model(self, request, obj, form, change):
        obj.category_type = 'expense'
        super().save_model(request, obj, form, change)


@admin.register(IncomeCategory)
class IncomeCategoryAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at_jalali']
    list_filter = ['is_active']
    search_fields = ['name', 'slug', 'description']
    ordering = ['name']
    readonly_fields = ['created_at_jalali', 'updated_at_jalali']
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        ('اطلاعات دسته‌بندی درآمد', {
            'fields': ('name', 'slug', 'description', 'is_active'),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )

    def save_model(self, request, obj, form, change):
        obj.category_type = 'income'
        super().save_model(request, obj, form, change)


@admin.register(Transaction)
class TransactionAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display = ['pk', 'transaction_type', 'category', 'get_amount_display', 'transaction_date_jalali', 'payment_status', 'created_at_jalali']
    list_filter = ['transaction_type', 'payment_status', 'category']
    search_fields = ['description']
    ordering = ['-transaction_date']
    readonly_fields = ['created_at_jalali', 'updated_at_jalali']
    date_hierarchy = 'transaction_date'
    formfield_overrides = {**JALALI_FORMFIELD_OVERRIDES, **MONEY_FORMFIELD_OVERRIDES}

    @admin.display(description='مبلغ', ordering='amount')
    def get_amount_display(self, obj):
        return clean_decimal_display(obj.amount)

    fieldsets = (
        ('اطلاعات تراکنش', {
            'fields': ('transaction_type', 'category', 'amount', 'transaction_date', 'payment_status', 'description'),
        }),
        ('شیء مرتبط', {
            'fields': ('content_type', 'object_id'),
            'classes': ('collapse',),
        }),
        ('سیستم', {
            'fields': ('created_at_jalali', 'updated_at_jalali'),
            'classes': ('collapse',),
        }),
    )