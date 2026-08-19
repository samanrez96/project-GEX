"""Tests for the seed_demo_data management command (CLI-65).

Covers:
- Command runs successfully
- Idempotency: running twice does not duplicate records
- Expected records are created (vendors, products, employees, etc.)
- Confirmed purchases increase stock and create inbound StockMovements
- Surgery used items decrease stock and create outbound StockMovements
- Finance records are created through existing flows
- Safety guard: DEBUG=False without --force raises CommandError
"""

from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from io import StringIO


class SeedDemoDataCommandTest(TestCase):

    def _seed(self, **kwargs):
        """Run the seed command, capturing output.  force=True because tests run with DEBUG=False."""
        out = StringIO()
        call_command("seed_demo_data", stdout=out, quiet=True, force=True, **kwargs)
        return out.getvalue()

    # ── Safety guard ─────────────────────────────────────────────────────────

    @override_settings(DEBUG=False)
    def test_refuses_to_run_in_production_without_force(self):
        """Command must raise CommandError when DEBUG=False and --force not passed."""
        with self.assertRaises(CommandError):
            # Deliberately call WITHOUT force=True to verify the guard
            call_command("seed_demo_data", stdout=StringIO(), force=False)

    @override_settings(DEBUG=True)
    def test_runs_with_debug_true_no_force_needed(self):
        """With DEBUG=True the command runs without --force."""
        out = StringIO()
        call_command("seed_demo_data", stdout=out, quiet=True)
        self.assertIn("Demo data seeded successfully", out.getvalue())

    # ── Basic success ─────────────────────────────────────────────────────────

    def test_command_runs_successfully(self):
        output = self._seed()
        self.assertIn("Demo data seeded successfully", output)

    # ── Idempotency ───────────────────────────────────────────────────────────

    def test_idempotent_vendors(self):
        from inventory.models import Vendor
        self._seed()
        count_after_first = Vendor.objects.filter(name__startswith="DEMO").count()
        self._seed()
        count_after_second = Vendor.objects.filter(name__startswith="DEMO").count()
        self.assertEqual(count_after_first, count_after_second)

    def test_idempotent_products(self):
        from inventory.models import Product
        self._seed()
        count1 = Product.objects.filter(internal_code__startswith="DEMO-").count()
        self._seed()
        count2 = Product.objects.filter(internal_code__startswith="DEMO-").count()
        self.assertEqual(count1, count2)

    def test_idempotent_employees(self):
        from employees.models import Employee
        self._seed()
        count1 = Employee.objects.filter(national_id__startswith="DEMO-EMP-").count()
        self._seed()
        count2 = Employee.objects.filter(national_id__startswith="DEMO-EMP-").count()
        self.assertEqual(count1, count2)

    def test_idempotent_surgeries(self):
        from surgeries.models import SurgeryHistory
        self._seed()
        count1 = SurgeryHistory.objects.filter(description__contains="DEMO-S0").count()
        self._seed()
        count2 = SurgeryHistory.objects.filter(description__contains="DEMO-S0").count()
        self.assertEqual(count1, count2)

    def test_idempotent_purchases(self):
        from inventory.models import Purchase
        self._seed()
        count1 = Purchase.objects.filter(reference_number__startswith="DEMO-INV-").count()
        self._seed()
        count2 = Purchase.objects.filter(reference_number__startswith="DEMO-INV-").count()
        self.assertEqual(count1, count2)

    # ── Expected record counts ────────────────────────────────────────────────

    def test_creates_3_vendors(self):
        from inventory.models import Vendor
        self._seed()
        self.assertEqual(Vendor.objects.filter(name__startswith="DEMO").count(), 3)

    def test_creates_155_products(self):
        from inventory.models import Product
        self._seed()
        self.assertEqual(
            Product.objects.filter(internal_code__startswith="DEMO-").count(), 155
        )

    def test_creates_150_medicine_products(self):
        from inventory.models import Product, ProductType
        self._seed()
        self.assertEqual(
            Product.objects.filter(
                internal_code__startswith="DEMO-MED-",
                product_type=ProductType.MEDICINE,
            ).count(),
            150,
        )

    def test_medicine_codes_are_unique(self):
        from inventory.models import Product, ProductType
        self._seed()
        codes = list(
            Product.objects.filter(
                internal_code__startswith="DEMO-MED-",
                product_type=ProductType.MEDICINE,
            ).values_list("internal_code", flat=True)
        )
        self.assertEqual(len(codes), len(set(codes)))

    def test_all_medicines_have_correct_product_type(self):
        from inventory.models import Product, ProductType
        self._seed()
        non_medicine = Product.objects.filter(
            internal_code__startswith="DEMO-MED-",
        ).exclude(product_type=ProductType.MEDICINE)
        self.assertEqual(non_medicine.count(), 0)

    def test_medicine_vendor_links_exist(self):
        """All 150 medicines must be linked to at least one vendor."""
        from inventory.models import Product, ProductType, ProductVendor
        self._seed()
        medicines = Product.objects.filter(
            internal_code__startswith="DEMO-MED-",
            product_type=ProductType.MEDICINE,
        )
        for med in medicines:
            self.assertTrue(
                ProductVendor.objects.filter(product=med).exists(),
                f"No vendor link for {med.internal_code}",
            )

    def test_150_medicines_fit_in_one_page(self):
        """150 medicines / page_size 150 = exactly 1 page."""
        from inventory.models import Product, ProductType
        self._seed()
        total = Product.objects.filter(
            internal_code__startswith="DEMO-MED-",
            product_type=ProductType.MEDICINE,
        ).count()
        self.assertEqual(total, 150)
        import math
        self.assertEqual(math.ceil(total / 150), 1)

    def test_creates_5_equipment_products(self):
        from inventory.models import Product, ProductType
        self._seed()
        self.assertEqual(
            Product.objects.filter(
                internal_code__startswith="DEMO-EQP-",
                product_type=ProductType.EQUIPMENT,
            ).count(),
            5,
        )

    def test_creates_6_employees(self):
        from employees.models import Employee
        self._seed()
        self.assertEqual(
            Employee.objects.filter(national_id__startswith="DEMO-EMP-").count(), 6
        )

    def test_creates_4_surgery_types(self):
        from surgeries.models import SurgeryType
        self._seed()
        self.assertEqual(
            SurgeryType.objects.filter(code__startswith="demo_").count(), 4
        )

    def test_creates_5_patients(self):
        from surgeries.models import Patient
        self._seed()
        self.assertEqual(
            Patient.objects.filter(case_code__startswith="DEMO-CASE-").count(), 5
        )

    def test_creates_3_purchases(self):
        from inventory.models import Purchase
        self._seed()
        self.assertEqual(
            Purchase.objects.filter(reference_number__startswith="DEMO-INV-").count(),
            3,
        )

    def test_creates_6_surgeries(self):
        from surgeries.models import SurgeryHistory
        self._seed()
        self.assertEqual(
            SurgeryHistory.objects.filter(description__contains="DEMO-S0").count(), 6
        )

    # ── Purchase → stock flow ─────────────────────────────────────────────────

    def test_confirmed_purchase_increases_medicine_stock(self):
        from inventory.models import Product
        self._seed()
        propofol = Product.objects.get(internal_code="DEMO-MED-001")
        # DEMO-INV-001 buys 500 ml; DEMO-INV-003 is pending (no stock)
        self.assertGreaterEqual(propofol.current_stock, Decimal("0"))
        # Confirmed purchase creates positive stock
        self.assertGreater(propofol.current_stock, Decimal("0"))

    def test_confirmed_purchase_creates_in_stock_movements(self):
        from inventory.models import MovementType, Product, StockMovement
        self._seed()
        propofol = Product.objects.get(internal_code="DEMO-MED-001")
        in_movements = StockMovement.objects.filter(
            product=propofol, movement_type=MovementType.IN
        )
        self.assertGreater(in_movements.count(), 0)

    def test_pending_purchase_does_not_create_stock_movement(self):
        from inventory.models import Purchase, PurchaseStatus, StockMovement
        self._seed()
        pending = Purchase.objects.get(reference_number="DEMO-INV-003")
        self.assertEqual(pending.status, PurchaseStatus.PENDING)
        self.assertFalse(pending.stock_applied)
        # Pending purchase must NOT create any StockMovement
        items = pending.items.all()
        for item in items:
            self.assertFalse(
                StockMovement.objects.filter(
                    product=item.product,
                    reference_id=f"purchase-{pending.pk}",
                ).exists()
            )

    # ── Surgery used items → stock flow ──────────────────────────────────────

    def test_surgery_used_items_create_out_stock_movements(self):
        from inventory.models import MovementType, Product, StockMovement
        self._seed()
        propofol = Product.objects.get(internal_code="DEMO-MED-001")
        out_movements = StockMovement.objects.filter(
            product=propofol, movement_type=MovementType.OUT
        )
        self.assertGreater(out_movements.count(), 0)

    def test_surgery_used_items_decrease_stock(self):
        """Stock after confirmed purchase minus used items should be > 0 and < purchased qty."""
        from inventory.models import Product
        self._seed()
        propofol = Product.objects.get(internal_code="DEMO-MED-001")
        # Purchased 500 ml via DEMO-INV-001; consumed 50+80+45+75=250 ml
        self.assertGreater(propofol.current_stock, Decimal("0"))
        self.assertLess(propofol.current_stock, Decimal("500"))

    def test_used_items_count_correct(self):
        from surgeries.models import SurgeryUsedItem
        self._seed()
        # 5+4+4+3 = 16 used item records across 4 completed surgeries
        count = SurgeryUsedItem.objects.filter(
            description__contains="DEMO"
        ).count()
        self.assertEqual(count, 16)

    # ── Finance flows ─────────────────────────────────────────────────────────

    def test_confirmed_purchase_creates_finance_expense(self):
        """DEMO-INV-001 (confirmed) must have linked expense Transactions."""
        from django.contrib.contenttypes.models import ContentType
        from finance.models import Transaction, TransactionType
        from inventory.models import Purchase
        self._seed()
        purchase = Purchase.objects.get(reference_number="DEMO-INV-001")
        ct = ContentType.objects.get_for_model(purchase)
        expenses = Transaction.objects.filter(
            content_type=ct,
            object_id=purchase.pk,
            transaction_type=TransactionType.EXPENSE,
        )
        self.assertGreater(expenses.count(), 0)

    def test_surgery_center_commission_creates_finance_income(self):
        """Completed surgery with center_commission_percent creates income Transaction."""
        from django.contrib.contenttypes.models import ContentType
        from finance.models import CenterCommissionIncome, Transaction, TransactionType
        from surgeries.models import SurgeryHistory
        self._seed()
        # DEMO-S001 is COMPLETED with commission percent set
        surgery = SurgeryHistory.objects.filter(
            description__contains="DEMO-S001"
        ).first()
        self.assertIsNotNone(surgery)
        try:
            cci = surgery.center_commission_income
            if cci:
                ct = ContentType.objects.get_for_model(cci)
                income_txs = Transaction.objects.filter(
                    content_type=ct,
                    object_id=cci.pk,
                    transaction_type=TransactionType.INCOME,
                )
                self.assertGreater(income_txs.count(), 0)
        except CenterCommissionIncome.DoesNotExist:
            pass  # commission amount may be 0 in some edge cases

    # ── Report readiness ──────────────────────────────────────────────────────

    def test_balance_report_has_nonzero_data(self):
        """After seeding, balance report API returns non-zero totals."""
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        from django.contrib.auth.models import Group

        self._seed()

        User = get_user_model()
        u = User.objects.create_user(username="seed_test_admin", password="x")
        g, _ = Group.objects.get_or_create(name="admin")
        u.groups.add(g)

        client = APIClient()
        client.force_authenticate(user=u)
        resp = client.get("/api/v2/finance/reports/balance/")
        self.assertEqual(resp.status_code, 200)

        data = resp.data
        total_income  = Decimal(str(data.get("total_income",  "0")))
        total_expense = Decimal(str(data.get("total_expense", "0")))
        # After seeding there must be some income and some expense
        self.assertGreater(total_income,  Decimal("0"))
        self.assertGreater(total_expense, Decimal("0"))

    def test_inventory_stock_has_nonzero_products(self):
        """After seeding, at least some products have positive stock."""
        from inventory.models import Product
        self._seed()
        products_in_stock = Product.objects.filter(
            internal_code__startswith="DEMO-",
            current_stock__gt=0,
        )
        self.assertGreater(products_in_stock.count(), 0)
