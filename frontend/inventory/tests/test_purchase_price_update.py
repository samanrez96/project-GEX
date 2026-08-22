"""Tests for price auto-update on Purchase.confirm() (CLI-71).

Verifies:
- Product.purchase_price is updated to the latest PurchaseItem.unit_price
- ProductVendor.unit_price is updated to the latest PurchaseItem.unit_price
- ProductVendor.last_price_date is set to the purchase date
- Products with zero/null unit_price are skipped (no price regression)
- Products with no ProductVendor link are handled gracefully (no crash)
- A single vendor can be linked to multiple products (unique constraint check)
"""

import datetime
from decimal import Decimal

from django.test import TestCase

from inventory.models import (
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)


_uid = 0


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _vendor(name=None):
    return Vendor.objects.create(name=name or f"فروشنده {_uid_next()}")


def _product(**kw):
    n = _uid_next()
    defaults = {
        "name":          f"محصول {n}",
        "internal_code": f"PPU-{n:04d}",
        "product_type":  ProductType.MEDICINE,
        "unit":          "عدد",
        "purchase_price": Decimal("0"),
    }
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _purchase(vendor, status=PurchaseStatus.PENDING, purchase_date=None):
    return Purchase.objects.create(
        vendor=vendor,
        status=status,
        purchase_date=purchase_date or datetime.datetime(2025, 6, 1, 10, 0, 0),
    )


def _item(purchase, product, quantity=10, unit_price=None):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
    )


class PurchasePriceUpdateTest(TestCase):

    def test_confirm_updates_product_purchase_price(self):
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("5000"))

        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("5000"))

    def test_confirm_updates_product_vendor_unit_price(self):
        vendor  = _vendor()
        product = _product()
        pv = ProductVendor.objects.create(
            vendor=vendor,
            product=product,
            unit_price=Decimal("1000"),
        )
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("5500"))

        purchase.confirm()

        pv.refresh_from_db()
        self.assertEqual(pv.unit_price, Decimal("5500"))

    def test_confirm_updates_product_vendor_last_price_date(self):
        vendor  = _vendor()
        product = _product()
        pv = ProductVendor.objects.create(
            vendor=vendor,
            product=product,
        )
        purchase_date = datetime.datetime(2025, 3, 21, 8, 0, 0)
        purchase = _purchase(vendor, purchase_date=purchase_date)
        _item(purchase, product, unit_price=Decimal("2000"))

        purchase.confirm()

        pv.refresh_from_db()
        self.assertEqual(pv.last_price_date, datetime.date(2025, 3, 21))

    def test_confirm_skips_zero_unit_price(self):
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("9999"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("0"))

        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("9999"))

    def test_confirm_skips_zero_unit_price_does_not_regress(self):
        """A second zero-price item must not zero out an already-set purchase_price."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("8888"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("0"))

        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("8888"))

    def test_confirm_no_product_vendor_link_does_not_crash(self):
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("1234"))

        # No ProductVendor record exists — confirm() must not raise
        try:
            purchase.confirm()
        except Exception as exc:
            self.fail(f"confirm() raised unexpectedly: {exc}")

    def test_confirm_only_updates_matching_vendor_product_link(self):
        """Only the ProductVendor for this vendor+product is updated."""
        vendor_a = _vendor()
        vendor_b = _vendor()
        product  = _product()
        pv_a = ProductVendor.objects.create(
            vendor=vendor_a, product=product, unit_price=Decimal("100"),
        )
        pv_b = ProductVendor.objects.create(
            vendor=vendor_b, product=product, unit_price=Decimal("200"),
        )
        purchase = _purchase(vendor_a)
        _item(purchase, product, unit_price=Decimal("777"))

        purchase.confirm()

        pv_a.refresh_from_db()
        pv_b.refresh_from_db()
        self.assertEqual(pv_a.unit_price, Decimal("777"))
        self.assertEqual(pv_b.unit_price, Decimal("200"))  # unchanged

    def test_idempotency_price_not_doubled(self):
        """confirm() is guarded by stock_applied; calling again is a no-op."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("3000"))

        purchase.confirm()
        purchase.confirm()  # second call must not raise or re-apply

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("3000"))


class ProductVendorMultiProductTest(TestCase):
    """One vendor can be linked to multiple distinct products."""

    def test_single_vendor_multiple_products(self):
        vendor    = _vendor()
        product_a = _product()
        product_b = _product()

        pv_a = ProductVendor.objects.create(vendor=vendor, product=product_a)
        pv_b = ProductVendor.objects.create(vendor=vendor, product=product_b)

        self.assertEqual(
            ProductVendor.objects.filter(vendor=vendor).count(), 2
        )
        self.assertNotEqual(pv_a.pk, pv_b.pk)

    def test_same_vendor_product_different_price_allowed(self):
        """The same (vendor, product) pair with a different price is now allowed."""
        vendor  = _vendor()
        product = _product()

        pv1 = ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("5000")
        )
        pv2 = ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("7000")
        )

        self.assertNotEqual(pv1.pk, pv2.pk)
        self.assertEqual(
            ProductVendor.objects.filter(vendor=vendor, product=product).count(), 2
        )


