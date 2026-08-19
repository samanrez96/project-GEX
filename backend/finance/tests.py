from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import CategoryType, FinanceCategory, Transaction, TransactionPaymentStatus, TransactionType

User = get_user_model()
CATEGORIES_URL = '/api/v1/finance/categories/'
TRANSACTIONS_URL = '/api/v1/finance/transactions/'


def make_category(**kwargs):
    defaults = {
        'name': 'کمیسیون مرکز',
        'category_type': CategoryType.INCOME,
    }
    defaults.update(kwargs)
    return FinanceCategory.objects.create(**defaults)


def make_transaction(category=None, **kwargs):
    if category is None:
        category = make_category()
    defaults = {
        'transaction_type': category.category_type,
        'category': category,
        'amount': Decimal('1000000'),
        'transaction_date': timezone.now(),
    }
    defaults.update(kwargs)
    return Transaction.objects.create(**defaults)


class FinanceCategoryModelTest(TestCase):

    def test_create(self):
        cat = make_category()
        self.assertIsNotNone(cat.pk)
        self.assertTrue(cat.is_active)

    def test_str(self):
        cat = make_category(name='درآمد آزمایشی', category_type=CategoryType.INCOME)
        self.assertIn('درآمد آزمایشی', str(cat))

    def test_unique_name_per_type(self):
        make_category(name='تست', category_type=CategoryType.INCOME)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_category(name='تست', category_type=CategoryType.INCOME)


class TransactionModelTest(TestCase):

    def test_create(self):
        tx = make_transaction()
        self.assertIsNotNone(tx.pk)
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PENDING)

    def test_amount_zero_raises(self):
        tx = make_transaction(amount=Decimal('0'))
        with self.assertRaises(ValidationError):
            tx.clean()

    def test_amount_negative_raises(self):
        tx = make_transaction(amount=Decimal('-100'))
        with self.assertRaises(ValidationError):
            tx.clean()

    def test_category_type_mismatch_raises(self):
        income_cat = make_category(name='درآمد', category_type=CategoryType.INCOME)
        tx = make_transaction(category=income_cat, transaction_type=TransactionType.EXPENSE)
        with self.assertRaises(ValidationError):
            tx.clean()


class FinanceCategoryAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='finance_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_list(self):
        make_category()
        resp = self.client.get(CATEGORIES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create(self):
        payload = {'name': 'درآمد تست جدید', 'category_type': 'income'}
        resp = self.client.post(CATEGORIES_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_filter_by_type(self):
        before = self.client.get(CATEGORIES_URL, {'category_type': 'expense'}).data
        before_count = before.get('count', len(before))
        make_category(name='درآمد تست', category_type=CategoryType.INCOME)
        make_category(name='هزینه تست', category_type=CategoryType.EXPENSE)
        resp = self.client.get(CATEGORIES_URL, {'category_type': 'expense'})
        after_count = resp.data.get('count', len(resp.data))
        self.assertEqual(after_count, before_count + 1)

    def test_unauthenticated_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(CATEGORIES_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TransactionAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='tx_user', password='pass')
        self.client.force_authenticate(user=self.user)
        self.income_cat = make_category(name='درآمد', category_type=CategoryType.INCOME)

    def test_list(self):
        resp = self.client.get(TRANSACTIONS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create(self):
        payload = {
            'transaction_type': 'income',
            'category': self.income_cat.pk,
            'amount': '500000',
            'transaction_date': '2026-01-15T10:00:00Z',
        }
        resp = self.client.post(TRANSACTIONS_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_invalid_amount(self):
        payload = {
            'transaction_type': 'income',
            'category': self.income_cat.pk,
            'amount': '-100',
            'transaction_date': '2026-01-15T10:00:00Z',
        }
        resp = self.client.post(TRANSACTIONS_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ExpenseCategoryTest(TestCase):

    def test_expense_category_proxy_only_shows_expenses(self):
        from finance.models import ExpenseCategory
        before = ExpenseCategory.objects.count()
        make_category(name='هزینه دارو جدید', category_type=CategoryType.EXPENSE)
        make_category(name='درآمد تست', category_type=CategoryType.INCOME)
        self.assertEqual(ExpenseCategory.objects.count(), before + 1)

    def test_expense_category_create_sets_type(self):
        from finance.models import ExpenseCategory
        cat = ExpenseCategory.objects.create(name='تجهیزات آزمایشی')
        self.assertEqual(cat.category_type, 'expense')


class IncomeCategoryTest(TestCase):

    def test_income_category_proxy_only_shows_income(self):
        from finance.models import IncomeCategory
        before = IncomeCategory.objects.count()
        make_category(name='کمیسیون مرکز', category_type=CategoryType.INCOME)
        make_category(name='هزینه دارو جدید تست', category_type=CategoryType.EXPENSE)
        self.assertEqual(IncomeCategory.objects.count(), before + 1)

    def test_income_category_create_sets_type(self):
        from finance.models import IncomeCategory
        cat = IncomeCategory.objects.create(name='درآمد آزمایشی')
        self.assertEqual(cat.category_type, 'income')

    def test_default_income_categories_seeded(self):
        from finance.models import IncomeCategory
        self.assertTrue(
            IncomeCategory.objects.filter(name='کمیسیون مرکز از اعمال جراحی').exists()
        )


BALANCE_URL = '/api/v1/finance/reports/balance/'
TREND_URL   = '/api/v1/finance/reports/trend/'


class BalanceReportAPITest(APITestCase):

    def _get_cat(self, name, cat_type):
        obj, _ = FinanceCategory.objects.get_or_create(
            name=name, category_type=cat_type,
            defaults={'is_active': True},
        )
        return obj

    def setUp(self):
        from django.contrib.auth.models import Group
        self.user = User.objects.create_user(username='balance_user', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

        self.income_cat  = self._get_cat('کمیسیون مرکز از اعمال جراحی', CategoryType.INCOME)
        self.expense_cat = self._get_cat('هزینه دارو',                   CategoryType.EXPENSE)
        self.salary_cat  = self._get_cat('حقوق ثابت کارمندان',          CategoryType.EXPENSE)
        self.comm_cat    = self._get_cat('کمیسیون کارمندان',            CategoryType.EXPENSE)
        self.equip_cat   = self._get_cat('هزینه تجهیزات',              CategoryType.EXPENSE)

    def _make_tx(self, tx_type, category, amount, date_str='2026-03-01T10:00:00Z'):
        from django.utils.dateparse import parse_datetime
        return Transaction.objects.create(
            transaction_type=tx_type,
            category=category,
            amount=Decimal(amount),
            transaction_date=parse_datetime(date_str),
        )

    def test_balance_report_returns_200(self):
        resp = self.client.get(BALANCE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(BALANCE_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_empty_result_returns_zeros(self):
        resp = self.client.get(BALANCE_URL, {'start_date': '2099-01-01', 'end_date': '2099-01-31'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data
        for field in ('total_income', 'total_expense', 'final_balance',
                      'total_employee_cost', 'total_equipment_cost',
                      'total_medicine_cost', 'center_commission_income'):
            self.assertEqual(Decimal(str(data[field])), Decimal('0'), field)

    def test_total_income_calculation(self):
        self._make_tx(TransactionType.INCOME, self.income_cat, '500000')
        self._make_tx(TransactionType.INCOME, self.income_cat, '300000')
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertGreaterEqual(Decimal(str(resp.data['total_income'])), Decimal('800000'))

    def test_total_expense_calculation(self):
        self._make_tx(TransactionType.EXPENSE, self.expense_cat, '200000')
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertGreaterEqual(Decimal(str(resp.data['total_expense'])), Decimal('200000'))

    def test_final_balance_is_income_minus_expense(self):
        self._make_tx(TransactionType.INCOME,  self.income_cat,  '1000000')
        self._make_tx(TransactionType.EXPENSE, self.expense_cat, '400000')
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        income  = Decimal(str(resp.data['total_income']))
        expense = Decimal(str(resp.data['total_expense']))
        balance = Decimal(str(resp.data['final_balance']))
        self.assertEqual(balance, income - expense)

    def test_medicine_cost_aggregation(self):
        self._make_tx(TransactionType.EXPENSE, self.expense_cat, '150000')
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertGreaterEqual(Decimal(str(resp.data['total_medicine_cost'])), Decimal('150000'))

    def test_equipment_cost_aggregation(self):
        self._make_tx(TransactionType.EXPENSE, self.equip_cat, '250000')
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertGreaterEqual(Decimal(str(resp.data['total_equipment_cost'])), Decimal('250000'))

    def test_employee_cost_aggregation(self):
        self._make_tx(TransactionType.EXPENSE, self.salary_cat, '3000000')
        self._make_tx(TransactionType.EXPENSE, self.comm_cat,   '100000')
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertGreaterEqual(Decimal(str(resp.data['total_employee_cost'])), Decimal('3100000'))

    def test_center_commission_income_aggregation(self):
        self._make_tx(TransactionType.INCOME, self.income_cat, '700000')
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertGreaterEqual(Decimal(str(resp.data['center_commission_income'])), Decimal('700000'))

    def test_date_range_filter_start(self):
        self._make_tx(TransactionType.INCOME, self.income_cat, '100000', '2025-01-15T10:00:00Z')
        # With start_date after 2025, this tx should be excluded
        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        # The old transaction should NOT appear in 2026 filter
        # (no transactions in 2026 were added in this test)
        data = resp.data
        # total_income for 2026 should be 0 from this test
        self.assertEqual(Decimal(str(data['total_income'])), Decimal('0'))

    def test_cancelled_transactions_excluded(self):
        """CANCELLED transactions must not appear in the totals."""
        tx = self._make_tx(TransactionType.INCOME, self.income_cat, '500000')
        tx.payment_status = TransactionPaymentStatus.CANCELLED
        tx.save()

        resp = self.client.get(BALANCE_URL, {'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        self.assertEqual(Decimal(str(resp.data['total_income'])), Decimal('0'))

    def test_year_filter(self):
        self._make_tx(TransactionType.INCOME, self.income_cat, '888888', '2027-06-01T10:00:00Z')
        resp = self.client.get(BALANCE_URL, {'year': '2027'})
        self.assertGreaterEqual(Decimal(str(resp.data['total_income'])), Decimal('888888'))

    def test_month_filter(self):
        self._make_tx(TransactionType.EXPENSE, self.expense_cat, '123456', '2026-05-15T10:00:00Z')
        resp = self.client.get(BALANCE_URL, {'year': '2026', 'month': '5'})
        self.assertGreaterEqual(Decimal(str(resp.data['total_expense'])), Decimal('123456'))


class FinanceTrendAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='trend_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_trend_returns_200(self):
        resp = self.client.get(TREND_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_trend_unauthenticated_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(TREND_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_trend_returns_list(self):
        resp = self.client.get(TREND_URL)
        self.assertIsInstance(resp.data, list)
