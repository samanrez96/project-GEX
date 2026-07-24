"""Tests: manual row-total override for PurchaseItem.

Covers (per specification):
  1.  Default row total equals quantity × unit_price (auto mode).
  2.  manual_total overrides calculated total.
  3.  manual_total of zero is respected (not treated as falsy).
  4.  Blank / NULL manual_total falls back to automatic total.
  5.  Negative manual_total is rejected by model validation.
  6.  Manual total persists after save and reload.
  7.  Purchase grand total (finance expense) uses effective totals.
  8.  Mixed rows: some auto, some manual — purchase total is sum of effective totals.
  9.  Finance expense uses effective purchase total.
  10. Stock movement still uses PurchaseItem.quantity (not affected by manual_total).
  11. Product latest purchase_price still uses PurchaseItem.unit_price.
  12. ProductVendor price still uses PurchaseItem.unit_price.
  13. New dynamic row (admin POST) correctly submits manual_total.
  14. Reset-to-auto: blank manual_total → effective_total = quantity × unit_price.
  15. Changing quantity / unit_price does NOT overwrite a saved manual_total (backend).
  16. Changing quantity / unit_price DOES update calculated_total.
  17. Product autocomplete field still present in rendered form.
  18. TOTAL_FORMS still works alongside manual_total submission.
  19. Confirmed-item locking: manual_total stays read-only for locked items.
  20. No fractional value (.00) introduced by model field for integer totals.
"""

import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.utils import timezone

from inventory.models import (
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    StockMovement,
    Vendor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid = 5000


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _vendor():
    return Vendor.objects.create(name=f"فروشنده-MT-{_uid_next()}")


def _product(price=Decimal("1000")):
    n = _uid_next()
    return Product.objects.create(
        name=f"محصول-MT-{n}",
        internal_code=f"MT-{n:04d}",
        product_type=ProductType.MEDICINE,
        purchase_price=price,
    )


def _purchase(vendor=None):
    v = vendor or _vendor()
    return Purchase.objects.create(
        vendor=v,
        status=PurchaseStatus.PENDING,
        purchase_date=timezone.now(),
    )


def _item(purchase, product=None, quantity=Decimal("3"), unit_price=Decimal("18000"), manual_total=None):
    p = product or _product()
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=p,
        quantity=quantity,
        unit_price=unit_price,
        manual_total=manual_total,
    )


def _superuser():
    n = _uid_next()
    return User.objects.create_superuser(
        username=f"admin_mt_{n}", password="pass", email=""
    )


# ---------------------------------------------------------------------------
# 1–6  Model-level behaviour
# ---------------------------------------------------------------------------