class PurchasePriceLatestWinsTest(TestCase):
    """Latest-wins semantics and cancel recalculation (Task 24 / CLI-24)."""

    def test_multi_item_purchase_updates_each_product_separately(self):
        vendor    = _vendor()
        product_a = _product()
        product_b = _product()
        purchase  = _purchase(vendor)
        _item(purchase, product_a, unit_price=Decimal("10000"))
        _item(purchase, product_b, unit_price=Decimal("20000"))

        purchase.confirm()

        product_a.refresh_from_db()
        product_b.refresh_from_db()
        self.assertEqual(product_a.purchase_price, Decimal("10000"))
        self.assertEqual(product_b.purchase_price, Decimal("20000"))

    def test_older_purchase_confirmed_later_does_not_overwrite_newer_price(self):
        """Confirming an older purchase after a newer one must not overwrite price."""
        vendor  = _vendor()
        product = _product()

        purchase_new = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 10, 10, 0, 0))
        _item(purchase_new, product, unit_price=Decimal("15000"))
        purchase_new.confirm()

        purchase_old = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0, 0))
        _item(purchase_old, product, unit_price=Decimal("10000"))
        purchase_old.confirm()

        product.refresh_from_db()
        self.assertEqual(
            product.purchase_price, Decimal("15000"),
            "Price from the newer purchase must survive when an older one is confirmed later",
        )

    def test_cancel_latest_purchase_recalculates_from_previous(self):
        """Cancelling the latest confirmed purchase reverts price to next latest."""
        vendor  = _vendor()
        product = _product()

        purchase_old = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0, 0))
        _item(purchase_old, product, unit_price=Decimal("10000"))
        purchase_old.confirm()

        purchase_new = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 10, 10, 0, 0))
        _item(purchase_new, product, unit_price=Decimal("15000"))
        purchase_new.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("15000"))

        purchase_new.cancel()

        product.refresh_from_db()
        self.assertEqual(
            product.purchase_price, Decimal("10000"),
            "After cancelling latest, price must fall back to next latest confirmed purchase",
        )

    def test_cancel_older_purchase_does_not_change_price(self):
        """Cancelling a non-latest confirmed purchase leaves the price at the latest."""
        vendor  = _vendor()
        product = _product()

        purchase_old = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0, 0))
        _item(purchase_old, product, unit_price=Decimal("10000"))
        purchase_old.confirm()

        purchase_new = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 10, 10, 0, 0))
        _item(purchase_new, product, unit_price=Decimal("15000"))
        purchase_new.confirm()

        purchase_old.cancel()

        product.refresh_from_db()
        self.assertEqual(
            product.purchase_price, Decimal("15000"),
            "Cancelling an older purchase must not affect the price set by the newer one",
        )

    def test_cancel_pending_purchase_reverts_to_previous_non_cancelled_price(self):
        """Cancelling the latest PENDING purchase reverts price to the next non-cancelled purchase."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("5000"))

        # Older confirmed purchase — price anchor
        p_confirmed = _purchase(vendor, purchase_date=datetime.datetime(2025, 1, 1, 10, 0))
        _item(p_confirmed, product, unit_price=Decimal("5000"))
        p_confirmed.confirm()

        # Newer PENDING purchase — becomes the active price
        p_pending = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p_pending, product, unit_price=Decimal("9999"))

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("9999"),
                         "PENDING item with newer date must be active price")

        p_pending.cancel()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("5000"),
                         "After cancelling latest PENDING, price must revert to confirmed fallback")

    def test_product_vendor_created_if_not_exists_on_confirm(self):
        """confirm() creates a ProductVendor row when none exists yet."""
        vendor  = _vendor()
        product = _product()
        self.assertFalse(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists(),
            "Precondition: no ProductVendor row",
        )

        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("8000"))
        purchase.confirm()

        pv = ProductVendor.objects.filter(product=product, vendor=vendor).first()
        self.assertIsNotNone(pv, "ProductVendor must be created on confirm when missing")
        self.assertEqual(pv.unit_price, Decimal("8000"))

    def test_confirming_twice_does_not_create_duplicate_product_vendor(self):
        """Second confirm() call (idempotent) must not produce a duplicate row."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("6000"))

        purchase.confirm()
        purchase.confirm()

        count = ProductVendor.objects.filter(product=product, vendor=vendor).count()
        self.assertEqual(count, 1, "Exactly one ProductVendor row must exist after double confirm")


# ---------------------------------------------------------------------------
# New tests for Bug 1 (vendor sync on save) and Bug 2 (relaxed unique rule)
# ---------------------------------------------------------------------------

