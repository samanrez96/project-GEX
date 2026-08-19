"""Tests: automatic expense Transaction creation from Purchase events.

Covers:
  - purchase confirmed → expense created
  - medicine purchase → medicine expense category
  - equipment purchase → equipment expense category
  - mixed purchase → separate expenses per type
  - updating purchase items updates expense amounts
  - duplicate expense not created (idempotency)
  - cancelled purchase cancels expense
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import FinanceCategory, Transaction, TransactionPaymentStatus, TransactionType
from inventory.models import (
    Product,
    ProductCategory,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)

User = get_user_model()

CONFIRM_URL = '/api/v2/inventory/purchases/{pk}/confirm/'
CANCEL_URL  = '/api/v2/inventory/purchases/{pk}/cancel/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_vendor(**kwargs):
    defaults = {'name': 'تامین‌کننده تست'}
    defaults.update(kwargs)
    return Vendor.objects.create(**defaults)


def make_category(name='دارو', parent=None):
    obj, _ = ProductCategory.objects.get_or_create(name=name, parent=parent)
    return obj


def make_product(product_type=ProductType.MEDICINE, price=Decimal('1000'), **kwargs):
    import uuid
    defaults = {
        'name': f'محصول {uuid.uuid4().hex[:6]}',
        'internal_code': f'CODE-{uuid.uuid4().hex[:8]}',
        'product_type': product_type,
        'unit': 'عدد',
        'purchase_price': price,
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def make_purchase(vendor=None, **kwargs):
    if vendor is None:
        vendor = make_vendor()
    defaults = {'vendor': vendor, 'purchase_date': timezone.now()}
    defaults.update(kwargs)
    return Purchase.objects.create(**defaults)


def make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('1000')):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
    )


def expense_transactions_for(purchase):
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(purchase)
    return Transaction.objects.filter(
        content_type=ct,
        object_id=purchase.pk,
        transaction_type=TransactionType.EXPENSE,
    )


# ---------------------------------------------------------------------------
# Model-level tests (no HTTP)
# ---------------------------------------------------------------------------

class PurchaseExpenseModelTest(TestCase):

    def test_confirmed_purchase_creates_expense(self):
        """Confirming a purchase must create at least one expense Transaction."""
        vendor  = make_vendor()
        product = make_product()
        purchase = make_purchase(vendor=vendor)
        make_item(purchase, product, quantity=Decimal('2'), unit_price=Decimal('5000'))

        purchase.confirm()

        txs = expense_transactions_for(purchase)
        self.assertEqual(txs.count(), 1)
        tx = txs.first()
        self.assertEqual(tx.transaction_type, TransactionType.EXPENSE)
        self.assertEqual(tx.amount, Decimal('10000.00'))
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.PENDING)

    def test_medicine_purchase_uses_medicine_category(self):
        """Medicine items must produce an expense with the medicine cost category."""
        product  = make_product(product_type=ProductType.MEDICINE)
        purchase = make_purchase()
        make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('3000'))

        purchase.confirm()

        tx = expense_transactions_for(purchase).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.category.name, 'هزینه دارو')
        self.assertEqual(tx.category.category_type, 'expense')

    def test_equipment_purchase_uses_equipment_category(self):
        """Equipment items must produce an expense with the equipment cost category."""
        product  = make_product(product_type=ProductType.EQUIPMENT)
        purchase = make_purchase()
        make_item(purchase, product, quantity=Decimal('2'), unit_price=Decimal('2000'))

        purchase.confirm()

        tx = expense_transactions_for(purchase).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.category.name, 'هزینه تجهیزات')
        self.assertEqual(tx.amount, Decimal('4000.00'))

    def test_mixed_purchase_creates_separate_expenses_per_type(self):
        """A purchase with both medicine and equipment items gets two expense Transactions."""
        medicine_product  = make_product(product_type=ProductType.MEDICINE)
        equipment_product = make_product(product_type=ProductType.EQUIPMENT)
        purchase          = make_purchase()
        make_item(purchase, medicine_product,  quantity=Decimal('1'), unit_price=Decimal('1000'))
        make_item(purchase, equipment_product, quantity=Decimal('1'), unit_price=Decimal('2000'))

        purchase.confirm()

        txs = expense_transactions_for(purchase)
        self.assertEqual(txs.count(), 2)

        categories = set(txs.values_list('category__name', flat=True))
        self.assertIn('هزینه دارو',      categories)
        self.assertIn('هزینه تجهیزات', categories)

        amounts = {tx.category.name: tx.amount for tx in txs}
        self.assertEqual(amounts['هزینه دارو'],      Decimal('1000.00'))
        self.assertEqual(amounts['هزینه تجهیزات'], Decimal('2000.00'))

    def test_no_duplicate_expense_on_double_confirm(self):
        """Calling confirm() twice must not create duplicate expense Transactions."""
        product  = make_product()
        purchase = make_purchase()
        make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('500'))

        purchase.confirm()
        # Simulate calling confirm() again (status is already CONFIRMED → stock_applied guard)
        # Force re-save to trigger signal again
        purchase.save()

        txs = expense_transactions_for(purchase)
        self.assertEqual(txs.count(), 1)

    def test_updating_item_price_updates_expense(self):
        """Changing a PurchaseItem's unit_price must update the linked expense amount."""
        product  = make_product()
        purchase = make_purchase()
        item     = make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('1000'))

        purchase.confirm()

        tx_before = expense_transactions_for(purchase).first()
        self.assertEqual(tx_before.amount, Decimal('1000.00'))

        # Update the item price
        item.unit_price = Decimal('2000')
        item.save()

        tx_after = expense_transactions_for(purchase).get(pk=tx_before.pk)
        self.assertEqual(tx_after.amount, Decimal('2000.00'))

    def test_adding_item_updates_expense(self):
        """Adding a new item to a confirmed purchase must update the expense total."""
        product  = make_product(product_type=ProductType.MEDICINE)
        purchase = make_purchase()
        make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('1000'))

        purchase.confirm()

        # Add another medicine item
        product2 = make_product(product_type=ProductType.MEDICINE)
        make_item(purchase, product2, quantity=Decimal('1'), unit_price=Decimal('500'))

        txs = expense_transactions_for(purchase)
        self.assertEqual(txs.count(), 1)
        self.assertEqual(txs.first().amount, Decimal('1500.00'))

    def test_cancelled_purchase_cancels_expense(self):
        """Cancelling a confirmed purchase must set expense status to CANCELLED."""
        product  = make_product()
        purchase = make_purchase()
        make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('1000'))

        purchase.confirm()
        self.assertEqual(expense_transactions_for(purchase).first().payment_status,
                         TransactionPaymentStatus.PENDING)

        purchase.cancel()

        tx = expense_transactions_for(purchase).first()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.CANCELLED)

    def test_pending_purchase_creates_no_expense(self):
        """A PENDING purchase must not produce any expense Transactions."""
        product  = make_product()
        purchase = make_purchase()
        make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('1000'))

        # Still PENDING — no expense expected
        self.assertEqual(expense_transactions_for(purchase).count(), 0)

    def test_expense_linked_to_purchase_via_generic_fk(self):
        """The expense Transaction must be linked to the Purchase via GenericForeignKey."""
        from django.contrib.contenttypes.models import ContentType

        product  = make_product()
        purchase = make_purchase()
        make_item(purchase, product, quantity=Decimal('1'), unit_price=Decimal('1000'))
        purchase.confirm()

        tx = expense_transactions_for(purchase).first()
        purchase_ct = ContentType.objects.get_for_model(purchase)
        self.assertEqual(tx.content_type, purchase_ct)
        self.assertEqual(tx.object_id, purchase.pk)


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------

class PurchaseExpenseAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='inv_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_confirm_api_creates_expense(self):
        vendor   = make_vendor()
        product  = make_product()
        purchase = make_purchase(vendor=vendor)
        make_item(purchase, product, unit_price=Decimal('7000'))

        resp = self.client.post(CONFIRM_URL.format(pk=purchase.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        txs = expense_transactions_for(purchase)
        self.assertEqual(txs.count(), 1)
        self.assertEqual(txs.first().amount, Decimal('7000.00'))

    def test_cancel_api_cancels_expense(self):
        product  = make_product()
        purchase = make_purchase()
        make_item(purchase, product, unit_price=Decimal('3000'))

        self.client.post(CONFIRM_URL.format(pk=purchase.pk))
        self.client.post(CANCEL_URL.format(pk=purchase.pk))

        tx = expense_transactions_for(purchase).first()
        self.assertEqual(tx.payment_status, TransactionPaymentStatus.CANCELLED)

    def test_unauthenticated_cannot_confirm(self):
        self.client.force_authenticate(user=None)
        purchase = make_purchase()
        resp = self.client.post(CONFIRM_URL.format(pk=purchase.pk))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
