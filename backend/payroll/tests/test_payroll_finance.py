"""Tests: automatic expense Transaction creation from payroll events.

Covers:
  - fixed salary creates finance expense when period is closed
  - employee commission creates finance expense
  - recalculation of period updates existing expense (no duplicate)
  - expenses are linked to employee and payroll period
  - employee total cost can be aggregated from finance records
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from employees.models import Employee, JobPosition
from finance.models import (
    FinanceCategory,
    Transaction,
    TransactionPaymentStatus,
    TransactionType,
)
from payroll.models import (
    CommissionRule,
    CommissionTransaction,
    MonthlyWage,
    PayrollPeriod,
    PayrollStatus,
    _gregorian_to_jalali,
)
from surgeries.models import Patient, SurgeryHistory, SurgeryType

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(name='پزشک'):
    obj, _ = JobPosition.objects.get_or_create(name=name)
    return obj


def make_employee(position=None, **kwargs):
    import uuid
    if position is None:
        position = make_position()
    defaults = {
        'full_name':    f'کارمند {uuid.uuid4().hex[:6]}',
        'national_id':  uuid.uuid4().hex[:10],
        'job_position': position,
        'start_date':   datetime.date(2020, 1, 1),
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_surgery_type(name='عمومی'):
    code = name.lower().replace(' ', '_')
    obj, _ = SurgeryType.objects.get_or_create(
        name=name,
        defaults={'code': code, 'base_rate': Decimal('0')},
    )
    return obj


def make_patient():
    import uuid
    code = uuid.uuid4().hex[:10]
    return Patient.objects.create(full_name='بیمار تست', case_code=code)


def make_surgery(patient=None, doctor=None, surgery_type=None, amount=Decimal('1000000')):
    if patient is None:
        patient = make_patient()
    if surgery_type is None:
        surgery_type = make_surgery_type()
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        doctor_or_therapist=doctor,
        surgery_date=timezone.now(),
        amount=amount,
    )


def make_period(year=None, month=None):
    today = datetime.date.today()
    jy, jm, _ = _gregorian_to_jalali(today.year, today.month, today.day)
    return PayrollPeriod.objects.get_or_create(
        year=year or jy,
        month=month or jm,
        defaults={'status': PayrollStatus.OPEN},
    )[0]


def commission_expense_for(commission_tx):
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(commission_tx)
    return Transaction.objects.filter(
        content_type=ct,
        object_id=commission_tx.pk,
        transaction_type=TransactionType.EXPENSE,
    )


def salary_expenses_for(period):
    from django.contrib.contenttypes.models import ContentType
    ct      = ContentType.objects.get_for_model(period)
    sal_cat = FinanceCategory.objects.filter(name='حقوق ثابت کارمندان', category_type='expense').first()
    if not sal_cat:
        return Transaction.objects.none()
    return Transaction.objects.filter(
        content_type=ct,
        object_id=period.pk,
        category=sal_cat,
        transaction_type=TransactionType.EXPENSE,
    )


# ---------------------------------------------------------------------------
# Commission expense tests
# ---------------------------------------------------------------------------

class CommissionFinanceExpenseTest(TestCase):

    def setUp(self):
        self.position     = make_position('جراح')
        self.surgery_type = make_surgery_type('قلب')
        self.employee     = make_employee(position=self.position)
        self.user         = User.objects.create_superuser('paytest_admin', password='pass')

        self.rule = CommissionRule.objects.create(
            job_position=self.position,
            surgery_type=self.surgery_type,
            commission_percent=Decimal('10.00'),
            start_date=datetime.date(2020, 1, 1),
            created_by=self.user,
        )

    def test_commission_transaction_creates_expense(self):
        """Creating a CommissionTransaction must create an expense Transaction."""
        surgery = make_surgery(doctor=self.employee, surgery_type=self.surgery_type,
                               amount=Decimal('2000000'))

        # The signal auto_calculate_commission fires on surgery save
        commission = CommissionTransaction.objects.filter(
            surgery=surgery, employee=self.employee,
        ).first()
        self.assertIsNotNone(commission)

        txs = commission_expense_for(commission)
        self.assertEqual(txs.count(), 1)

        tx = txs.first()
        self.assertEqual(tx.transaction_type, TransactionType.EXPENSE)
        self.assertEqual(tx.amount, commission.amount)
        self.assertEqual(tx.category.name, 'کمیسیون کارمندان')
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PENDING)

    def test_commission_expense_amount_matches_commission(self):
        """Expense amount must equal commission_percent × surgery.amount / 100."""
        surgery = make_surgery(doctor=self.employee, surgery_type=self.surgery_type,
                               amount=Decimal('1000000'))

        commission = CommissionTransaction.objects.filter(surgery=surgery).first()
        expected_amount = (Decimal('1000000') * Decimal('10') / Decimal('100')).quantize(Decimal('0.01'))
        self.assertEqual(commission.amount, expected_amount)

        tx = commission_expense_for(commission).first()
        self.assertEqual(tx.amount, expected_amount)

    def test_no_duplicate_commission_expense(self):
        """Saving CommissionTransaction again must not create a duplicate expense."""
        surgery = make_surgery(doctor=self.employee, surgery_type=self.surgery_type)
        commission = CommissionTransaction.objects.filter(surgery=surgery).first()

        # Force another save to trigger signal
        commission.save()

        txs = commission_expense_for(commission)
        self.assertEqual(txs.count(), 1)

    def test_commission_expense_linked_to_employee_via_commission(self):
        """The expense Transaction links to CommissionTransaction which links to employee."""
        from django.contrib.contenttypes.models import ContentType

        surgery    = make_surgery(doctor=self.employee, surgery_type=self.surgery_type)
        commission = CommissionTransaction.objects.filter(surgery=surgery).first()
        tx         = commission_expense_for(commission).first()

        ct = ContentType.objects.get_for_model(commission)
        self.assertEqual(tx.content_type, ct)
        self.assertEqual(tx.object_id, commission.pk)
        self.assertEqual(tx.related_object.employee, self.employee)

    def test_no_expense_when_no_commission_rule(self):
        """If no CommissionRule exists, no CommissionTransaction and no expense."""
        position2      = make_position('پرستار')
        employee2      = make_employee(position=position2)
        surgery_type2  = make_surgery_type('ارتوپدی')
        surgery        = make_surgery(doctor=employee2, surgery_type=surgery_type2)

        self.assertEqual(
            CommissionTransaction.objects.filter(surgery=surgery).count(), 0
        )

    def test_manual_commission_transaction_creates_expense(self):
        """Directly created CommissionTransaction must also produce an expense."""
        surgery = make_surgery(surgery_type=self.surgery_type)

        ct = CommissionTransaction.objects.create(
            surgery=surgery,
            employee=self.employee,
            commission_rule=self.rule,
            amount=Decimal('50000'),
        )

        txs = commission_expense_for(ct)
        self.assertEqual(txs.count(), 1)
        self.assertEqual(txs.first().amount, Decimal('50000'))


# ---------------------------------------------------------------------------
# Salary expense tests
# ---------------------------------------------------------------------------

class SalaryFinanceExpenseTest(TestCase):

    def setUp(self):
        self.position = make_position('مدیر')
        self.user     = User.objects.create_superuser('salary_admin', password='pass')

    def test_closing_period_creates_salary_expenses(self):
        """Closing a PayrollPeriod must create salary expense Transactions."""
        employee = make_employee(position=self.position)
        MonthlyWage.objects.create(
            employee=employee,
            amount=Decimal('5000000'),
            start_date=datetime.date(2020, 1, 1),
            created_by=self.user,
        )

        period = make_period()
        period.close()

        txs = salary_expenses_for(period)
        self.assertGreaterEqual(txs.count(), 1)

        # Find the one for our employee
        marker = f'#emp:{employee.pk}#'
        tx = txs.filter(description__contains=marker).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('5000000'))
        self.assertEqual(tx.category.name, 'حقوق ثابت کارمندان')

    def test_salary_expense_linked_to_payroll_period(self):
        """Salary expense Transaction must be linked to PayrollPeriod via GFK."""
        from django.contrib.contenttypes.models import ContentType

        employee = make_employee(position=self.position)
        MonthlyWage.objects.create(
            employee=employee,
            amount=Decimal('3000000'),
            start_date=datetime.date(2020, 1, 1),
            created_by=self.user,
        )

        period = make_period()
        period.close()

        marker = f'#emp:{employee.pk}#'
        tx     = salary_expenses_for(period).filter(description__contains=marker).first()

        period_ct = ContentType.objects.get_for_model(period)
        self.assertEqual(tx.content_type, period_ct)
        self.assertEqual(tx.object_id, period.pk)

    def test_reclosing_period_updates_existing_salary_expense(self):
        """Re-processing a period must update existing salary expense, not duplicate."""
        employee = make_employee(position=self.position)
        wage = MonthlyWage.objects.create(
            employee=employee,
            amount=Decimal('4000000'),
            start_date=datetime.date(2020, 1, 1),
            created_by=self.user,
        )

        # Use a unique period
        import uuid
        period = PayrollPeriod.objects.create(
            year=1400, month=1, status=PayrollStatus.OPEN
        )

        # Close → creates salary expense
        period.close()
        txs_after_first_close = salary_expenses_for(period)
        count_after_first = txs_after_first_close.count()
        self.assertGreaterEqual(count_after_first, 1)

        # Simulate re-syncing by directly calling the service again
        from finance.services import PayrollFinanceService
        PayrollFinanceService.sync_salary_expenses(period)

        # Count must not have grown
        txs_after_second = salary_expenses_for(period)
        self.assertEqual(txs_after_second.count(), count_after_first)

    def test_multiple_employees_get_separate_salary_expenses(self):
        """Each active employee must get their own salary expense Transaction."""
        emp1 = make_employee(position=self.position)
        emp2 = make_employee(position=self.position)

        for emp in (emp1, emp2):
            MonthlyWage.objects.create(
                employee=emp,
                amount=Decimal('2000000'),
                start_date=datetime.date(2020, 1, 1),
                created_by=self.user,
            )

        period = PayrollPeriod.objects.create(year=1400, month=2, status=PayrollStatus.OPEN)
        period.close()

        txs = salary_expenses_for(period)
        markers = [f'#emp:{emp1.pk}#', f'#emp:{emp2.pk}#']
        for marker in markers:
            self.assertTrue(txs.filter(description__contains=marker).exists(),
                            f"No salary expense found for {marker}")


# ---------------------------------------------------------------------------
# Aggregation test
# ---------------------------------------------------------------------------

class EmployeeCostAggregationTest(TestCase):

    def test_total_employee_cost_aggregates_salary_and_commission(self):
        """Finance records from salary + commission must be aggregatable together."""
        from django.db.models import Sum

        position     = make_position('کارشناس')
        surgery_type = make_surgery_type('چشم')
        employee     = make_employee(position=position)
        user         = User.objects.create_superuser('agg_admin', password='pass')

        MonthlyWage.objects.create(
            employee=employee,
            amount=Decimal('3000000'),
            start_date=datetime.date(2020, 1, 1),
            created_by=user,
        )

        rule = CommissionRule.objects.create(
            job_position=position,
            surgery_type=surgery_type,
            commission_percent=Decimal('5'),
            start_date=datetime.date(2020, 1, 1),
            created_by=user,
        )

        surgery = make_surgery(doctor=employee, surgery_type=surgery_type,
                               amount=Decimal('1000000'))

        period = PayrollPeriod.objects.create(year=1400, month=3, status=PayrollStatus.OPEN)
        period.close()

        cat_names = ['حقوق ثابت کارمندان', 'کمیسیون کارمندان']
        cat_ids   = list(
            FinanceCategory.objects.filter(name__in=cat_names, category_type='expense')
            .values_list('pk', flat=True)
        )

        total = Transaction.objects.filter(
            transaction_type=TransactionType.EXPENSE,
            category_id__in=cat_ids,
        ).exclude(
            payment_status=TransactionPaymentStatus.CANCELLED,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # At minimum: salary 3,000,000 + commission 50,000
        self.assertGreaterEqual(total, Decimal('3050000'))