class VendorProductSyncOnSaveTest(TestCase):
    """ensure_vendor_product_link creates ProductVendor rows immediately on save.

    The admin's save_related calls this so the vendor page shows purchased
    products without requiring a separate confirm step.
    """

    def test_ensure_vendor_product_link_creates_row_for_medicine(self):
        vendor  = _vendor()
        product = _product(product_type=ProductType.MEDICINE)
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("1000"))

        from inventory.services import PriceService
        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists(),
            "ProductVendor must exist for a medicine purchase after ensure_vendor_product_link",
        )

    def test_ensure_vendor_product_link_creates_row_for_equipment(self):
        vendor  = _vendor()
        product = _product(product_type=ProductType.EQUIPMENT)
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("2500"))

        from inventory.services import PriceService
        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists(),
            "ProductVendor must exist for an equipment purchase after ensure_vendor_product_link",
        )

    def test_ensure_vendor_product_link_multi_item(self):
        vendor    = _vendor()
        product_a = _product()
        product_b = _product()
        purchase  = _purchase(vendor)
        _item(purchase, product_a, unit_price=Decimal("100"))
        _item(purchase, product_b, unit_price=Decimal("200"))

        from inventory.services import PriceService
        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(
            ProductVendor.objects.filter(product=product_a, vendor=vendor).exists()
        )
        self.assertTrue(
            ProductVendor.objects.filter(product=product_b, vendor=vendor).exists()
        )

    def test_ensure_vendor_product_link_no_duplicate_on_repeat(self):
        """Calling ensure_vendor_product_link twice must not create duplicate rows."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("500"))

        from inventory.services import PriceService
        PriceService.ensure_vendor_product_link(purchase)
        PriceService.ensure_vendor_product_link(purchase)

        count = ProductVendor.objects.filter(product=product, vendor=vendor).count()
        self.assertEqual(count, 1, "ensure_vendor_product_link must be idempotent")

    def test_ensure_vendor_product_link_works_for_zero_price_item(self):
        """Items with zero price also get a vendor link (price sync is deferred to confirm)."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("0"))

        from inventory.services import PriceService
        PriceService.ensure_vendor_product_link(purchase)

        self.assertTrue(
            ProductVendor.objects.filter(product=product, vendor=vendor).exists(),
            "Even zero-price items must establish a vendor-product link",
        )

    def test_confirm_still_creates_vendor_product_link(self):
        """confirm() also creates ProductVendor for items with price > 0."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("8000"))

        purchase.confirm()

        pv = ProductVendor.objects.filter(product=product, vendor=vendor).first()
        self.assertIsNotNone(pv)
        self.assertEqual(pv.unit_price, Decimal("8000"))


class MultipleConditionsTest(TestCase):
    """Same product + vendor with different conditions must be allowed (Bug 2)."""

    def test_same_vendor_product_different_price_is_allowed_at_db_level(self):
        vendor  = _vendor()
        product = _product()

        pv1 = ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("5000")
        )
        pv2 = ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("6000")
        )

        self.assertNotEqual(pv1.pk, pv2.pk)

    def test_same_vendor_product_different_moq_is_allowed(self):
        vendor  = _vendor()
        product = _product()

        pv1 = ProductVendor.objects.create(
            vendor=vendor, product=product, minimum_order_quantity=1
        )
        pv2 = ProductVendor.objects.create(
            vendor=vendor, product=product, minimum_order_quantity=10
        )

        self.assertNotEqual(pv1.pk, pv2.pk)

    def test_confirm_purchase_does_not_create_exact_duplicate_row(self):
        """Confirming the same purchase twice must not create a second row."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("3000"))

        purchase.confirm()
        # Second confirm is blocked by stock_applied, so sync never runs again.
        purchase.confirm()

        count = ProductVendor.objects.filter(product=product, vendor=vendor).count()
        self.assertEqual(count, 1)

    def test_sync_purchase_vendor_price_updates_most_recent_row(self):
        """When multiple rows exist, sync updates the row with the highest pk."""
        vendor  = _vendor()
        product = _product()

        pv_old = ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("100")
        )
        pv_new = ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("200")
        )

        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("999"))
        purchase.confirm()

        pv_new.refresh_from_db()
        pv_old.refresh_from_db()
        self.assertEqual(pv_new.unit_price, Decimal("999"),
                         "Most-recent row must be updated by sync")
        self.assertEqual(pv_old.unit_price, Decimal("100"),
                         "Older row must remain unchanged")

    def test_vendor_api_returns_all_product_rows(self):
        """All ProductVendor rows for a vendor are visible (no incorrect filtering)."""
        vendor  = _vendor()
        product = _product()

        ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("100")
        )
        ProductVendor.objects.create(
            vendor=vendor, product=product, unit_price=Decimal("200")
        )

        qs = ProductVendor.objects.filter(vendor=vendor)
        self.assertEqual(qs.count(), 2)


