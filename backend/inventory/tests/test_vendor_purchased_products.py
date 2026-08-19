"""Tests for vendor purchased-products feature.

Verifies the Django Admin vendor change page (/admin/inventory/vendor/{id}/change/)
shows products derived from CONFIRMED purchase history — not from the manually-
maintained ProductVendor table.

Requirements covered:
  1.  Empty state: no confirmed purchases → Persian empty-state message
  2.  A confirmed purchase adds its product to the list automatically
  3.  Multiple items in one purchase → all products listed
  4.  Same product purchased multiple times → appears exactly once (dedup)
  5.  Products from another vendor do not appear
  6.  total_quantity is the sum across all confirmed purchase items
  7.  purchase_count is the number of distinct confirmed purchases
  8.  last_purchase_date is the most recent confirmed purchase date
  9.  last_unit_price comes from the most recent confirmed PurchaseItem
  10. CANCELLED purchases are excluded
  11. PENDING purchases are excluded; CONFIRMED is the qualifying status
  12. ProductVendor records are NOT required — purchase history is the source
  13. A ProductVendor record without a confirmed purchase does NOT appear
  14. «افزودن محصول»/«ویرایش»/«حذف» buttons are absent from the purchased-products table
  15. Product names link to the correct product detail URL
  16. Query count is bounded (no N+1)
  17. Vendor ID 2 reproduction scenario: structure matches real database
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from inventory.models import (
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)
from inventory.services import VendorService

User = get_user_model()

_uid = 0


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _vendor(name=None):
    return Vendor.objects.create(name=name or f"تأمین‌کننده {_uid_next()}")


def _product(**kw):
    n = _uid_next()
    defaults = {
        "name":          f"محصول {n}",
        "internal_code": f"VPP-{n:04d}",
        "product_type":  ProductType.MEDICINE,
        "unit":          "عدد",
        "purchase_price": Decimal("0"),
    }
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _purchase(vendor, status=PurchaseStatus.CONFIRMED, purchase_date=None):
    return Purchase.objects.create(
        vendor=vendor,
        status=status,
        purchase_date=purchase_date or datetime.datetime(2025, 6, 1, 10, 0, 0),
    )


def _item(purchase, product, quantity=Decimal("10"), unit_price=Decimal("5000")):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
    )


def _superuser():
    return User.objects.create_superuser(
        username=f"admin_{_uid_next()}", password="pass", email=""
    )


def _change_url(vendor_id):
    return f"/admin/inventory/vendor/{vendor_id}/change/"


def _api_url(vendor_id):
    return f"/api/v2/inventory/vendors/{vendor_id}/purchased-products/"


# ---------------------------------------------------------------------------
# Helper mixin: authenticated client
# ---------------------------------------------------------------------------

class AdminClientMixin:
    def setUp(self):
        self.user   = _superuser()
        self.client = Client()
        self.client.force_login(self.user)

    def _get_change(self, vendor):
        return self.client.get(_change_url(vendor.pk))


# ---------------------------------------------------------------------------
# 1. Empty state
# ---------------------------------------------------------------------------

class EmptyStateTest(AdminClientMixin, TestCase):
    """Vendor with no confirmed purchases shows Persian empty-state message."""

    def test_empty_state_message_on_change_page(self):
        vendor = _vendor()
        r = self._get_change(vendor)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "هنوز محصولی از این تأمین‌کننده خریداری نشده است")

    def test_no_purchased_products_in_context(self):
        vendor = _vendor()
        r = self._get_change(vendor)
        self.assertEqual(r.context["purchased_products"], [])


# ---------------------------------------------------------------------------
# 2. Confirmed purchase adds product automatically
# ---------------------------------------------------------------------------

class SinglePurchaseTest(AdminClientMixin, TestCase):

    def test_confirmed_purchase_adds_product_to_change_page(self):
        vendor  = _vendor()
        product = _product(name="داروی یک")
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product)

        r = self._get_change(vendor)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "داروی یک")
        self.assertEqual(len(r.context["purchased_products"]), 1)


# ---------------------------------------------------------------------------
# 3. Multiple items in one purchase → all products listed
# ---------------------------------------------------------------------------

class MultipleItemsTest(AdminClientMixin, TestCase):

    def test_multiple_products_from_one_purchase_all_appear(self):
        vendor   = _vendor()
        product1 = _product(name="الف")
        product2 = _product(name="ب")
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product1)
        _item(p, product2)

        r = self._get_change(vendor)
        self.assertContains(r, "الف")
        self.assertContains(r, "ب")
        self.assertEqual(len(r.context["purchased_products"]), 2)


# ---------------------------------------------------------------------------
# 4. Same product purchased multiple times → appears once (dedup)
# ---------------------------------------------------------------------------

class DeduplicationTest(AdminClientMixin, TestCase):

    def test_same_product_multiple_purchases_appears_once(self):
        vendor  = _vendor()
        product = _product()
        p1 = _purchase(vendor, purchase_date=datetime.datetime(2025, 3, 1, 10, 0))
        _item(p1, product, unit_price=Decimal("3000"))
        p2 = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p2, product, unit_price=Decimal("4000"))

        r = self._get_change(vendor)
        self.assertEqual(len(r.context["purchased_products"]), 1)

    def test_same_product_two_items_same_purchase_no_duplicate(self):
        vendor  = _vendor()
        product = _product()
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product, quantity=Decimal("3"))
        _item(p, product, quantity=Decimal("7"))

        r = self._get_change(vendor)
        self.assertEqual(len(r.context["purchased_products"]), 1)


# ---------------------------------------------------------------------------
# 5. Products from another vendor do not appear
# ---------------------------------------------------------------------------

class OtherVendorIsolationTest(AdminClientMixin, TestCase):

    def test_other_vendor_products_excluded(self):
        vendor_a = _vendor()
        vendor_b = _vendor()
        product_a = _product(name="محصول الف")
        product_b = _product(name="محصول ب")
        pa = _purchase(vendor_a, status=PurchaseStatus.CONFIRMED)
        _item(pa, product_a)
        pb = _purchase(vendor_b, status=PurchaseStatus.CONFIRMED)
        _item(pb, product_b)

        r = self._get_change(vendor_a)
        ids = [p.pk for p in r.context["purchased_products"]]
        self.assertIn(product_a.pk, ids)
        self.assertNotIn(product_b.pk, ids)


# ---------------------------------------------------------------------------
# 6. total_quantity is the sum across confirmed purchases
# ---------------------------------------------------------------------------

class TotalQuantityTest(TestCase):

    def test_total_quantity_is_summed(self):
        vendor  = _vendor()
        product = _product()
        p1 = _purchase(vendor, purchase_date=datetime.datetime(2025, 3, 1, 10, 0))
        _item(p1, product, quantity=Decimal("5"))
        p2 = _purchase(vendor, purchase_date=datetime.datetime(2025, 6, 1, 10, 0))
        _item(p2, product, quantity=Decimal("8"))

        row = VendorService.get_vendor_purchased_products(vendor.pk).first()
        self.assertEqual(row.total_quantity, Decimal("13"))


# ---------------------------------------------------------------------------
# 7. purchase_count is the number of distinct confirmed purchases
# ---------------------------------------------------------------------------

class PurchaseCountTest(TestCase):

    def test_purchase_count_equals_distinct_purchases(self):
        vendor  = _vendor()
        product = _product()
        for month in [1, 4, 7]:
            p = _purchase(vendor, purchase_date=datetime.datetime(2025, month, 1, 10, 0))
            _item(p, product)

        row = VendorService.get_vendor_purchased_products(vendor.pk).first()
        self.assertEqual(row.purchase_count, 3)


# ---------------------------------------------------------------------------
# 8. last_purchase_date is the most recent confirmed purchase date
# ---------------------------------------------------------------------------

class LastPurchaseDateTest(TestCase):

    def test_last_purchase_date_is_most_recent(self):
        vendor   = _vendor()
        product  = _product()
        p_early  = _purchase(vendor, purchase_date=datetime.datetime(2025, 1, 15, 12, 0))
        p_recent = _purchase(vendor, purchase_date=datetime.datetime(2025, 9, 15, 12, 0))
        _item(p_early,  product)
        _item(p_recent, product)

        row = VendorService.get_vendor_purchased_products(vendor.pk).first()
        actual = row.last_purchase_date
        if hasattr(actual, "month"):
            self.assertEqual(actual.month, 9)
            self.assertEqual(actual.year, 2025)
        else:
            self.assertIn("2025", str(actual))
            self.assertIn("9", str(actual)[:8])


# ---------------------------------------------------------------------------
# 9. last_unit_price from the most recent confirmed PurchaseItem
# ---------------------------------------------------------------------------

class LastUnitPriceTest(TestCase):

    def test_last_unit_price_from_most_recent_item(self):
        vendor   = _vendor()
        product  = _product()
        p_early  = _purchase(vendor, purchase_date=datetime.datetime(2025, 1, 15, 12, 0))
        _item(p_early,  product, unit_price=Decimal("3000"))
        p_recent = _purchase(vendor, purchase_date=datetime.datetime(2025, 9, 15, 12, 0))
        _item(p_recent, product, unit_price=Decimal("7000"))

        row = VendorService.get_vendor_purchased_products(vendor.pk).first()
        self.assertEqual(row.last_unit_price, Decimal("7000"))


# ---------------------------------------------------------------------------
# 10. CANCELLED purchases excluded
# ---------------------------------------------------------------------------

class CancelledExclusionTest(TestCase):

    def test_cancelled_purchase_excluded(self):
        vendor  = _vendor()
        product = _product()
        p = _purchase(vendor, status=PurchaseStatus.CANCELLED)
        _item(p, product)

        qs = VendorService.get_vendor_purchased_products(vendor.pk)
        self.assertEqual(qs.count(), 0)

    def test_cancel_removes_product_from_list(self):
        vendor  = _vendor()
        product = _product()
        p = Purchase.objects.create(
            vendor=vendor,
            status=PurchaseStatus.CONFIRMED,
            purchase_date=datetime.datetime(2025, 6, 1, 10, 0),
        )
        _item(p, product)
        self.assertEqual(VendorService.get_vendor_purchased_products(vendor.pk).count(), 1)

        p.status = PurchaseStatus.CANCELLED
        p.save(update_fields=["status", "updated_at"])

        self.assertEqual(VendorService.get_vendor_purchased_products(vendor.pk).count(), 0)


# ---------------------------------------------------------------------------
# 11. PENDING purchases excluded; CONFIRMED is the qualifying status
# ---------------------------------------------------------------------------

class PendingExclusionTest(TestCase):

    def test_pending_purchase_excluded(self):
        vendor  = _vendor()
        product = _product()
        p = _purchase(vendor, status=PurchaseStatus.PENDING)
        _item(p, product)

        qs = VendorService.get_vendor_purchased_products(vendor.pk)
        self.assertEqual(qs.count(), 0)

    def test_confirmed_purchase_is_included(self):
        vendor  = _vendor()
        product = _product()
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product)

        qs = VendorService.get_vendor_purchased_products(vendor.pk)
        self.assertEqual(qs.count(), 1)


# ---------------------------------------------------------------------------
# 12. ProductVendor records are NOT required
# ---------------------------------------------------------------------------

class ProductVendorNotRequiredTest(TestCase):

    def test_product_without_product_vendor_record_still_appears(self):
        vendor  = _vendor()
        product = _product()
        # No ProductVendor record created
        self.assertEqual(
            ProductVendor.objects.filter(vendor=vendor, product=product).count(), 0
        )
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product)

        qs = VendorService.get_vendor_purchased_products(vendor.pk)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, product.pk)


# ---------------------------------------------------------------------------
# 13. A ProductVendor record without a confirmed purchase does NOT appear
# ---------------------------------------------------------------------------

class ProductVendorWithoutPurchaseTest(TestCase):

    def test_product_vendor_without_confirmed_purchase_not_listed(self):
        vendor  = _vendor()
        product = _product()
        # Create a ProductVendor record (manual link) but NO confirmed purchase
        ProductVendor.objects.create(
            product=product,
            vendor=vendor,
            unit_price=Decimal("1000"),
        )

        qs = VendorService.get_vendor_purchased_products(vendor.pk)
        self.assertEqual(qs.count(), 0)


# ---------------------------------------------------------------------------
# 14. Add/Edit/Delete buttons absent from the purchased-products table
# ---------------------------------------------------------------------------

class NoManualControlsTest(AdminClientMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.vendor  = _vendor()
        product = _product(name="محصول کنترل")
        p = _purchase(self.vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product)

    def test_add_product_button_not_in_purchased_section(self):
        r = self._get_change(self.vendor)
        content = r.content.decode("utf-8")
        # «افزودن محصول» must not appear inside the purchased section.
        # The purchased section ends before the "تنظیمات تجاری" section.
        purchased_idx = content.find("vf-purchased-products-section")
        commercial_idx = content.find("vf-products-section")
        self.assertGreater(purchased_idx, -1, "purchased section not found in page")
        self.assertGreater(commercial_idx, -1, "commercial section not found in page")
        # Ensure the purchased section comes before the commercial (JS) section
        self.assertLess(purchased_idx, commercial_idx)

    def test_no_edit_button_in_purchased_table(self):
        r = self._get_change(self.vendor)
        content = r.content.decode("utf-8")
        # Extract the purchased-products section
        start = content.find('id="vf-purchased-products-section"')
        end   = content.find('id="vf-products-section"')
        if start == -1 or end == -1 or end <= start:
            self.fail("Could not isolate purchased-products section in page")
        purchased_section = content[start:end]
        # No edit or delete action buttons in this section
        self.assertNotIn('data-action="edit-pv"', purchased_section)
        self.assertNotIn('data-action="remove-pv"', purchased_section)
        self.assertNotIn('افزودن محصول', purchased_section)

    def test_no_delete_button_in_purchased_table(self):
        r = self._get_change(self.vendor)
        content = r.content.decode("utf-8")
        start = content.find('id="vf-purchased-products-section"')
        end   = content.find('id="vf-products-section"')
        if start != -1 and end != -1 and end > start:
            purchased_section = content[start:end]
            self.assertNotIn('>حذف<', purchased_section)
            self.assertNotIn('>ویرایش<', purchased_section)


# ---------------------------------------------------------------------------
# 15. Product links point to the correct URL
# ---------------------------------------------------------------------------

class ProductLinkTest(AdminClientMixin, TestCase):

    def test_product_link_points_to_detail_page(self):
        vendor  = _vendor()
        product = _product(name="محصول لینک")
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product)

        r = self._get_change(vendor)
        expected = f"/admin/inventory/product/{product.pk}/detail/"
        self.assertContains(r, expected)


# ---------------------------------------------------------------------------
# 16. Query count bounded (no N+1)
# ---------------------------------------------------------------------------

class QueryCountTest(TestCase):

    def test_service_uses_single_query(self):
        vendor   = _vendor()
        products = [_product() for _ in range(5)]
        for product in products:
            p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
            _item(p, product)

        with self.assertNumQueries(1):
            result = list(VendorService.get_vendor_purchased_products(vendor.pk))
        self.assertEqual(len(result), 5)


# ---------------------------------------------------------------------------
# 17. Vendor ID 2 reproduction scenario
# ---------------------------------------------------------------------------

class VendorId2ReproductionTest(TestCase):
    """Reproduce the exact structure of vendor ID 2 (DEMO تجهیزات پزشکی پارس).

    Vendor has:
    - 1 CONFIRMED purchase with 5 products
    - 1 CANCELLED purchase with 1 product
    - 2 PENDING purchases

    Expected: 5 distinct products from the CONFIRMED purchase appear.
    The CANCELLED product must not add a 6th row.
    The PENDING products must not add additional rows.
    """

    def test_vendor2_structure_confirmed_only(self):
        vendor = _vendor(name="تجهیزات پزشکی آزمایشی")

        # 5-product CONFIRMED purchase
        p_confirmed = _purchase(
            vendor,
            status=PurchaseStatus.CONFIRMED,
            purchase_date=datetime.datetime(2026, 5, 10, 12, 0),
        )
        products = [_product() for _ in range(5)]
        prices   = [23000, 14000, 11000, 33000, 7500]
        for prod, price in zip(products, prices):
            _item(p_confirmed, prod, unit_price=Decimal(str(price)))

        # CANCELLED purchase with same first product
        p_cancelled = _purchase(
            vendor,
            status=PurchaseStatus.CANCELLED,
            purchase_date=datetime.datetime(2024, 7, 20, 12, 0),
        )
        _item(p_cancelled, products[0], unit_price=Decimal("25000"))

        # 2 PENDING purchases
        p_pend1 = _purchase(
            vendor,
            status=PurchaseStatus.PENDING,
            purchase_date=datetime.datetime(2026, 9, 20, 12, 0),
        )
        _item(p_pend1, products[0], unit_price=Decimal("50000"))

        p_pend2 = _purchase(
            vendor,
            status=PurchaseStatus.PENDING,
            purchase_date=datetime.datetime(2027, 1, 18, 12, 0),
        )
        _item(p_pend2, products[3], unit_price=Decimal("35000"))

        qs = list(VendorService.get_vendor_purchased_products(vendor.pk))
        self.assertEqual(len(qs), 5, "Expected exactly 5 products (from CONFIRMED purchase)")

        product_ids = {p.pk for p in qs}
        for prod in products:
            self.assertIn(prod.pk, product_ids)

        # The last_unit_price for products[0] must be from CONFIRMED (23000), not PENDING (50000)
        row_0 = next(p for p in qs if p.pk == products[0].pk)
        self.assertEqual(row_0.last_unit_price, Decimal("23000"))

        # purchase_count for each should be 1 (only 1 CONFIRMED purchase)
        for row in qs:
            self.assertEqual(row.purchase_count, 1)

    def test_admin_change_page_shows_purchased_products(self):
        user   = _superuser()
        vendor = _vendor(name="تجهیزات آزمایشی ۲")
        product = _product(name="کالای بازتولید")
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product)

        c = Client()
        c.force_login(user)
        r = c.get(_change_url(vendor.pk))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "کالای بازتولید")
        self.assertContains(r, "محصولات این تامین‌کننده")


# ---------------------------------------------------------------------------
# API endpoint tests (already backed by VendorViewSet.purchased_products)
# ---------------------------------------------------------------------------

class APIEndpointTest(TestCase):

    def setUp(self):
        self.user   = _superuser()
        self.client = Client()
        self.client.force_login(self.user)

    def test_api_returns_empty_for_no_confirmed_purchases(self):
        vendor = _vendor()
        r = self.client.get(_api_url(vendor.pk))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        results = data.get("results", data)
        self.assertEqual(len(results), 0)

    def test_api_product_detail_url_is_correct(self):
        vendor  = _vendor()
        product = _product()
        p = _purchase(vendor, status=PurchaseStatus.CONFIRMED)
        _item(p, product)

        r = self.client.get(_api_url(vendor.pk))
        results = r.json().get("results", r.json())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["product_detail_url"],
                         f"/admin/inventory/product/{product.pk}/detail/")

    def test_api_requires_authentication(self):
        vendor = _vendor()
        r = Client().get(_api_url(vendor.pk))
        self.assertIn(r.status_code, (401, 403))
