"""Balance report edge-case tests (CLI-63).

Covers gaps not present in the existing finance/tests.py BalanceReportAPITest:
- PAID transactions are INCLUDED in totals (only CANCELLED is excluded)
- PARTIAL transactions are INCLUDED in totals
- end_date boundary is inclusive (transaction on the exact end_date is counted)
- Transaction before start_date boundary is excluded
- Decimal precision is preserved (amounts with cents)

NOT duplicated from finance/tests.py:
  - Empty result returns zeros  ✅
  - CANCELLED excluded  ✅
  - Income/expense/balance calculation  ✅
  - Year/month filter  ✅
  - Date range start filter  ✅
"""

from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import (
    CategoryType,
    FinanceCategory,
    Transaction,
    TransactionPaymentStatus,
    TransactionType,
)

BALANCE_URL = '/api/v2/finance/reports/balance/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_make_category(name, cat_type):
    obj, _ = FinanceCategory.objects.get_or_create(
        name=name, category_type=cat_type,
        defaults={'is_active': True},
    )
    return obj


def _make_tx(category, amount, date_str, payment_status=TransactionPaymentStatus.PENDING):
    return Transaction.objects.create(
        transaction_type=category.category_type,
        category=category,
        amount=Decimal(str(amount)),
        transaction_date=parse_datetime(date_str),
        payment_status=payment_status,
    )


# ---------------------------------------------------------------------------
# Payment status inclusion/exclusion
# ---------------------------------------------------------------------------

