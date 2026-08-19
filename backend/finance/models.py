from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class IncomeStatus(models.TextChoices):
    CONFIRMED = 'CONFIRMED', 'تأیید شده'
    CANCELLED = 'CANCELLED', 'لغو شده'


class CenterCommissionIncome(models.Model):
    surgery = models.OneToOneField(
        'surgeries.SurgeryHistory',
        on_delete=models.CASCADE,
        related_name='center_commission_income',
        verbose_name='عمل جراحی',
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='مبلغ درآمد',
    )
    status = models.CharField(
        max_length=10,
        choices=IncomeStatus.choices,
        default=IncomeStatus.CONFIRMED,
        verbose_name='وضعیت',
    )
    description = models.TextField(blank=True, default='', verbose_name='توضیحات')
    income_date = models.DateTimeField(verbose_name='تاریخ درآمد')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'درآمد کمیسیون مرکز'
        verbose_name_plural = 'درآمدهای کمیسیون مرکز'
        ordering = ['-income_date', '-created_at']
        indexes = [
            models.Index(fields=['surgery'], name='idx_cci_surgery'),
            models.Index(fields=['status'], name='idx_cci_status'),
            models.Index(fields=['income_date'], name='idx_cci_income_date'),
        ]

    def __str__(self) -> str:
        return f'کمیسیون مرکز #{self.pk} — {self.amount:,} تومان ({self.status})'


class DoctorFeeExpense(models.Model):
    surgery = models.OneToOneField(
        'surgeries.SurgeryHistory',
        on_delete=models.CASCADE,
        related_name='doctor_fee_expense',
        verbose_name='عمل جراحی',
    )
    doctor = models.ForeignKey(
        'contacts.Doctor',
        on_delete=models.PROTECT,
        related_name='fee_expenses',
        verbose_name='پزشک',
    )
    surgery_type = models.ForeignKey(
        'surgeries.SurgeryType',
        on_delete=models.PROTECT,
        related_name='doctor_fee_expenses',
        verbose_name='نوع عمل',
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name='مبلغ حق‌الزحمه',
    )
    status = models.CharField(
        max_length=10,
        choices=IncomeStatus.choices,
        default=IncomeStatus.CONFIRMED,
        verbose_name='وضعیت',
    )
    description = models.TextField(blank=True, default='', verbose_name='توضیحات')
    fee_date = models.DateTimeField(verbose_name='تاریخ محاسبه')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'حق‌الزحمه پزشک'
        verbose_name_plural = 'حق‌الزحمه‌های پزشکان'
        ordering = ['-fee_date', '-created_at']
        indexes = [
            models.Index(fields=['surgery'], name='idx_dfe_surgery'),
            models.Index(fields=['doctor'], name='idx_dfe_doctor'),
            models.Index(fields=['status'], name='idx_dfe_status'),
        ]

    def __str__(self) -> str:
        return f'حق‌الزحمه #{self.pk} — {self.amount:,} تومان ({self.status})'


class CategoryType(models.TextChoices):
    INCOME = 'income', 'درآمد'
    EXPENSE = 'expense', 'هزینه'


class FinanceCategory(models.Model):
    name = models.CharField(max_length=200, verbose_name='نام دسته‌بندی')
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name='شناسه یکتا (Slug)',
        help_text='کد یکتا برای استفاده در محاسبات سیستمی (مثلاً medicine-cost)'
    )
    category_type = models.CharField(
        max_length=10,
        choices=CategoryType.choices,
        verbose_name='نوع دسته‌بندی',
    )
    description = models.TextField(blank=True, default='', verbose_name='توضیحات')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'دسته‌بندی مالی'
        verbose_name_plural = 'دسته‌بندی‌های مالی'
        ordering = ['category_type', 'name']
        unique_together = [['name', 'category_type']]
        indexes = [
            models.Index(fields=['category_type'], name='idx_fc_category_type'),
            models.Index(fields=['is_active'], name='idx_fc_is_active'),
            models.Index(fields=['slug'], name='idx_fc_slug'),
        ]

    def __str__(self) -> str:
        return f'{self.get_category_type_display()} — {self.name}'

    def __repr__(self) -> str:
        return f'<FinanceCategory pk={self.pk} slug={self.slug} type={self.category_type}>'


class TransactionType(models.TextChoices):
    INCOME = 'income', 'درآمد'
    EXPENSE = 'expense', 'هزینه'


class TransactionPaymentStatus(models.TextChoices):
    PENDING = 'pending', 'در انتظار پرداخت'
    PARTIAL = 'partial', 'پرداخت ناقص'
    PAID = 'paid', 'پرداخت شده'
    CANCELLED = 'cancelled', 'لغو شده'


class Transaction(models.Model):
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
        verbose_name='نوع تراکنش',
    )
    category = models.ForeignKey(
        FinanceCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transactions',
        verbose_name='دسته‌بندی',
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='مبلغ',
        help_text='مبلغ باید بزرگ‌تر از صفر باشد.',
    )
    transaction_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='تاریخ تراکنش',
    )
    description = models.TextField(blank=True, default='', verbose_name='توضیحات')
    payment_status = models.CharField(
        max_length=10,
        choices=TransactionPaymentStatus.choices,
        default=TransactionPaymentStatus.PENDING,
        verbose_name='وضعیت پرداخت',
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='نوع شیء مرتبط',
    )
    object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='شناسه شیء مرتبط')
    related_object = GenericForeignKey('content_type', 'object_id')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'تراکنش مالی'
        verbose_name_plural = 'تراکنش‌های مالی'
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['transaction_type'], name='idx_tx_type'),
            models.Index(fields=['transaction_date'], name='idx_tx_date'),
            models.Index(fields=['payment_status'], name='idx_tx_payment_status'),
            models.Index(fields=['category'], name='idx_tx_category'),
            models.Index(fields=['content_type', 'object_id'], name='idx_tx_gfk'),
        ]

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'مبلغ باید بزرگ‌تر از صفر باشد.'})
        if self.category and self.transaction_type and self.category.category_type != self.transaction_type:
            raise ValidationError({'category': 'دسته‌بندی باید با نوع تراکنش مطابقت داشته باشد.'})

    def __str__(self) -> str:
        date_str = self.transaction_date.strftime('%Y-%m-%d') if self.transaction_date else '—'
        return f'{self.get_transaction_type_display()} #{self.pk} — {self.amount:,.0f} ({date_str})'


class ExpenseCategoryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category_type=CategoryType.EXPENSE)

    def create(self, **kwargs):
        kwargs.setdefault('category_type', CategoryType.EXPENSE)
        return super().create(**kwargs)


class ExpenseCategory(FinanceCategory):
    objects = ExpenseCategoryManager()

    class Meta:
        proxy = True
        verbose_name = 'دسته‌بندی هزینه'
        verbose_name_plural = 'دسته‌بندی‌های هزینه'


class IncomeCategoryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category_type=CategoryType.INCOME)

    def create(self, **kwargs):
        kwargs.setdefault('category_type', CategoryType.INCOME)
        return super().create(**kwargs)


class IncomeCategory(FinanceCategory):
    objects = IncomeCategoryManager()

    class Meta:
        proxy = True
        verbose_name = 'دسته‌بندی درآمد'
        verbose_name_plural = 'دسته‌بندی‌های درآمد'