"""Finance service layer."""

import datetime
from decimal import Decimal

from django.db import transaction as db_transaction

# ===================================================================
# SLUG CONSTANTS (سیستم دیگر به نام فارسی وابسته نیست)
# ===================================================================
SLUG_MEDICINE = 'medicine-cost'
SLUG_EQUIPMENT = 'equipment-cost'
SLUG_SALARY = 'employee-salary-cost'
SLUG_COMMISSION = 'employee-commission-cost'
SLUG_CENTER_COMMISSION = 'center-commission-income'
SLUG_ANESTHESIA = 'anesthesia-cost'
SLUG_DAILY_SUPPLIES = 'daily-supplies-cost'
SLUG_UNIVERSITY = 'university-commission-cost'
SLUG_DOCTOR_FEE = 'doctor-fee-expense'


class PurchaseFinanceService:
    MEDICINE_CATEGORY_SLUG = SLUG_MEDICINE
    EQUIPMENT_CATEGORY_SLUG = SLUG_EQUIPMENT

    @staticmethod
    def _get_or_create_category(slug: str, name: str):
        from finance.models import FinanceCategory
        obj, _ = FinanceCategory.objects.get_or_create(
            slug=slug,
            defaults={
                'name': name,
                'category_type': 'expense',
                'description': '',
                'is_active': True,
            }
        )
        return obj

    @classmethod
    @db_transaction.atomic
    def sync_purchase_expenses(cls, purchase) -> None:
        from django.contrib.contenttypes.models import ContentType
        from finance.models import (
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )
        from inventory.models import ProductType, PurchaseStatus

        purchase_ct = ContentType.objects.get_for_model(purchase)

        if purchase.status == PurchaseStatus.CANCELLED:
            Transaction.objects.filter(
                content_type=purchase_ct,
                object_id=purchase.pk,
                transaction_type=TransactionType.EXPENSE,
            ).exclude(
                payment_status=TransactionPaymentStatus.CANCELLED,
            ).update(payment_status=TransactionPaymentStatus.CANCELLED)
            return

        if purchase.status != PurchaseStatus.CONFIRMED:
            return

        items = purchase.items.select_related('product').all()
        totals: dict = {}
        for item in items:
            ptype = item.product.product_type
            line_total = item.effective_total
            totals[ptype] = totals.get(ptype, Decimal('0')) + line_total

        type_to_slug = {
            ProductType.MEDICINE: cls.MEDICINE_CATEGORY_SLUG,
            ProductType.EQUIPMENT: cls.EQUIPMENT_CATEGORY_SLUG,
        }
        type_to_name = {
            ProductType.MEDICINE: 'هزینه دارو',
            ProductType.EQUIPMENT: 'هزینه تجهیزات',
        }

        existing_by_cat: dict = {
            tx.category_id: tx
            for tx in Transaction.objects.filter(
                content_type=purchase_ct,
                object_id=purchase.pk,
                transaction_type=TransactionType.EXPENSE,
            ).select_related('category')
        }

        for ptype, total in totals.items():
            slug = type_to_slug.get(ptype)
            name = type_to_name.get(ptype)
            if slug is None or total <= 0:
                continue

            category = cls._get_or_create_category(slug, name)
            ref = purchase.reference_number
            description = (
                f"هزینه خرید #{purchase.pk}"
                + (f" ({ref})" if ref else "")
                + f" — {purchase.vendor.name}"
            )

            existing = existing_by_cat.get(category.pk)
            if existing:
                needs_update = (
                    existing.amount != total
                    or existing.payment_status == TransactionPaymentStatus.CANCELLED
                    or existing.description != description
                )
                if needs_update:
                    existing.amount = total
                    existing.payment_status = TransactionPaymentStatus.PENDING
                    existing.description = description
                    existing.transaction_date = purchase.purchase_date
                    existing.save(update_fields=[
                        'amount', 'payment_status', 'description',
                        'transaction_date', 'updated_at',
                    ])
            else:
                Transaction.objects.create(
                    transaction_type=TransactionType.EXPENSE,
                    category=category,
                    amount=total,
                    transaction_date=purchase.purchase_date,
                    description=description,
                    payment_status=TransactionPaymentStatus.PENDING,
                    content_type=purchase_ct,
                    object_id=purchase.pk,
                )