class BalanceReportPaymentStatusTest(APITestCase):
    """Verify which payment statuses are included or excluded from totals.

    Rule: all statuses EXCEPT 'cancelled' are included in balance totals.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='br_pstatus', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)
        self.income_cat = _get_or_make_category(
            'کمیسیون مرکز از اعمال جراحی', CategoryType.INCOME
        )

    def _get_balance(self):
        resp = self.client.get(BALANCE_URL, {
            'start_date': '2028-01-01',
            'end_date':   '2028-12-31',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return Decimal(str(resp.data['total_income']))

    def _tx(self, pstatus):
        return _make_tx(
            self.income_cat, '400000',
            '2028-06-15T10:00:00Z',
            payment_status=pstatus,
        )

    def test_pending_transaction_included(self):
        """PENDING transactions must be included (control case)."""
        self._tx(TransactionPaymentStatus.PENDING)
        total = self._get_balance()
        self.assertGreaterEqual(total, Decimal('400000'))

    def test_paid_transaction_included(self):
        """PAID transactions must be included in totals."""
        self._tx(TransactionPaymentStatus.PAID)
        total = self._get_balance()
        self.assertGreaterEqual(total, Decimal('400000'))

    def test_partial_transaction_included(self):
        """PARTIAL transactions must be included in totals."""
        self._tx(TransactionPaymentStatus.PARTIAL)
        total = self._get_balance()
        self.assertGreaterEqual(total, Decimal('400000'))

    def test_cancelled_transaction_excluded(self):
        """CANCELLED transactions must be excluded (already tested, regression guard)."""
        self._tx(TransactionPaymentStatus.CANCELLED)
        total = self._get_balance()
        self.assertEqual(total, Decimal('0'))

    def test_mix_cancelled_and_paid_correct_total(self):
        """Only the CANCELLED one should be excluded; PAID should be counted."""
        self._tx(TransactionPaymentStatus.PAID)       # 400,000 — included
        self._tx(TransactionPaymentStatus.CANCELLED)   # 400,000 — excluded
        total = self._get_balance()
        # Exactly one payment of 400,000 should be in the total
        self.assertEqual(total, Decimal('400000'))


# ---------------------------------------------------------------------------
# Date boundary precision
# ---------------------------------------------------------------------------

class BalanceReportDateBoundaryTest(APITestCase):
    """Verify that date range filters are inclusive at both ends."""

    def setUp(self):
        self.user = User.objects.create_user(username='br_boundary', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)
        self.expense_cat = _get_or_make_category('هزینه دارو', CategoryType.EXPENSE)

    def _get_expense(self, start, end):
        resp = self.client.get(BALANCE_URL, {
            'start_date': start,
            'end_date':   end,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return Decimal(str(resp.data['total_expense']))

    def test_transaction_on_start_date_included(self):
        """A transaction with its date on start_date must be included."""
        # Use noon UTC — avoids timezone edge cases near midnight
        _make_tx(self.expense_cat, '111000', '2029-04-01T12:00:00Z')
        total = self._get_expense('2029-04-01', '2029-04-30')
        self.assertGreaterEqual(total, Decimal('111000'))

    def test_transaction_on_end_date_included(self):
        """A transaction with its date on end_date must be included."""
        _make_tx(self.expense_cat, '222000', '2029-04-30T12:00:00Z')
        total = self._get_expense('2029-04-01', '2029-04-30')
        self.assertGreaterEqual(total, Decimal('222000'))

    def test_transaction_well_before_start_date_excluded(self):
        """A transaction from a week before start_date must be excluded."""
        _make_tx(self.expense_cat, '333000', '2029-03-24T12:00:00Z')  # March 24
        total = self._get_expense('2029-04-01', '2029-04-30')
        self.assertEqual(total, Decimal('0'))

    def test_transaction_well_after_end_date_excluded(self):
        """A transaction from a week after end_date must be excluded."""
        _make_tx(self.expense_cat, '444000', '2029-05-07T12:00:00Z')  # May 7
        total = self._get_expense('2029-04-01', '2029-04-30')
        self.assertEqual(total, Decimal('0'))


# ---------------------------------------------------------------------------
# Decimal precision
# ---------------------------------------------------------------------------

class BalanceReportDecimalPrecisionTest(APITestCase):
    """Verify that centesimal (2-decimal) amounts are preserved correctly."""

    def setUp(self):
        self.user = User.objects.create_user(username='br_decimal', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)
        self.income_cat  = _get_or_make_category('کمیسیون مرکز از اعمال جراحی', CategoryType.INCOME)
        self.expense_cat = _get_or_make_category('هزینه دارو', CategoryType.EXPENSE)

    def test_income_with_cents_preserved(self):
        """Amounts like 1,234,567.89 must not lose the cents."""
        _make_tx(self.income_cat, '1234567.89', '2030-01-15T10:00:00Z')
        resp = self.client.get(BALANCE_URL, {
            'start_date': '2030-01-01',
            'end_date':   '2030-01-31',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        total = Decimal(str(resp.data['total_income']))
        self.assertEqual(total, Decimal('1234567.89'))

    def test_final_balance_decimal_precision(self):
        """final_balance = income - expense must preserve decimal precision."""
        _make_tx(self.income_cat,  '1000000.50', '2030-02-15T10:00:00Z')
        _make_tx(self.expense_cat, '999999.75',  '2030-02-15T10:00:00Z')
        resp = self.client.get(BALANCE_URL, {
            'start_date': '2030-02-01',
            'end_date':   '2030-02-28',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        income  = Decimal(str(resp.data['total_income']))
        expense = Decimal(str(resp.data['total_expense']))
        balance = Decimal(str(resp.data['final_balance']))
        # Verify precision exactly
        self.assertEqual(income,  Decimal('1000000.50'))
        self.assertEqual(expense, Decimal('999999.75'))
        self.assertEqual(balance, Decimal('0.75'))

    def test_multiple_small_amounts_sum_correctly(self):
        """Sum of many small amounts must add up without floating-point error."""
        for _ in range(5):
            _make_tx(self.income_cat, '100000.33', '2030-03-15T10:00:00Z')
        resp = self.client.get(BALANCE_URL, {
            'start_date': '2030-03-01',
            'end_date':   '2030-03-31',
        })
        total = Decimal(str(resp.data['total_income']))
        expected = Decimal('100000.33') * 5  # 500,001.65
        self.assertEqual(total, expected)