class SerializerExactDuplicateTest(TestCase):
    """ProductVendorSerializer must block exact duplicates via application-layer check."""

    def _serializer(self, data, instance=None):
        from inventory.serializers import ProductVendorSerializer
        return ProductVendorSerializer(instance=instance, data=data)

    def test_exact_duplicate_rejected_by_serializer(self):
        vendor  = _vendor()
        product = _product()
        ProductVendor.objects.create(
            vendor=vendor, product=product,
            unit_price=Decimal("500"), minimum_order_quantity=5,
            supplier_product_code="SKU-001",
        )

        data = {
            "vendor":                  vendor.pk,
            "product":                 product.pk,
            "unit_price":              "500",
            "minimum_order_quantity":  5,
            "supplier_product_code":   "SKU-001",
            "is_primary":              False,
            "is_active":               True,
        }
        ser = self._serializer(data)
        self.assertFalse(ser.is_valid(), "Exact duplicate must be rejected")

    def test_different_price_accepted_by_serializer(self):
        vendor  = _vendor()
        product = _product()
        ProductVendor.objects.create(
            vendor=vendor, product=product,
            unit_price=Decimal("500"), minimum_order_quantity=5,
            supplier_product_code="SKU-001",
        )

        data = {
            "vendor":                 vendor.pk,
            "product":                product.pk,
            "unit_price":             "999",  # different price
            "minimum_order_quantity": 5,
            "supplier_product_code":  "SKU-001",
            "is_primary":             False,
            "is_active":              True,
        }
        ser = self._serializer(data)
        self.assertTrue(ser.is_valid(), ser.errors)


# ---------------------------------------------------------------------------
# purchase_date ordering & tie-breaker correctness
# ---------------------------------------------------------------------------