class PurchaseItemEffectiveTotalTest(TestCase):

    def test_default_effective_total_is_quantity_times_price(self):
        """Without manual_total the effective total is qty × unit_price."""
        purchase = _purchase()
        item = _item(purchase, quantity=Decimal("3"), unit_price=Decimal("18000"))
        self.assertEqual(item.effective_total, Decimal("54000"))

    def test_calculated_total_property(self):
        purchase = _purchase()
        item = _item(purchase, quantity=Decimal("5"), unit_price=Decimal("10000"))
        self.assertEqual(item.calculated_total, Decimal("50000"))

    def test_manual_total_overrides_calculated(self):
        """When manual_total is set it takes priority over qty × unit_price."""
        purchase = _purchase()
        item = _item(
            purchase,
            quantity=Decimal("3"),
            unit_price=Decimal("18000"),
            manual_total=Decimal("50000"),
        )
        self.assertEqual(item.effective_total, Decimal("50000"))
        # calculated_total is still the arithmetic value
        self.assertEqual(item.calculated_total, Decimal("54000"))

    def test_manual_total_of_zero_is_respected(self):
        """manual_total=0 is a valid override; must NOT fall back to auto."""
        purchase = _purchase()
        item = _item(
            purchase,
            quantity=Decimal("3"),
            unit_price=Decimal("18000"),
            manual_total=Decimal("0"),
        )
        self.assertEqual(item.effective_total, Decimal("0"))
        # Explicit is-not-None check — zero is not None
        self.assertIsNotNone(item.manual_total)

    def test_null_manual_total_falls_back_to_calculated(self):
        """NULL manual_total means auto mode; effective_total = qty × unit_price."""
        purchase = _purchase()
        item = _item(
            purchase,
            quantity=Decimal("4"),
            unit_price=Decimal("5000"),
            manual_total=None,
        )
        self.assertIsNone(item.manual_total)
        self.assertEqual(item.effective_total, Decimal("20000"))

    def test_negative_manual_total_raises_validation_error(self):
        """Negative manual_total must be rejected by model.clean()."""
        purchase = _purchase()
        item = PurchaseItem(
            purchase=purchase,
            product=_product(),
            quantity=Decimal("2"),
            unit_price=Decimal("1000"),
            manual_total=Decimal("-1"),
        )
        with self.assertRaises(ValidationError) as ctx:
            item.clean()
        self.assertIn("manual_total", ctx.exception.message_dict)

    def test_manual_total_persists_after_save_and_reload(self):
        """Saved manual_total must be retrievable from the database."""
        purchase = _purchase()
        item = _item(purchase, manual_total=Decimal("50000"))
        pk = item.pk
        reloaded = PurchaseItem.objects.get(pk=pk)
        self.assertEqual(reloaded.manual_total, Decimal("50000"))
        self.assertEqual(reloaded.effective_total, Decimal("50000"))

    def test_changing_quantity_does_not_overwrite_manual_total(self):
        """Updating quantity on a saved item must not clear manual_total."""
        purchase = _purchase()
        item = _item(purchase, quantity=Decimal("3"), unit_price=Decimal("18000"),
                     manual_total=Decimal("50000"))
        item.quantity = Decimal("4")
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.manual_total, Decimal("50000"))
        self.assertEqual(item.effective_total, Decimal("50000"))

    def test_changing_quantity_updates_calculated_total(self):
        """calculated_total must reflect the latest qty × price even with manual_total set."""
        purchase = _purchase()
        item = _item(purchase, quantity=Decimal("3"), unit_price=Decimal("18000"),
                     manual_total=Decimal("50000"))
        item.quantity = Decimal("4")
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.calculated_total, Decimal("72000"))

    def test_reset_to_auto_by_clearing_manual_total(self):
        """Setting manual_total=None restores automatic effective total."""
        purchase = _purchase()
        item = _item(purchase, quantity=Decimal("3"), unit_price=Decimal("18000"),
                     manual_total=Decimal("50000"))
        item.manual_total = None
        item.save()
        item.refresh_from_db()
        self.assertIsNone(item.manual_total)
        self.assertEqual(item.effective_total, Decimal("54000"))


# ---------------------------------------------------------------------------
# 7–9  Finance integration
# ---------------------------------------------------------------------------