class PayrollFinanceService:
    SALARY_CATEGORY_SLUG = SLUG_SALARY
    COMMISSION_CATEGORY_SLUG = SLUG_COMMISSION

    @staticmethod
    def _get_expense_category(slug: str, name: str):
        from finance.models import FinanceCategory
        obj, _ = FinanceCategory.objects.get_or_create(
            slug=slug,
            defaults={
                'name': name,
                'category_type': 'expense',
                'description': '',
                'is_active': True,
            }
        )
        return obj

    @classmethod
    @db_transaction.atomic
    def sync_commission_expense(cls, commission_transaction) -> None:
        from django.contrib.contenttypes.models import ContentType
        from finance.models import (
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )

        ct = ContentType.objects.get_for_model(commission_transaction)
        existing = Transaction.objects.filter(
            content_type=ct,
            object_id=commission_transaction.pk,
        ).first()

        amount = commission_transaction.amount
        category = cls._get_expense_category(
            cls.COMMISSION_CATEGORY_SLUG,
            'کمیسیون کارمندان'
        )

        description = (
            f"کمیسیون #{commission_transaction.pk} — "
            f"{commission_transaction.employee.full_name} — "
            f"عمل #{commission_transaction.surgery_id}"
        )

        if amount <= 0:
            if existing and existing.payment_status != TransactionPaymentStatus.CANCELLED:
                existing.payment_status = TransactionPaymentStatus.CANCELLED
                existing.save(update_fields=['payment_status', 'updated_at'])
            return

        surgery_date = commission_transaction.surgery.surgery_date

        if existing:
            needs_update = (
                existing.amount != amount
                or existing.payment_status == TransactionPaymentStatus.CANCELLED
                or existing.description != description
            )
            if needs_update:
                existing.amount = amount
                existing.category = category
                existing.description = description
                existing.payment_status = TransactionPaymentStatus.PENDING
                existing.transaction_date = surgery_date
                existing.save(update_fields=[
                    'amount', 'category', 'description',
                    'payment_status', 'transaction_date', 'updated_at',
                ])
        else:
            Transaction.objects.create(
                transaction_type=TransactionType.EXPENSE,
                category=category,
                amount=amount,
                transaction_date=surgery_date,
                description=description,
                payment_status=TransactionPaymentStatus.PENDING,
                content_type=ct,
                object_id=commission_transaction.pk,
            )

    @classmethod
    @db_transaction.atomic
    def sync_salary_expenses(cls, period) -> None:
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Q
        from django.utils import timezone
        from finance.models import (
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )
        from payroll.models import (
            MonthlyWage,
            _jalali_days_in_month,
            _jalali_to_gregorian,
        )

        salary_cat = cls._get_expense_category(cls.SALARY_CATEGORY_SLUG, 'حقوق ثابت کارمندان')
        period_ct = ContentType.objects.get_for_model(period)

        last_day = _jalali_days_in_month(period.year, period.month)
        first_greg = datetime.date(*_jalali_to_gregorian(period.year, period.month, 1))
        last_greg = datetime.date(*_jalali_to_gregorian(period.year, period.month, last_day))

        active_wages = MonthlyWage.objects.filter(
            is_active=True,
            start_date__lte=last_greg,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=first_greg),
        ).select_related('employee')

        employee_totals: dict = {}
        employee_names: dict = {}
        for wage in active_wages:
            eid = wage.employee_id
            employee_totals[eid] = employee_totals.get(eid, Decimal('0')) + wage.amount
            employee_names[eid] = wage.employee.full_name

        trans_date = timezone.make_aware(
            datetime.datetime.combine(last_greg, datetime.time.min)
        )

        for emp_id, total in employee_totals.items():
            emp_name = employee_names[emp_id]
            marker = f'#emp:{emp_id}#'
            description = f"{marker} حقوق {period.year}/{period.month:02d} — {emp_name}"

            existing = Transaction.objects.filter(
                content_type=period_ct,
                object_id=period.pk,
                category=salary_cat,
                description__contains=marker,
            ).first()

            if existing:
                needs_update = (
                    existing.amount != total
                    or existing.payment_status == TransactionPaymentStatus.CANCELLED
                )
                if needs_update:
                    existing.amount = total
                    existing.payment_status = TransactionPaymentStatus.PENDING
                    existing.description = description
                    existing.save(update_fields=[
                        'amount', 'payment_status', 'description', 'updated_at',
                    ])
            else:
                Transaction.objects.create(
                    transaction_type=TransactionType.EXPENSE,
                    category=salary_cat,
                    amount=total,
                    transaction_date=trans_date,
                    description=description,
                    payment_status=TransactionPaymentStatus.PENDING,
                    content_type=period_ct,
                    object_id=period.pk,
                )

        # ساعت‌های کاری نیز در همین دسته‌بندی (حقوق ثابت) ثبت می‌شوند
        # پس نیازی به دسته‌بندی جداگانه نیست، اما تابع زیر برای مدیریت آن‌هاست
        cls._sync_hourly_expenses(period, period_ct, trans_date, salary_cat)

    @classmethod
    def _sync_hourly_expenses(cls, period, period_ct, trans_date, salary_cat) -> None:
        from django.core.exceptions import ValidationError
        from django.db.models import Sum
        from finance.models import Transaction, TransactionPaymentStatus, TransactionType
        from payroll.models import HourlyWorkEntry, PayrollTypeConfig
        from payroll.services import finalize_hourly_payroll

        employees = [
            cfg.employee for cfg in
            PayrollTypeConfig.objects.filter(has_hourly_wage=True).select_related('employee')
        ]

        for employee in employees:
            emp_id = employee.pk

            try:
                finalize_hourly_payroll(employee, period)
            except ValidationError:
                continue

            total = HourlyWorkEntry.objects.filter(
                employee=employee, payroll_period=period,
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            marker = f'#emp-hourly:{emp_id}:{period.pk}#'
            description = f'{marker} حقوق ساعتی {employee.full_name} - دوره {period.year}/{period.month:02d}'

            existing = Transaction.objects.filter(
                content_type=period_ct,
                object_id=period.pk,
                category=salary_cat,
                description__contains=marker,
            ).first()

            if total <= 0:
                if existing and existing.payment_status != TransactionPaymentStatus.CANCELLED:
                    existing.payment_status = TransactionPaymentStatus.CANCELLED
                    existing.save(update_fields=['payment_status', 'updated_at'])
                continue

            if existing:
                needs_update = (
                    existing.amount != total
                    or existing.payment_status == TransactionPaymentStatus.CANCELLED
                    or existing.description != description
                )
                if needs_update:
                    existing.amount = total
                    existing.payment_status = TransactionPaymentStatus.PENDING
                    existing.description = description
                    existing.save(update_fields=[
                        'amount', 'payment_status', 'description', 'updated_at',
                    ])
            else:
                Transaction.objects.create(
                    transaction_type=TransactionType.EXPENSE,
                    category=salary_cat,
                    amount=total,
                    transaction_date=trans_date,
                    description=description,
                    payment_status=TransactionPaymentStatus.PENDING,
                    content_type=period_ct,
                    object_id=period.pk,
                )


class DoctorFeeTransactionService:
    EXPENSE_CATEGORY_SLUG = SLUG_DOCTOR_FEE
    EXPENSE_CATEGORY_NAME = 'حق‌الزحمه پزشک از اعمال جراحی'

    @classmethod
    @db_transaction.atomic
    def sync_expense_transaction(cls, fee_expense) -> None:
        from django.contrib.contenttypes.models import ContentType
        from finance.models import (
            FinanceCategory,
            IncomeStatus,
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )

        ct = ContentType.objects.get_for_model(fee_expense)
        existing = Transaction.objects.filter(
            content_type=ct,
            object_id=fee_expense.pk,
        ).first()

        if fee_expense.status == IncomeStatus.CANCELLED:
            if existing and existing.payment_status != TransactionPaymentStatus.CANCELLED:
                existing.payment_status = TransactionPaymentStatus.CANCELLED
                existing.save(update_fields=['payment_status', 'updated_at'])
            return

        expense_cat, _ = FinanceCategory.objects.get_or_create(
            slug=cls.EXPENSE_CATEGORY_SLUG,
            defaults={
                'name': cls.EXPENSE_CATEGORY_NAME,
                'category_type': 'expense',
                'description': '',
                'is_active': True,
            }
        )

        description = (
            f"حق‌الزحمه پزشک — عمل #{fee_expense.surgery_id} — {fee_expense.doctor.full_name}"
        )
        amount = fee_expense.amount

        if existing:
            needs_update = (
                existing.amount != amount
                or existing.payment_status == TransactionPaymentStatus.CANCELLED
                or existing.transaction_date != fee_expense.fee_date
            )
            if needs_update:
                existing.amount = amount
                existing.category = expense_cat
                existing.description = description
                existing.payment_status = TransactionPaymentStatus.PENDING
                existing.transaction_date = fee_expense.fee_date
                existing.save(update_fields=[
                    'amount', 'category', 'description',
                    'payment_status', 'transaction_date', 'updated_at',
                ])
        else:
            Transaction.objects.create(
                transaction_type=TransactionType.EXPENSE,
                category=expense_cat,
                amount=amount,
                transaction_date=fee_expense.fee_date,
                description=description,
                payment_status=TransactionPaymentStatus.PENDING,
                content_type=ct,
                object_id=fee_expense.pk,
            )


class SurgeryCommissionTransactionService:
    INCOME_CATEGORY_SLUG = SLUG_CENTER_COMMISSION
    INCOME_CATEGORY_NAME = 'کمیسیون مرکز از اعمال جراحی'

    @classmethod
    @db_transaction.atomic
    def sync_income_transaction(cls, commission_income) -> None:
        from django.contrib.contenttypes.models import ContentType
        from finance.models import (
            FinanceCategory,
            IncomeStatus,
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )

        ct = ContentType.objects.get_for_model(commission_income)
        existing = Transaction.objects.filter(
            content_type=ct,
            object_id=commission_income.pk,
        ).first()

        income_cat, _ = FinanceCategory.objects.get_or_create(
            slug=cls.INCOME_CATEGORY_SLUG,
            defaults={
                'name': cls.INCOME_CATEGORY_NAME,
                'category_type': 'income',
                'description': '',
                'is_active': True,
            }
        )

        if commission_income.status == IncomeStatus.CANCELLED:
            if existing and existing.payment_status != TransactionPaymentStatus.CANCELLED:
                existing.payment_status = TransactionPaymentStatus.CANCELLED
                existing.save(update_fields=['payment_status', 'updated_at'])
            return

        surgery_desc = commission_income.description or ''
        description = (
            f"درآمد کمیسیون مرکز — عمل #{commission_income.surgery_id}"
            + (f" — {surgery_desc}" if surgery_desc else "")
        )
        amount = commission_income.amount

        if existing:
            needs_update = (
                existing.amount != amount
                or existing.payment_status == TransactionPaymentStatus.CANCELLED
                or existing.transaction_date != commission_income.income_date
            )
            if needs_update:
                existing.amount = amount
                existing.description = description
                existing.payment_status = TransactionPaymentStatus.PAID
                existing.transaction_date = commission_income.income_date
                existing.save(update_fields=[
                    'amount', 'description', 'payment_status',
                    'transaction_date', 'updated_at',
                ])
        else:
            Transaction.objects.create(
                transaction_type=TransactionType.INCOME,
                category=income_cat,
                amount=amount,
                transaction_date=commission_income.income_date,
                description=description,
                payment_status=TransactionPaymentStatus.PAID,
                content_type=ct,
                object_id=commission_income.pk,
            )


class UniversityCommissionService:
    CATEGORY_SLUG = SLUG_UNIVERSITY
    CATEGORY_NAME = 'هزینه سهم دانشگاه'

    @classmethod
    @db_transaction.atomic
    def sync_transaction(cls, surgery) -> None:
        from django.conf import settings
        from django.contrib.contenttypes.models import ContentType
        from finance.models import (
            FinanceCategory,
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )

        percent = Decimal(getattr(settings, 'UNIVERSITY_COMMISSION_PERCENT', 45))
        amount = (surgery.amount * percent / 100).quantize(Decimal('1'))

        ct = ContentType.objects.get_for_model(surgery)
        cat, _ = FinanceCategory.objects.get_or_create(
            slug=cls.CATEGORY_SLUG,
            defaults={
                'name': cls.CATEGORY_NAME,
                'category_type': 'expense',
                'description': 'سهم دانشگاه از درآمد جراحی',
                'is_active': True,
            }
        )

        existing = Transaction.objects.filter(
            content_type=ct,
            object_id=surgery.pk,
            category=cat,
        ).first()

        if surgery.status == 'CANCELLED':
            if existing and existing.payment_status != TransactionPaymentStatus.CANCELLED:
                existing.payment_status = TransactionPaymentStatus.CANCELLED
                existing.save(update_fields=['payment_status', 'updated_at'])
            return

        if amount <= 0:
            if existing and existing.payment_status != TransactionPaymentStatus.CANCELLED:
                existing.payment_status = TransactionPaymentStatus.CANCELLED
                existing.save(update_fields=['payment_status', 'updated_at'])
            return

        defaults = {
            'transaction_type': TransactionType.EXPENSE,
            'category': cat,
            'amount': amount,
            'transaction_date': surgery.surgery_date,
            'description': f'سهم دانشگاه از عمل #{surgery.pk}',
            'payment_status': TransactionPaymentStatus.PENDING,
            'content_type': ct,
            'object_id': surgery.pk,
        }

        if existing:
            for k, v in defaults.items():
                setattr(existing, k, v)
            existing.save()
        else:
            Transaction.objects.create(**defaults)