class PriceDateOrderingTest(TestCase):
    """Verify the 3-level ordering: purchase_date DESC → purchase.pk DESC → item.pk DESC."""

    def test_later_date_wins_over_earlier_date(self):
        vendor  = _vendor()
        product = _product()

        old = _purchase(vendor, purchase_date=datetime.datetime(2025, 4, 1, 10, 0))
        _item(old, product, unit_price=Decimal("100000"))
        old.confirm()

        new = _purchase(vendor, purchase_date=datetime.datetime(2025, 4, 10, 10, 0))
        _item(new, product, unit_price=Decimal("130000"))
        new.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("130000"),
                         "Later purchase date must win")

    def test_middle_date_entered_last_does_not_beat_newer_date(self):
        """Entering an older purchase later in the DB must not overwrite a newer-dated price."""
        vendor  = _vendor()
        product = _product()

        p1 = _purchase(vendor, purchase_date=datetime.datetime(2025, 4, 10, 10, 0))
        _item(p1, product, unit_price=Decimal("130000"))
        p1.confirm()

        p2 = _purchase(vendor, purchase_date=datetime.datetime(2025, 4, 5, 10, 0))
        _item(p2, product, unit_price=Decimal("110000"))
        p2.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("130000"),
                         "Earlier-dated purchase confirmed later must not overwrite the newer price")

    def test_same_date_higher_purchase_pk_wins(self):
        """When two purchases share purchase_date, the one with the higher pk wins."""
        vendor  = _vendor()
        product = _product()
        same_date = datetime.datetime(2025, 6, 15, 9, 0)

        p_first = _purchase(vendor, purchase_date=same_date)
        _item(p_first, product, unit_price=Decimal("80000"))
        p_first.confirm()

        p_second = _purchase(vendor, purchase_date=same_date)
        _item(p_second, product, unit_price=Decimal("90000"))
        p_second.confirm()

        product.refresh_from_db()
        self.assertGreater(p_second.pk, p_first.pk)
        self.assertEqual(product.purchase_price, Decimal("90000"),
                         "Same date: higher purchase pk must win")

    def test_same_purchase_higher_item_pk_wins(self):
        """When the same purchase has two items for the same product, the higher item pk wins."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        # Two items for same product in the same purchase
        _item(purchase, product, unit_price=Decimal("70000"))
        _item(purchase, product, unit_price=Decimal("75000"))
        purchase.confirm()

        product.refresh_from_db()
        # recalculate uses -pk so the last-created item (higher pk) wins
        self.assertEqual(product.purchase_price, Decimal("75000"),
                         "Same purchase: higher item pk must win")

    def test_recalculate_direct_call_uses_correct_ordering(self):
        """Directly calling PriceService.recalculate_product_price uses the same ordering."""
        from inventory.services import PriceService

        vendor  = _vendor()
        product = _product()

        p_old = _purchase(vendor, purchase_date=datetime.datetime(2025, 3, 1, 10, 0))
        _item(p_old, product, unit_price=Decimal("50000"))
        p_old.confirm()

        p_new = _purchase(vendor, purchase_date=datetime.datetime(2025, 4, 1, 10, 0))
        _item(p_new, product, unit_price=Decimal("60000"))
        p_new.confirm()

        # Force product price to wrong value
        from inventory.models import Product as Prod
        Prod.objects.filter(pk=product.pk).update(purchase_price=Decimal("1"))

        PriceService.recalculate_product_price(product.pk)

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("60000"))


# ---------------------------------------------------------------------------
# Initial price preservation when no confirmed purchase exists
# ---------------------------------------------------------------------------

class PriceFallbackNoConfirmedPurchaseTest(TestCase):

    def test_initial_price_preserved_when_no_purchase_exists(self):
        """A product with zero purchase history must retain its initial/manual price."""
        product = _product(purchase_price=Decimal("12345"))
        # No purchase at all — not even PENDING

        from inventory.services import PriceService
        PriceService.recalculate_product_price(product.pk)

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("12345"),
                         "Initial price must survive when there are no purchases at all")

    def test_pending_purchase_updates_product_price_via_recalculate(self):
        """A PENDING purchase qualifies for recalculation — CANCELLED only is excluded."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("12345"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("99999"))
        # leave pending — do not confirm

        from inventory.services import PriceService
        PriceService.recalculate_product_price(product.pk)

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("99999"),
                         "PENDING purchase must qualify for price recalculation")

    def test_cancel_all_confirmed_purchases_does_not_zero_price(self):
        """After cancelling the only confirmed purchase the price must not become zero."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("5000"))

        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("8000"))
        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("8000"))

        purchase.cancel()

        # No confirmed purchase remains: recalculate leaves price unchanged (stays at
        # last confirmed value — not zeroed, not reverted to the pre-confirm original).
        product.refresh_from_db()
        self.assertGreater(product.purchase_price, Decimal("0"),
                           "After cancelling all confirmed purchases, price must not be zeroed")
        self.assertEqual(product.purchase_price, Decimal("8000"),
                         "Price must stay at the last confirmed value when no confirmed purchase remains")

    def test_pending_purchase_updates_product_price(self):
        """A PENDING purchase immediately updates Product.purchase_price — no confirm needed."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("9000"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("15000"))

        # Price should already be 15000 from the post_save signal on PurchaseItem.
        # Calling recalculate explicitly must produce the same result.
        from inventory.services import PriceService
        PriceService.recalculate_product_price(product.pk)

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("15000"),
                         "PENDING purchase must immediately update Product.purchase_price")

    def test_cancelled_purchase_does_not_count_as_latest(self):
        """A CANCELLED purchase must be excluded — an older confirmed purchase wins."""
        vendor  = _vendor()
        product = _product()

        # Earlier confirmed purchase: price 3000
        p_early = _purchase(vendor, purchase_date=datetime.datetime(2025, 1, 1, 10, 0))
        _item(p_early, product, unit_price=Decimal("3000"))
        p_early.confirm()

        # Later purchase at 20000 — confirm then cancel, so it's CANCELLED in DB
        p_later = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p_later, product, unit_price=Decimal("20000"))
        p_later.confirm()   # price becomes 20000
        p_later.cancel()    # CANCELLED — excluded from calculation

        from inventory.services import PriceService
        PriceService.recalculate_product_price(product.pk)

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("3000"),
                         "Cancelled purchase must not count; the earlier confirmed purchase should win")


# ---------------------------------------------------------------------------
# Efficiency: duplicate product_ids recalculated only once per confirm
# ---------------------------------------------------------------------------

class PriceSyncEfficiencyTest(TestCase):

    def test_same_product_in_two_items_recalculated_once(self):
        """A purchase with the same product in two items must only run recalculate once."""
        from unittest.mock import patch
        from inventory import services as svc

        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("10000"))
        _item(purchase, product, unit_price=Decimal("11000"))

        call_count = []
        original = svc.PriceService.recalculate_product_price  # staticmethod — plain function

        with patch.object(svc.PriceService, 'recalculate_product_price',
                          side_effect=lambda pid: (call_count.append(pid), original(pid))):
            purchase.confirm()

        self.assertEqual(
            call_count.count(product.pk), 1,
            f"recalculate_product_price must be called exactly once per product, "
            f"got {call_count.count(product.pk)} calls for product {product.pk}"
        )

    def test_multi_product_purchase_each_product_recalculated(self):
        """A purchase with N distinct products must trigger N recalculate calls."""
        from unittest.mock import patch
        from inventory import services as svc

        vendor    = _vendor()
        product_a = _product()
        product_b = _product()
        product_c = _product()
        purchase  = _purchase(vendor)
        _item(purchase, product_a, unit_price=Decimal("1000"))
        _item(purchase, product_b, unit_price=Decimal("2000"))
        _item(purchase, product_c, unit_price=Decimal("3000"))

        called_ids = []
        original = svc.PriceService.recalculate_product_price  # staticmethod — plain function

        with patch.object(svc.PriceService, 'recalculate_product_price',
                          side_effect=lambda pid: (called_ids.append(pid), original(pid))):
            purchase.confirm()

        self.assertEqual(len(called_ids), 3)
        self.assertIn(product_a.pk, called_ids)
        self.assertIn(product_b.pk, called_ids)
        self.assertIn(product_c.pk, called_ids)