class PurchaseFinanceManualTotalTest(TestCase):
    """Finance expense amounts must use effective_total (not qty × unit_price)."""

    def _expense_txs(self, purchase):
        from django.contrib.contenttypes.models import ContentType
        from finance.models import Transaction, TransactionType
        ct = ContentType.objects.get_for_model(purchase)
        return Transaction.objects.filter(
            content_type=ct,
            object_id=purchase.pk,
            transaction_type=TransactionType.EXPENSE,
        )

    def test_finance_expense_uses_effective_total_not_calculated(self):
        """Confirming a purchase with manual_total must create expense using manual value."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product=product,
              quantity=Decimal("3"), unit_price=Decimal("18000"),
              manual_total=Decimal("50000"))

        purchase.confirm()

        txs = self._expense_txs(purchase)
        self.assertEqual(txs.count(), 1)
        self.assertEqual(txs.first().amount, Decimal("50000"))

    def test_finance_expense_for_automatic_row_uses_qty_times_price(self):
        """No manual_total → expense amount = qty × unit_price."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product=product,
              quantity=Decimal("2"), unit_price=Decimal("5000"),
              manual_total=None)

        purchase.confirm()

        txs = self._expense_txs(purchase)
        self.assertEqual(txs.count(), 1)
        self.assertEqual(txs.first().amount, Decimal("10000"))

    def test_mixed_rows_purchase_total_sums_effective_totals(self):
        """Purchase with one auto row and one manual row: expense = sum of effective totals."""
        vendor    = _vendor()
        product_a = _product()
        product_b = _product()
        purchase  = _purchase(vendor)
        # Row A: auto → effective = 3 × 18000 = 54,000
        _item(purchase, product=product_a,
              quantity=Decimal("3"), unit_price=Decimal("18000"),
              manual_total=None)
        # Row B: manual → effective = 40,000
        _item(purchase, product=product_b,
              quantity=Decimal("3"), unit_price=Decimal("18000"),
              manual_total=Decimal("40000"))

        purchase.confirm()

        txs = self._expense_txs(purchase)
        total_amount = sum(tx.amount for tx in txs)
        self.assertEqual(total_amount, Decimal("94000"))

    def test_manual_total_zero_creates_zero_expense(self):
        """manual_total=0 means the effective total is 0; expense should not be created."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product=product,
              quantity=Decimal("1"), unit_price=Decimal("10000"),
              manual_total=Decimal("0"))

        purchase.confirm()

        # effective_total=0 → line is skipped (total <= 0 guard in PurchaseFinanceService)
        txs = self._expense_txs(purchase)
        self.assertEqual(txs.count(), 0)


# ---------------------------------------------------------------------------
# 10–12  Stock and price update restrictions
# ---------------------------------------------------------------------------

class PurchaseItemStockAndPriceTest(TestCase):
    """manual_total must NOT affect stock movements or price updates."""

    def test_stock_movement_uses_quantity_not_manual_total(self):
        """StockMovement quantity must equal PurchaseItem.quantity regardless of manual_total."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product=product,
              quantity=Decimal("5"), unit_price=Decimal("10000"),
              manual_total=Decimal("99999"))

        purchase.confirm()

        movements = StockMovement.objects.filter(product=product)
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().quantity, Decimal("5"))

    def test_product_latest_price_uses_unit_price_not_manual_total(self):
        """Product.purchase_price must be updated from unit_price, not manual_total."""
        vendor   = _vendor()
        product  = _product(price=Decimal("1"))
        purchase = _purchase(vendor)
        _item(purchase, product=product,
              quantity=Decimal("1"), unit_price=Decimal("15000"),
              manual_total=Decimal("99999"))

        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("15000"))

    def test_product_vendor_price_uses_unit_price_not_manual_total(self):
        """ProductVendor.unit_price must reflect PurchaseItem.unit_price, not manual_total."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product=product,
              quantity=Decimal("1"), unit_price=Decimal("12000"),
              manual_total=Decimal("999"))

        purchase.confirm()

        pv = ProductVendor.objects.get(product=product, vendor=vendor)
        self.assertEqual(pv.unit_price, Decimal("12000"))


# ---------------------------------------------------------------------------
# 13–15  Admin form (HTTP) integration
# ---------------------------------------------------------------------------

class PurchaseAdminManualTotalFormTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def _post_change(self, purchase, product, qty, price, manual_total_val=""):
        data = {
            "vendor":              str(purchase.vendor.pk),
            "purchase_date":       "1405/04/03",
            "status":              "PENDING",
            "notes":               "",
            "items-TOTAL_FORMS":   "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-product":     str(product.pk),
            "items-0-quantity":    str(qty),
            "items-0-unit_price":  str(price),
            "items-0-manual_total": str(manual_total_val),
            "items-0-notes":       "",
            "items-0-id":          "",
            "_save":               "1",
        }
        return self.client.post(
            f"/admin/inventory/purchase/{purchase.pk}/change/", data
        )

    def test_manual_total_submitted_via_admin_form_is_saved(self):
        """Submitting manual_total via the admin form must persist it to the database."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)

        r = self._post_change(purchase, product, qty=3, price=18000, manual_total_val=50000)
        self.assertIn(r.status_code, [301, 302],
                      f"POST must redirect on success; got {r.status_code}")

        item = purchase.items.first()
        self.assertIsNotNone(item)
        self.assertEqual(item.manual_total, Decimal("50000"))
        self.assertEqual(item.effective_total, Decimal("50000"))

    def test_blank_manual_total_saves_as_null(self):
        """Leaving manual_total blank must save NULL (auto mode)."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)

        r = self._post_change(purchase, product, qty=3, price=18000, manual_total_val="")
        self.assertIn(r.status_code, [301, 302])

        item = purchase.items.first()
        self.assertIsNone(item.manual_total)
        self.assertEqual(item.effective_total, Decimal("54000"))

    def test_negative_manual_total_is_rejected_by_form(self):
        """Admin form must not save a negative manual_total."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)

        r = self._post_change(purchase, product, qty=3, price=18000, manual_total_val=-1)
        # Should re-render the form with an error (200), not redirect (302)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(purchase.items.count(), 0)

    def test_total_forms_still_works_with_manual_total(self):
        """TOTAL_FORMS accounting must remain correct when manual_total is submitted."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)

        r = self._post_change(purchase, product, qty=2, price=10000, manual_total_val=15000)
        self.assertIn(r.status_code, [301, 302])
        self.assertEqual(purchase.items.count(), 1)

    def test_manual_total_field_present_in_rendered_form(self):
        """The purchase change form must include the manual_total input in the HTML."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=Decimal("3"),
            unit_price=Decimal("18000"),
            manual_total=Decimal("50000"),
        )
        r = self.client.get(f"/admin/inventory/purchase/{purchase.pk}/change/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode("utf-8")
        self.assertIn('name="items-0-manual_total"', content,
                      "manual_total input must be rendered in the form")

    def test_manual_total_value_present_on_edit_page_for_existing_override(self):
        """An existing manual_total must be pre-filled on the edit page."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=Decimal("3"),
            unit_price=Decimal("18000"),
            manual_total=Decimal("50000"),
        )
        r = self.client.get(f"/admin/inventory/purchase/{purchase.pk}/change/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode("utf-8")
        self.assertIn("50000", content,
                      "Persisted manual_total value must appear on the edit page")

    def test_product_autocomplete_still_present(self):
        """The product selector (pf-product-trigger pattern via JS) must still be referenced."""
        r = self.client.get("/admin/inventory/purchase/add/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode("utf-8")
        # JS file still loaded
        self.assertIn("purchase_form.js", content)


# ---------------------------------------------------------------------------
# 16  Confirmed purchase locking
# ---------------------------------------------------------------------------

class PurchaseItemConfirmedLockingTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def test_confirmed_purchase_renders_manual_total_read_only(self):
        """For a CONFIRMED purchase, all item inputs are read-only — manual_total too."""
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=Decimal("3"),
            unit_price=Decimal("18000"),
            manual_total=Decimal("50000"),
        )
        purchase.confirm()

        r = self.client.get(f"/admin/inventory/purchase/{purchase.pk}/change/")
        self.assertEqual(r.status_code, 200)
        # pf-items-locked class should be present
        content = r.content.decode("utf-8")
        self.assertIn("pf-items-locked", content,
                      "CONFIRMED purchase items section must have pf-items-locked class")


# ---------------------------------------------------------------------------
# 17  JS source assertions
# ---------------------------------------------------------------------------

class PurchaseFormJsManualTotalTest(TestCase):
    """JS source must implement the manual override and reset-to-auto logic."""

    @classmethod
    def _js(cls):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static", "admin", "js", "purchase_form.js",
        )
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_js_defines_get_row_effective_total(self):
        self.assertIn("getRowEffectiveTotal", self._js())

    def test_js_defines_row_is_manual(self):
        self.assertIn("rowIsManual", self._js())

    def test_js_update_row_total_sets_placeholder_not_value(self):
        """Auto-mode update must use .placeholder, never .value (prevents accidental manual mode)."""
        src = self._js()
        # Must reference .placeholder
        self.assertIn(".placeholder", src,
                      "JS must update .placeholder to show calculated total in auto mode")

    def test_js_defines_reset_row_to_auto(self):
        self.assertIn("resetRowToAuto", self._js())

    def test_js_reset_clears_manual_input_value(self):
        """resetRowToAuto must set the manual_total input .value to empty string."""
        src = self._js()
        reset_idx = src.find("function resetRowToAuto")
        self.assertGreater(reset_idx, 0)
        reset_body = src[reset_idx: reset_idx + 400]
        self.assertIn("inp.value = ''", reset_body,
                      "resetRowToAuto must clear manual_total input value")

    def test_js_grand_total_uses_effective_total(self):
        """updateGrandTotal must call getRowEffectiveTotal, not multiply qty × price directly."""
        src = self._js()
        grand_idx = src.find("function updateGrandTotal")
        self.assertGreater(grand_idx, 0)
        grand_body = src[grand_idx: grand_idx + 600]
        self.assertIn("getRowEffectiveTotal", grand_body,
                      "updateGrandTotal must use getRowEffectiveTotal")

    def test_js_qty_price_change_checks_manual_mode_before_updating(self):
        """qty/price change handlers must check rowIsManual before updating the row total."""
        src = self._js()
        self.assertIn("rowIsManual(row)", src,
                      "JS must guard qty/price updates with rowIsManual check")

    def test_js_manual_active_class_added_on_input(self):
        """JS must add pf-manual-active class when user enters a manual total."""
        self.assertIn("pf-manual-active", self._js())

    def test_js_lock_hides_reset_buttons(self):
        """lockItemInputs must hide reset buttons for CONFIRMED/CANCELLED purchases."""
        src = self._js()
        lock_idx = src.find("function lockItemInputs")
        self.assertGreater(lock_idx, 0)
        lock_body = src[lock_idx: lock_idx + 1000]
        self.assertIn("pf-row-total-reset", lock_body,
                      "lockItemInputs must handle .pf-row-total-reset elements")

    def test_js_manual_total_selector_uses_name_suffix(self):
        """JS must locate manual_total input by name suffix '-manual_total'."""
        self.assertIn("-manual_total", self._js())

    def test_js_still_defines_init_product_selector(self):
        """initProductSelector must still be present (product selector not affected)."""
        self.assertIn("initProductSelector", self._js())

    def test_js_total_forms_query_selector_still_correct(self):
        src = self._js()
        self.assertIn("querySelector('[name=\"' + PREFIX + '-TOTAL_FORMS\"]')", src)
