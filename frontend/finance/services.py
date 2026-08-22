"""Finance service layer.

PurchaseFinanceService         — expense Transaction sync when a Purchase is confirmed/cancelled.
PayrollFinanceService          — expense Transaction sync for commission and salary events.
SurgeryCommissionTransactionService — income Transaction sync from CenterCommissionIncome.
"""

import datetime
from decimal import Decimal

from django.db import transaction as db_transaction


class PurchaseFinanceService:
    """Manages expense Transactions that mirror confirmed Purchase records.

    One Transaction per (purchase, product_type) combination.
    Linked to the Purchase via GenericForeignKey (content_type + object_id).

    Category mapping:
      medicine  → 'هزینه دارو'
      equipment → 'هزینه تجهیزات'
    """

    MEDICINE_CATEGORY_NAME  = 'هزینه دارو'
    EQUIPMENT_CATEGORY_NAME = 'هزینه تجهیزات'

    @staticmethod
    def _get_or_create_category(name: str):
        from finance.models import FinanceCategory
        obj, _ = FinanceCategory.objects.get_or_create(
            name=name,
            category_type='expense',
            defaults={'description': '', 'is_active': True},
        )
        return obj

    @classmethod
    @db_transaction.atomic
    def sync_purchase_expenses(cls, purchase) -> None:
        """Create or update expense Transactions for a confirmed purchase.

        Groups PurchaseItems by product_type and creates one Transaction per
        type that has a positive total.

        Idempotent — calling multiple times produces the same result.

        When purchase.status == CANCELLED: marks existing expense Transactions
        as CANCELLED instead of deleting them (preserves audit history).
        When purchase.status == PENDING:  does nothing (not yet finalised).
        """
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

        # Compute totals grouped by product_type
        items = purchase.items.select_related('product').all()
        totals: dict = {}
        for item in items:
            ptype = item.product.product_type
            line_total = item.effective_total
            totals[ptype] = totals.get(ptype, Decimal('0')) + line_total

        type_to_cat_name = {
            ProductType.MEDICINE:  cls.MEDICINE_CATEGORY_NAME,
            ProductType.EQUIPMENT: cls.EQUIPMENT_CATEGORY_NAME,
        }

        # Build index of existing expense Transactions for this purchase
        existing_by_cat: dict = {
            tx.category_id: tx
            for tx in Transaction.objects.filter(
                content_type=purchase_ct,
                object_id=purchase.pk,
                transaction_type=TransactionType.EXPENSE,
            ).select_related('category')
        }

        for ptype, total in totals.items():
            cat_name = type_to_cat_name.get(ptype)
            if cat_name is None or total <= 0:
                continue

            category = cls._get_or_create_category(cat_name)
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
                    existing.amount          = total
                    existing.payment_status  = TransactionPaymentStatus.PENDING
                    existing.description     = description
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
    """Manages expense Transactions for payroll events.

    Commission expense: one Transaction per CommissionTransaction, linked via GFK.
    Salary expense:     one Transaction per (employee, period), linked to
                        PayrollPeriod via GFK; employee is identified by a
                        structured marker in description (#emp:<id>#).
    """

    SALARY_CATEGORY_NAME     = 'حقوق ثابت کارمندان'
    COMMISSION_CATEGORY_NAME = 'کمیسیون کارمندان'
    HOURLY_CATEGORY_NAME     = SALARY_CATEGORY_NAME

    @staticmethod
    def _get_expense_category(name: str):
        from finance.models import FinanceCategory
        obj, _ = FinanceCategory.objects.get_or_create(
            name=name,
            category_type='expense',
            defaults={'description': '', 'is_active': True},
        )
        return obj

    @classmethod
    @db_transaction.atomic
    def sync_commission_expense(cls, commission_transaction) -> None:
        """Create or update an expense Transaction for a CommissionTransaction.

        Linked to CommissionTransaction via GenericForeignKey.
        Idempotent.
        """
        from django.contrib.contenttypes.models import ContentType

        from finance.models import (
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )

        ct       = ContentType.objects.get_for_model(commission_transaction)
        existing = Transaction.objects.filter(
            content_type=ct,
            object_id=commission_transaction.pk,
        ).first()

        amount   = commission_transaction.amount
        category = cls._get_expense_category(cls.COMMISSION_CATEGORY_NAME)

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
                existing.amount           = amount
                existing.category         = category
                existing.description      = description
                existing.payment_status   = TransactionPaymentStatus.PENDING
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
        """Create or update salary expense Transactions for a PayrollPeriod.

        One Transaction per employee active during the period, linked to the
        PayrollPeriod via GenericForeignKey.  The employee is identified by a
        structured marker in the description field (#emp:<id>#) so that
        multiple employees can share the same content_type/object_id pair.

        Idempotent — safe to call multiple times (e.g. if a period is
        re-processed after corrections).
        """
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

        salary_cat = cls._get_expense_category(cls.SALARY_CATEGORY_NAME)
        period_ct  = ContentType.objects.get_for_model(period)

        last_day   = _jalali_days_in_month(period.year, period.month)
        first_greg = datetime.date(*_jalali_to_gregorian(period.year, period.month, 1))
        last_greg  = datetime.date(*_jalali_to_gregorian(period.year, period.month, last_day))

        active_wages = MonthlyWage.objects.filter(
            is_active=True,
            start_date__lte=last_greg,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=first_greg),
        ).select_related('employee')

        # Aggregate per employee (employee may have multiple wage records)
        employee_totals: dict = {}
        employee_names: dict  = {}
        for wage in active_wages:
            eid = wage.employee_id
            employee_totals[eid] = employee_totals.get(eid, Decimal('0')) + wage.amount
            employee_names[eid]  = wage.employee.full_name

        trans_date = timezone.make_aware(
            datetime.datetime.combine(last_greg, datetime.time.min)
        )

        for emp_id, total in employee_totals.items():
            emp_name = employee_names[emp_id]
            marker      = f'#emp:{emp_id}#'
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
                    existing.amount         = total
                    existing.payment_status = TransactionPaymentStatus.PENDING
                    existing.description    = description
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

        cls._sync_hourly_expenses(period, period_ct, trans_date)

    @classmethod
    def _sync_hourly_expenses(cls, period, period_ct, trans_date) -> None:
        """Create/update one expense Transaction per employee for hourly
        payroll earned inside `period`.

        Reuses the same expense category as fixed salary (per project
        convention: one "employee payroll" expense bucket) but keeps its own
        marker (#emp-hourly:<employee_id>:<payroll_period_id>#, embedding
        both ids explicitly rather than relying only on the GFK's object_id
        to disambiguate periods) so the fixed-salary and hourly-salary
        Transactions for the same employee/period stay independently
        updatable — e.g. adding more work entries later and re-closing the
        period only touches that one period's hourly Transaction, never
        another period's.

        Pricing and marking HourlyWorkEntry rows as processed is delegated to
        payroll.services.finalize_hourly_payroll — this is the only place
        that function is ever called, since this method itself only runs
        from the PayrollPeriod CLOSED/PROCESSED signal (see
        payroll.signals.sync_salary_finance_expenses). Nothing in a GET
        request, report, or preview API call may finalize entries.
        """
        from django.core.exceptions import ValidationError
        from django.db.models import Sum

        from finance.models import Transaction, TransactionPaymentStatus, TransactionType
        from payroll.models import HourlyWorkEntry, PayrollTypeConfig
        from payroll.services import finalize_hourly_payroll

        hourly_cat = cls._get_expense_category(cls.HOURLY_CATEGORY_NAME)

        employees = [
            cfg.employee for cfg in
            PayrollTypeConfig.objects.filter(has_hourly_wage=True).select_related('employee')
        ]

        for employee in employees:
            emp_id = employee.pk

            try:
                # Processes any not-yet-processed entries in `period` — its
                # return value is only THAT incremental batch, not the
                # period's running total (an already-processed entry from an
                # earlier sync is excluded from what it prices), so the
                # actual Transaction amount is read back from all processed
                # entries below rather than from this return value directly.
                finalize_hourly_payroll(employee, period)
            except ValidationError:
                # No effective rate for some in-range entry — skip this
                # employee's hourly sync rather than failing the whole
                # period close; the entries stay unprocessed until the
                # missing rate is configured and the period is re-closed.
                continue

            total = HourlyWorkEntry.objects.filter(
                employee=employee, payroll_period=period,
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            # Embeds both employee AND period id explicitly — the GFK
            # (content_type/object_id) already scopes the query to this one
            # period, but the marker alone must also be an unambiguous,
            # self-contained (employee, period) key: relying on object_id
            # alone would silently break if this method were ever called
            # without that filter (e.g. a future cross-period lookup/report).
            marker      = f'#emp-hourly:{emp_id}:{period.pk}#'
            description = f'{marker} حقوق ساعتی {employee.full_name} - دوره {period.year}/{period.month:02d}'

            existing = Transaction.objects.filter(
                content_type=period_ct,
                object_id=period.pk,
                category=hourly_cat,
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
                    existing.amount          = total
                    existing.payment_status  = TransactionPaymentStatus.PENDING
                    existing.description     = description
                    existing.save(update_fields=[
                        'amount', 'payment_status', 'description', 'updated_at',
                    ])
            else:
                Transaction.objects.create(
                    transaction_type=TransactionType.EXPENSE,
                    category=hourly_cat,
                    amount=total,
                    transaction_date=trans_date,
                    description=description,
                    payment_status=TransactionPaymentStatus.PENDING,
                    content_type=period_ct,
                    object_id=period.pk,
                )


class DoctorFeeTransactionService:
    """Manages expense Transactions that mirror DoctorFeeExpense records.

    One Transaction per DoctorFeeExpense, linked via GenericForeignKey.
    Status mirrors the DoctorFeeExpense status:
      CONFIRMED → Transaction payment_status = PENDING (owed, not yet paid —
                  matches PayrollFinanceService.sync_commission_expense's
                  convention for personnel-fee expenses)
      CANCELLED → Transaction payment_status = CANCELLED
    """

    EXPENSE_CATEGORY_NAME = 'حق‌الزحمه پزشک از اعمال جراحی'

    @classmethod
    @db_transaction.atomic
    def sync_expense_transaction(cls, fee_expense) -> None:
        """Create or update a finance Transaction for a DoctorFeeExpense.

        Linked to the DoctorFeeExpense via GenericForeignKey. Idempotent.
        """
        from django.contrib.contenttypes.models import ContentType

        from finance.models import (
            FinanceCategory,
            IncomeStatus,
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )

        ct       = ContentType.objects.get_for_model(fee_expense)
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
            name=cls.EXPENSE_CATEGORY_NAME,
            category_type='expense',
            defaults={'description': '', 'is_active': True},
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
                existing.amount           = amount
                existing.category         = expense_cat
                existing.description      = description
                existing.payment_status   = TransactionPaymentStatus.PENDING
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
    """Manages income Transactions that mirror CenterCommissionIncome records.

    One Transaction per CenterCommissionIncome, linked via GenericForeignKey.
    Status mirrors the CenterCommissionIncome status:
      CONFIRMED → Transaction payment_status = PAID
      CANCELLED → Transaction payment_status = CANCELLED
    """

    INCOME_CATEGORY_NAME = 'کمیسیون مرکز از اعمال جراحی'

    @classmethod
    @db_transaction.atomic
    def sync_income_transaction(cls, commission_income) -> None:
        """Create or update a finance Transaction for a CenterCommissionIncome.

        Linked to the CenterCommissionIncome via GenericForeignKey.
        Idempotent.
        """
        from django.contrib.contenttypes.models import ContentType

        from finance.models import (
            FinanceCategory,
            IncomeStatus,
            Transaction,
            TransactionPaymentStatus,
            TransactionType,
        )

        ct       = ContentType.objects.get_for_model(commission_income)
        existing = Transaction.objects.filter(
            content_type=ct,
            object_id=commission_income.pk,
        ).first()

        income_cat, _ = FinanceCategory.objects.get_or_create(
            name=cls.INCOME_CATEGORY_NAME,
            category_type='income',
            defaults={'description': '', 'is_active': True},
        )

        if commission_income.status == IncomeStatus.CANCELLED:
            if existing and existing.payment_status != TransactionPaymentStatus.CANCELLED:
                existing.payment_status = TransactionPaymentStatus.CANCELLED
                existing.save(update_fields=['payment_status', 'updated_at'])
            return

        # Status is CONFIRMED
        surgery_desc = commission_income.description or ''
        description  = (
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
                existing.amount           = amount
                existing.description      = description
                existing.payment_status   = TransactionPaymentStatus.PAID
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