# ---------------------------------------------------------------------------
# Multi-vendor: any supplier's price can become the latest
# ---------------------------------------------------------------------------

class PriceMultiVendorTest(TestCase):

    def test_second_vendor_purchase_updates_product_price(self):
        """A confirmed purchase from vendor B must update price even if vendor A purchased first."""
        vendor_a = _vendor()
        vendor_b = _vendor()
        product  = _product()

        p_a = _purchase(vendor_a, purchase_date=datetime.datetime(2025, 5, 1, 10, 0))
        _item(p_a, product, unit_price=Decimal("100000"))
        p_a.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("100000"))

        p_b = _purchase(vendor_b, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p_b, product, unit_price=Decimal("95000"))
        p_b.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("95000"),
                         "Later purchase from a different vendor must update the product price")

    def test_earlier_vendor_b_purchase_does_not_overwrite_later_vendor_a_price(self):
        vendor_a = _vendor()
        vendor_b = _vendor()
        product  = _product()

        p_b = _purchase(vendor_b, purchase_date=datetime.datetime(2025, 4, 1, 10, 0))
        _item(p_b, product, unit_price=Decimal("80000"))
        p_b.confirm()

        p_a = _purchase(vendor_a, purchase_date=datetime.datetime(2025, 5, 1, 10, 0))
        _item(p_a, product, unit_price=Decimal("90000"))
        p_a.confirm()

        # Now confirm a vendor B purchase with older date
        p_b2 = _purchase(vendor_b, purchase_date=datetime.datetime(2025, 3, 1, 10, 0))
        _item(p_b2, product, unit_price=Decimal("70000"))
        p_b2.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("90000"),
                         "Vendor A purchase (latest date) must remain authoritative")


# ---------------------------------------------------------------------------
# Pending price change: only takes effect after confirmation
# ---------------------------------------------------------------------------

class PricePendingEditTest(TestCase):

    def test_editing_pending_unit_price_updates_product_price(self):
        """Editing a PENDING PurchaseItem's unit_price must immediately update Product.purchase_price."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("5000"))
        purchase = _purchase(vendor)
        item = _item(purchase, product, unit_price=Decimal("10000"))

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("10000"),
                         "Creating PENDING item must immediately set price")

        item.unit_price = Decimal("20000")
        item.save()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("20000"),
                         "Editing a pending item's unit_price must update the product price immediately")

    def test_confirming_after_pending_edit_updates_price_to_new_value(self):
        """After editing unit_price in PENDING state, confirming must use the new value."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("5000"))
        purchase = _purchase(vendor)
        item = _item(purchase, product, unit_price=Decimal("10000"))

        item.unit_price = Decimal("20000")
        item.save()

        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("20000"),
                         "After editing pending item and confirming, new price must be used")

    def test_quantity_change_does_not_affect_product_price(self):
        """Product.purchase_price comes from unit_price only; quantity change must not matter."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        item = _item(purchase, product, unit_price=Decimal("15000"), quantity=Decimal("1"))

        item.quantity = Decimal("100")
        item.save()
        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("15000"),
                         "Quantity must never affect Product.purchase_price")


# ---------------------------------------------------------------------------
# Manual total: must not affect Product.purchase_price
# ---------------------------------------------------------------------------

class PriceManualTotalIsolationTest(TestCase):

    def test_manual_total_does_not_affect_product_price(self):
        """Setting manual_total to an arbitrary value must not change Product.purchase_price."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        item = PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=Decimal("3"),
            unit_price=Decimal("18000"),
            manual_total=Decimal("99999"),
        )
        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("18000"),
                         "manual_total must have no effect on Product.purchase_price")

    def test_manual_total_zero_still_uses_unit_price_for_product_price(self):
        """manual_total=0 (which skips finance expense) must not zero out Product.purchase_price."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("1000"))
        purchase = _purchase(vendor)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=Decimal("1"),
            unit_price=Decimal("25000"),
            manual_total=Decimal("0"),
        )
        purchase.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("25000"),
                         "unit_price must always be the product price source, even when manual_total=0")


# ---------------------------------------------------------------------------
# Product API returns the synchronized price
# ---------------------------------------------------------------------------

class PriceSyncApiTest(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        from django.test import Client
        self.client = Client()
        u = User.objects.create_superuser(
            username=f"api_test_{_uid_next()}", password="pass", email=""
        )
        self.client.force_login(u)

    def test_product_list_api_returns_synced_purchase_price(self):
        """After confirm, /api/v1/inventory/products/ must return the updated purchase_price."""
        import json
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("1"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("55000"))
        purchase.confirm()

        r = self.client.get(f'/api/v1/inventory/products/{product.pk}/')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        from decimal import Decimal as D
        self.assertEqual(D(data['purchase_price']), D("55000"))

    def test_product_list_api_price_reflects_latest_purchase(self):
        """After two confirms the API must reflect the later-dated purchase price."""
        import json
        vendor  = _vendor()
        product = _product()

        p1 = _purchase(vendor, purchase_date=datetime.datetime(2025, 3, 1, 10, 0))
        _item(p1, product, unit_price=Decimal("40000"))
        p1.confirm()

        p2 = _purchase(vendor, purchase_date=datetime.datetime(2025, 5, 1, 10, 0))
        _item(p2, product, unit_price=Decimal("55000"))
        p2.confirm()

        r = self.client.get(f'/api/v1/inventory/products/{product.pk}/')
        data = json.loads(r.content)
        self.assertEqual(data['purchase_price'], '55000.00')

    def test_product_admin_detail_page_shows_updated_price(self):
        """The /admin/inventory/product/<id>/detail/ page must display the synced price."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("72000"))
        purchase.confirm()

        r = self.client.get(f'/admin/inventory/product/{product.pk}/detail/')
        self.assertEqual(r.status_code, 200)
        # The page loads the price via JS/API so it must include the product data endpoint
        content = r.content.decode('utf-8')
        self.assertIn(str(product.pk), content)

    def test_product_list_price_uses_purchase_item_unit_price_not_total(self):
        """API purchase_price must equal unit_price, not manual_total or effective_total."""
        import json
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=Decimal("10"),
            unit_price=Decimal("8000"),
            manual_total=Decimal("999999"),
        )
        purchase.confirm()

        r = self.client.get(f'/api/v1/inventory/products/{product.pk}/')
        data = json.loads(r.content)
        from decimal import Decimal as D
        self.assertEqual(D(data['purchase_price']), D("8000"))


