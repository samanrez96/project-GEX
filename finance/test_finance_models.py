"""Finance model unit tests (CLI-63).

Covers gaps not present in the existing finance/tests.py:
- Transaction.__str__ is meaningful
- Transaction.description field stored correctly
- Transaction.transaction_date stored correctly
- Transaction.payment_status values: PAID, PARTIAL, CANCELLED
- Persian message content in clean() validation (not just "raises")
- CenterCommissionIncome model: create, __str__, status values, fields

NOT duplicated from finance/tests.py:
  - FinanceCategoryModelTest  ✅
  - TransactionModelTest (create, zero/negative raise, type-mismatch raise)  ✅
  - ExpenseCategoryTest, IncomeCategoryTest  ✅
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from finance.models import (
    CategoryType,
    CenterCommissionIncome,
    FinanceCategory,
    IncomeStatus,
    Transaction,
    TransactionPaymentStatus,
    TransactionType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid = 0


def _uid_str():
    global _uid
    _uid += 1
    return str(_uid).zfill(5)


def _income_cat(name=None):
    uid = _uid_str()
    cat, _ = FinanceCategory.objects.get_or_create(
        name=name or f'درآمد تست {uid}',
        category_type=CategoryType.INCOME,
    )
    return cat


def _expense_cat(name=None):
    uid = _uid_str()
    cat, _ = FinanceCategory.objects.get_or_create(
        name=name or f'هزینه تست {uid}',
        category_type=CategoryType.EXPENSE,
    )
    return cat


def _make_tx(category=None, amount=Decimal('500000'), transaction_date=None, **kwargs):
    cat = category or _income_cat()
    return Transaction.objects.create(
        transaction_type=cat.category_type,
        category=cat,
        amount=amount,
        transaction_date=transaction_date or timezone.now(),
        **kwargs,
    )


def _surgery_history():
    """Create the minimal set of objects needed for a SurgeryHistory."""
    from decimal import Decimal
    from surgeries.models import Patient, SurgeryHistory, SurgeryType
    uid = _uid_str()
    patient = Patient.objects.create(
        full_name=f'بیمار {uid}',
        case_code=f'FIN-{uid}',
        phone_number='09100000000',
    )
    surgery_type = SurgeryType.objects.create(
        name=f'نوع عمل {uid}',
        code=f'fin_{uid}',
        base_rate=Decimal('1000000'),
    )
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        amount=Decimal('5000000'),
        surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    )


# ---------------------------------------------------------------------------
# Transaction __str__ and field storage
# ---------------------------------------------------------------------------

class TransactionStrAndFieldsTest(TestCase):

    def test_str_contains_type_label(self):
        tx = _make_tx(category=_income_cat())
        result = str(tx)
        # __str__ returns: '{type_display} #{pk} — {amount} ({date})'
        # type_display for income is 'درآمد'
        self.assertIn('درآمد', result)

    def test_str_contains_amount(self):
        tx = _make_tx(amount=Decimal('1500000'))
        result = str(tx)
        self.assertIn('1,500,000', result)

    def test_str_contains_date(self):
        fixed = datetime.datetime(2025, 6, 15, 10, 0, tzinfo=datetime.timezone.utc)
        tx = _make_tx(transaction_date=fixed)
        result = str(tx)
        self.assertIn('2025-06-15', result)

    def test_description_stored_and_retrieved(self):
        desc = 'هزینه خرید داروهای بخش جراحی — دی ماه'
        tx = _make_tx(description=desc)
        tx.refresh_from_db()
        self.assertEqual(tx.description, desc)

    def test_transaction_date_stored_correctly(self):
        fixed = datetime.datetime(2025, 3, 21, 8, 30, tzinfo=datetime.timezone.utc)
        tx = _make_tx(transaction_date=fixed)
        tx.refresh_from_db()
        self.assertEqual(tx.transaction_date, fixed)

    def test_amount_stored_as_decimal(self):
        tx = _make_tx(amount=Decimal('12345.67'))
        tx.refresh_from_db()
        self.assertIsInstance(tx.amount, Decimal)
        self.assertEqual(tx.amount, Decimal('12345.67'))


# ---------------------------------------------------------------------------
# Transaction payment_status values
# ---------------------------------------------------------------------------

class TransactionPaymentStatusTest(TestCase):
    """Verify each payment_status value can be set and is persisted."""

    def _tx_with_status(self, pstatus):
        return Transaction.objects.create(
            transaction_type=TransactionType.INCOME,
            category=_income_cat(),
            amount=Decimal('100000'),
            transaction_date=timezone.now(),
            payment_status=pstatus,
        )

    def test_status_pending(self):
        tx = self._tx_with_status(TransactionPaymentStatus.PENDING)
        tx.refresh_from_db()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PENDING)

    def test_status_paid(self):
        tx = self._tx_with_status(TransactionPaymentStatus.PAID)
        tx.refresh_from_db()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PAID)

    def test_status_partial(self):
        tx = self._tx_with_status(TransactionPaymentStatus.PARTIAL)
        tx.refresh_from_db()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PARTIAL)

    def test_status_cancelled(self):
        tx = self._tx_with_status(TransactionPaymentStatus.CANCELLED)
        tx.refresh_from_db()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.CANCELLED)

    def test_status_can_be_updated_to_paid(self):
        tx = self._tx_with_status(TransactionPaymentStatus.PENDING)
        tx.payment_status = TransactionPaymentStatus.PAID
        tx.save()
        tx.refresh_from_db()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PAID)


# ---------------------------------------------------------------------------
# Transaction validation: Persian message content
# ---------------------------------------------------------------------------

class TransactionValidationMessageTest(TestCase):
    """Verify that clean() raises ValidationError with Persian messages.

    The existing tests.py already tests that the error IS raised.
    These tests verify the MESSAGE is actually Persian and meaningful.
    """

    def test_amount_zero_message_is_persian(self):
        cat = _income_cat()
        tx = Transaction(
            transaction_type=TransactionType.INCOME,
            category=cat,
            amount=Decimal('0'),
            transaction_date=timezone.now(),
        )
        try:
            tx.clean()
            self.fail("Expected ValidationError for zero amount")
        except ValidationError as exc:
            # Use exc.messages (flat list) to get actual string values without repr escaping
            all_messages = ' '.join(exc.messages)
            self.assertIn('مبلغ', all_messages, "Error message should contain 'مبلغ' (amount)")

    def test_amount_negative_message_is_persian(self):
        cat = _income_cat()
        tx = Transaction(
            transaction_type=TransactionType.INCOME,
            category=cat,
            amount=Decimal('-100'),
            transaction_date=timezone.now(),
        )
        try:
            tx.clean()
            self.fail("Expected ValidationError for negative amount")
        except ValidationError as exc:
            all_messages = ' '.join(exc.messages)
            self.assertIn('مبلغ', all_messages)

    def test_category_type_mismatch_message_is_persian(self):
        income_cat = _income_cat()
        tx = Transaction(
            transaction_type=TransactionType.EXPENSE,  # mismatch!
            category=income_cat,
            amount=Decimal('500000'),
            transaction_date=timezone.now(),
        )
        try:
            tx.clean()
            self.fail("Expected ValidationError for category type mismatch")
        except ValidationError as exc:
            all_messages = ' '.join(exc.messages)
            # Message: 'دسته‌بندی باید با نوع تراکنش مطابقت داشته باشد.'
            self.assertIn('مطابقت', all_messages,
                          "Error message should contain 'مطابقت' (match)")


# ---------------------------------------------------------------------------
# CenterCommissionIncome model
# ---------------------------------------------------------------------------

class CenterCommissionIncomeModelTest(TestCase):
    """Direct model-level tests for CenterCommissionIncome.

    The existing surgery income tests cover the service-triggered creation;
    these tests verify the model itself at the field/method level.
    """

    def setUp(self):
        self.surgery = _surgery_history()

    def _make_cci(self, amount=Decimal('500000'), status=IncomeStatus.CONFIRMED):
        return CenterCommissionIncome.objects.create(
            surgery=self.surgery,
            amount=amount,
            status=status,
            income_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )

    def test_create_confirmed_income_succeeds(self):
        cci = self._make_cci()
        self.assertIsNotNone(cci.pk)
        self.assertEqual(cci.status, IncomeStatus.CONFIRMED)

    def test_create_cancelled_income_succeeds(self):
        cci = self._make_cci(status=IncomeStatus.CANCELLED)
        cci.refresh_from_db()
        self.assertEqual(cci.status, IncomeStatus.CANCELLED)

    def test_amount_stored_as_decimal(self):
        cci = self._make_cci(amount=Decimal('1234567.89'))
        cci.refresh_from_db()
        self.assertIsInstance(cci.amount, Decimal)
        self.assertEqual(cci.amount, Decimal('1234567.89'))

    def test_income_date_stored_correctly(self):
        fixed = datetime.datetime(2025, 3, 21, 0, 0, tzinfo=datetime.timezone.utc)
        cci = CenterCommissionIncome.objects.create(
            surgery=self.surgery,
            amount=Decimal('300000'),
            status=IncomeStatus.CONFIRMED,
            income_date=fixed,
        )
        cci.refresh_from_db()
        self.assertEqual(cci.income_date, fixed)

    def test_linked_to_surgery_via_onetoone(self):
        cci = self._make_cci()
        self.assertEqual(cci.surgery_id, self.surgery.pk)

    def test_str_contains_amount(self):
        cci = self._make_cci(amount=Decimal('750000'))
        result = str(cci)
        # __str__: 'کمیسیون مرکز #{pk} — {amount:,} ریال ({status})'
        self.assertIn('750,000', result)

    def test_str_contains_status(self):
        cci = self._make_cci(status=IncomeStatus.CONFIRMED)
        result = str(cci)
        self.assertIn('CONFIRMED', result)

    def test_status_can_be_updated_to_cancelled(self):
        cci = self._make_cci(status=IncomeStatus.CONFIRMED)
        cci.status = IncomeStatus.CANCELLED
        cci.save()
        cci.refresh_from_db()
        self.assertEqual(cci.status, IncomeStatus.CANCELLED)

    def test_default_status_is_confirmed(self):
        """Default status is CONFIRMED, not CANCELLED."""
        cci = CenterCommissionIncome.objects.create(
            surgery=self.surgery,
            amount=Decimal('100000'),
            income_date=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(cci.status, IncomeStatus.CONFIRMED)