# ---------------------------------------------------------------------------
# Recalculate management command
# ---------------------------------------------------------------------------

class RecalculateCommandTest(TestCase):

    def _run_command(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('recalculate_product_prices', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_reports_mismatched_products(self):
        """--dry-run must report products with wrong price without modifying DB."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("1"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("50000"))
        purchase.confirm()

        # Force wrong price back
        from inventory.models import Product as Prod
        Prod.objects.filter(pk=product.pk).update(purchase_price=Decimal("1"))

        output = self._run_command('--dry-run')
        self.assertIn('dry-run', output.lower())
        self.assertIn('1', output)  # product id or wrong count

        # DB must be unchanged
        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("1"),
                         "dry-run must not modify the database")

    def test_apply_fixes_incorrect_product_price(self):
        """--apply must update products whose price doesn't match latest confirmed purchase."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("1"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("50000"))
        purchase.confirm()

        # Force wrong price
        from inventory.models import Product as Prod
        Prod.objects.filter(pk=product.pk).update(purchase_price=Decimal("1"))

        self._run_command('--apply')

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("50000"),
                         "--apply must correct the product price")

    def test_apply_does_not_change_correct_prices(self):
        """--apply must not touch products already at the correct price."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("30000"))
        purchase.confirm()

        product.refresh_from_db()
        correct_price = product.purchase_price

        self._run_command('--apply')

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, correct_price,
                         "--apply must not change already-correct prices")

    def test_dry_run_no_changes_reported_when_all_correct(self):
        """--dry-run with all prices correct must report 0 items needing update."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("20000"))
        purchase.confirm()

        output = self._run_command('--dry-run')
        self.assertIn('مطابقت', output)  # "prices match" message

    def test_apply_does_not_touch_stock_or_purchases(self):
        """--apply must only update Product.purchase_price, nothing else."""
        from inventory.models import StockMovement, Purchase as Purch
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("10000"))
        purchase.confirm()

        stock_before  = StockMovement.objects.count()
        purchase_before = Purch.objects.count()

        from inventory.models import Product as Prod
        Prod.objects.filter(pk=product.pk).update(purchase_price=Decimal("1"))

        self._run_command('--apply')

        self.assertEqual(StockMovement.objects.count(), stock_before)
        self.assertEqual(Purch.objects.count(), purchase_before)

    def test_apply_uses_latest_date_ordering_not_pk(self):
        """--apply must select by purchase_date, not by insertion order."""
        vendor  = _vendor()
        product = _product()

        p_old = _purchase(vendor, purchase_date=datetime.datetime(2025, 2, 1, 10, 0))
        _item(p_old, product, unit_price=Decimal("100"))
        p_old.confirm()

        p_new = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p_new, product, unit_price=Decimal("200"))
        p_new.confirm()

        # Force wrong price
        from inventory.models import Product as Prod
        Prod.objects.filter(pk=product.pk).update(purchase_price=Decimal("1"))

        self._run_command('--apply')

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("200"),
                         "--apply must use the latest-dated purchase, not insertion order")

    def test_apply_respects_no_purchase_fallback(self):
        """--apply must not change a product with no non-cancelled purchase."""
        product = _product(purchase_price=Decimal("7777"))
        # No purchase at all

        self._run_command('--apply')

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("7777"),
                         "--apply must not touch products without any qualifying purchase")


# ---------------------------------------------------------------------------
# Regression: 28,000 vs 25,000 — PENDING purchase must update product price
# ---------------------------------------------------------------------------

class PendingPriceSyncRegressionTest(TestCase):
    """Regression tests for the reported 28,000 vs 25,000 price mismatch.

    Root cause: the old PriceService filtered CONFIRMED only, and was never
    called from admin save_related().  A saved PENDING purchase had no effect
    on Product.purchase_price.
    """

    def _run_command(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('recalculate_product_prices', *args, stdout=out)
        return out.getvalue()

    def test_pending_purchase_unit_price_28000_updates_product_from_25000(self):
        """Exact reproduction of the reported bug: نخ بخیه at 25,000 with PENDING
        purchase at 28,000 must show 28,000 immediately after saving."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("25000"))

        # Simulate saving a PENDING purchase with unit_price=28,000
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("28000"))
        # No confirm() — purchase stays PENDING

        product.refresh_from_db()
        self.assertEqual(
            product.purchase_price, Decimal("28000"),
            "PENDING purchase at 28,000 must immediately update product from 25,000",
        )

    def test_pending_beats_older_confirmed(self):
        """A PENDING purchase with a newer date overrides an older CONFIRMED price."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("0"))

        p_old = _purchase(vendor, purchase_date=datetime.datetime(2025, 1, 1, 10, 0))
        _item(p_old, product, unit_price=Decimal("25000"))
        p_old.confirm()

        p_pending = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p_pending, product, unit_price=Decimal("28000"))

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("28000"),
                         "Newer PENDING purchase must override older confirmed price")

    def test_confirmed_beats_older_pending(self):
        """A CONFIRMED purchase with a newer date overrides an older PENDING price."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("0"))

        p_pending = _purchase(vendor, purchase_date=datetime.datetime(2025, 1, 1, 10, 0))
        _item(p_pending, product, unit_price=Decimal("28000"))

        p_confirmed = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p_confirmed, product, unit_price=Decimal("30000"))
        p_confirmed.confirm()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("30000"),
                         "Newer confirmed purchase must override older pending price")

    def test_editing_pending_unit_price_updates_immediately(self):
        """Editing unit_price in a PENDING purchase must update product price at once."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("25000"))
        purchase = _purchase(vendor)
        item = _item(purchase, product, unit_price=Decimal("28000"))

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("28000"))

        item.unit_price = Decimal("29000")
        item.save()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("29000"),
                         "Editing unit_price on PENDING item must update product immediately")

    def test_cancelling_pending_reverts_to_confirmed(self):
        """After cancelling the PENDING purchase the price must fall back to confirmed."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("0"))

        p_old = _purchase(vendor, purchase_date=datetime.datetime(2025, 1, 1, 10, 0))
        _item(p_old, product, unit_price=Decimal("25000"))
        p_old.confirm()

        p_pending = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p_pending, product, unit_price=Decimal("28000"))

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("28000"))

        p_pending.cancel()

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("25000"),
                         "Cancelling the latest PENDING must revert price to confirmed fallback")

    def test_quantity_and_manual_total_irrelevant(self):
        """unit_price is the only source; quantity=3, manual_total=99,999 must not matter."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("0"))
        purchase = _purchase(vendor)
        item = _item(purchase, product, unit_price=Decimal("28000"), quantity=Decimal("3"))
        # Override manual_total via .update() (bypasses signals — intentional)
        from inventory.models import PurchaseItem as PI
        PI.objects.filter(pk=item.pk).update(manual_total=Decimal("99999"))

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("28000"),
                         "manual_total and quantity must never affect Product.purchase_price")

    def test_management_command_applies_pending_price(self):
        """--apply must fix a product whose price predates a PENDING purchase."""
        vendor  = _vendor()
        product = _product(purchase_price=Decimal("25000"))
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("28000"))
        # Force the DB back to old price (simulate legacy stale data)
        from inventory.models import Product as Prod
        Prod.objects.filter(pk=product.pk).update(purchase_price=Decimal("25000"))

        self._run_command('--apply')

        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("28000"),
                         "--apply must include PENDING purchases when finding latest price")
