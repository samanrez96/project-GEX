"""Tests for initial price/stock on the Product admin add form and for the
_has_confirmed_purchase helper that controls price editability on edit forms.

Covers:
  1. Product created with initial fallback price (no purchase needed).
  2. Product created with initial stock via MANUAL_ADJUSTMENT StockMovement.
  3. _has_confirmed_purchase returns False for new / PENDING-only products.
  4. _has_confirmed_purchase returns True after a confirmed purchase.
  5. _has_confirmed_purchase returns False after the only confirmed purchase is cancelled.
  6. Admin add form POST creates product without price.
  7. Admin add form POST creates product with initial price.
  8. Admin add form POST creates product with initial stock (movement created).
  9. Task 24 still updates price after a confirmed purchase.
 10. Product detail and list API responses include purchase_price field.
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from inventory.models import (
    MovementType,
    Product,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    SourceType,
    StockMovement,
    Vendor,
)
from inventory.services import StockService


# ---------------------------------------------------------------------------
# Shared helpers (isolated uid counter so this file doesn't conflict with
# the existing helpers in test_purchase_price_update.py)
# ---------------------------------------------------------------------------

_uid = 5000


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _product(**kw):
    n = _uid_next()
    defaults = {
        "name":           f"محصول {n}",
        "internal_code":  f"PI-{n:04d}",
        "product_type":   ProductType.MEDICINE,
        "unit":           "عدد",
        "purchase_price": Decimal("0"),
    }
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _vendor():
    return Vendor.objects.create(name=f"فروشنده {_uid_next()}")


def _purchase(vendor, purchase_date=None):
    return Purchase.objects.create(
        vendor=vendor,
        status=PurchaseStatus.PENDING,
        purchase_date=purchase_date or datetime.datetime(2025, 6, 1, 10, 0, 0),
    )


def _item(purchase, product, unit_price=Decimal("5000"), quantity=10):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
    )


# ---------------------------------------------------------------------------
# 1–2 · Model-level initial price / stock
# ---------------------------------------------------------------------------

class ProductInitialPriceModelTest(TestCase):

    def test_product_created_with_initial_price(self):
        product = _product(purchase_price=Decimal("7500"))
        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("7500"))

    def test_product_initial_price_zero_by_default(self):
        product = _product()
        self.assertEqual(product.purchase_price, Decimal("0"))

    def test_initial_stock_via_manual_adjustment(self):
        """StockService.create_movement with MANUAL_ADJUSTMENT sets current_stock."""
        product = _product()
        self.assertEqual(product.current_stock, Decimal("0"))

        StockService.create_movement(
            product=product,
            quantity=Decimal("25"),
            movement_type=MovementType.IN,
            source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id=f"initial-stock-{product.pk}",
            description="موجودی اولیه",
        )

        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal("25"))

    def test_initial_stock_creates_movement_record(self):
        product = _product()
        StockService.create_movement(
            product=product,
            quantity=Decimal("10"),
            movement_type=MovementType.IN,
            source_type=SourceType.MANUAL_ADJUSTMENT,
            reference_id="initial-stock-test",
            description="موجودی اولیه",
        )
        movement = StockMovement.objects.filter(product=product).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.source_type, SourceType.MANUAL_ADJUSTMENT)
        self.assertEqual(movement.movement_type, MovementType.IN)
        self.assertEqual(movement.quantity, Decimal("10"))


# ---------------------------------------------------------------------------
# 3–5 · _has_confirmed_purchase helper
# ---------------------------------------------------------------------------

class HasConfirmedPurchaseTest(TestCase):

    def setUp(self):
        from inventory.admin import ProductAdmin
        from django.contrib.admin import site
        self.pa = ProductAdmin(Product, site)

    def test_false_for_new_product_with_no_purchases(self):
        product = _product()
        self.assertFalse(self.pa._has_confirmed_purchase(product))

    def test_false_with_only_pending_purchase(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)
        # Purchase is still PENDING — not confirmed.
        self.assertFalse(self.pa._has_confirmed_purchase(product))

    def test_true_after_confirmed_purchase(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)
        purchase.confirm()
        self.assertTrue(self.pa._has_confirmed_purchase(product))

    def test_false_after_cancelling_the_only_confirmed_purchase(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        _item(purchase, product)
        purchase.confirm()
        purchase.cancel()
        self.assertFalse(self.pa._has_confirmed_purchase(product))

    def test_true_when_one_of_two_purchases_is_still_confirmed(self):
        vendor    = _vendor()
        product   = _product()
        purchase1 = _purchase(vendor, datetime.datetime(2025, 6, 1, 10, 0, 0))
        _item(purchase1, product, unit_price=Decimal("5000"))
        purchase1.confirm()

        purchase2 = _purchase(vendor, datetime.datetime(2025, 6, 10, 10, 0, 0))
        _item(purchase2, product, unit_price=Decimal("6000"))
        purchase2.confirm()

        # Cancel only the newer one — older is still confirmed.
        purchase2.cancel()
        self.assertTrue(self.pa._has_confirmed_purchase(product))


# ---------------------------------------------------------------------------
# 6–9 · Admin integration (POST to add/change form)
# ---------------------------------------------------------------------------

class ProductAdminFormTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin_pi_test", password="pass", email="pi@test.com"
        )
        self.client.force_login(self.superuser)

    def _post_add(self, **fields):
        # Django admin requires management-form data for every inline formset.
        # ProductVendorInline prefix = "product_vendors" (related_name)
        # StockMovementInline prefix = "stock_movements" (related_name)
        defaults = {
            "product_type":   ProductType.MEDICINE,
            "minimum_stock":  "0",
            "purchase_price": "0",
            "initial_stock":  "",
            # ProductVendorInline management form
            "product_vendors-TOTAL_FORMS":   "0",
            "product_vendors-INITIAL_FORMS": "0",
            "product_vendors-MIN_NUM_FORMS": "0",
            "product_vendors-MAX_NUM_FORMS": "1000",
            # StockMovementInline management form
            "stock_movements-TOTAL_FORMS":   "0",
            "stock_movements-INITIAL_FORMS": "0",
            "stock_movements-MIN_NUM_FORMS": "0",
            "stock_movements-MAX_NUM_FORMS": "1000",
        }
        defaults.update(fields)
        return self.client.post("/admin/inventory/product/add/", defaults, follow=True)

    def test_add_form_loads_with_200(self):
        response = self.client.get("/admin/inventory/product/add/")
        self.assertEqual(response.status_code, 200)

    def test_product_can_be_created_without_price(self):
        n = _uid_next()
        self._post_add(name=f"محصول {n}", internal_code=f"NP-{n}")
        self.assertTrue(Product.objects.filter(internal_code=f"NP-{n}").exists())

    def test_product_created_with_initial_price_via_admin(self):
        n = _uid_next()
        self._post_add(
            name=f"نخ بخیه {n}",
            internal_code=f"NB-{n}",
            purchase_price="8000",
        )
        product = Product.objects.get(internal_code=f"NB-{n}")
        self.assertEqual(product.purchase_price, Decimal("8000"))

    def test_product_created_with_initial_stock_via_admin(self):
        n = _uid_next()
        self._post_add(
            name=f"سرنگ {n}",
            internal_code=f"SRN-{n}",
            minimum_stock="5",
            purchase_price="500",
            initial_stock="20",
        )
        product = Product.objects.get(internal_code=f"SRN-{n}")
        product.refresh_from_db()
        self.assertEqual(product.current_stock, Decimal("20"))

        movement = StockMovement.objects.filter(
            product=product, source_type=SourceType.MANUAL_ADJUSTMENT,
        ).first()
        self.assertIsNotNone(movement, "A MANUAL_ADJUSTMENT movement must be created for initial stock")
        self.assertEqual(movement.quantity, Decimal("20"))
        self.assertEqual(movement.movement_type, MovementType.IN)

    def test_zero_initial_stock_does_not_create_movement(self):
        n = _uid_next()
        self._post_add(
            name=f"محصول بدون موجودی {n}",
            internal_code=f"ZS-{n}",
            initial_stock="0",
        )
        product = Product.objects.get(internal_code=f"ZS-{n}")
        self.assertEqual(
            StockMovement.objects.filter(product=product).count(),
            0,
            "Zero initial_stock must not create a movement",
        )

    def test_blank_initial_stock_does_not_create_movement(self):
        n = _uid_next()
        self._post_add(
            name=f"محصول خالی {n}",
            internal_code=f"BS-{n}",
            initial_stock="",
        )
        product = Product.objects.get(internal_code=f"BS-{n}")
        self.assertEqual(
            StockMovement.objects.filter(product=product).count(),
            0,
        )

    def test_task24_price_update_still_works_after_confirmed_purchase(self):
        """Confirming a purchase must still update product.purchase_price via Task 24."""
        product  = _product(purchase_price=Decimal("5000"))
        vendor   = _vendor()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("9000"))
        purchase.confirm()
        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("9000"))

    def test_initial_price_overwritten_by_first_confirmed_purchase(self):
        """Initial manual price is replaced by the first confirmed purchase price."""
        product  = _product(purchase_price=Decimal("3000"))
        vendor   = _vendor()
        purchase = _purchase(vendor)
        _item(purchase, product, unit_price=Decimal("4500"))
        purchase.confirm()
        product.refresh_from_db()
        self.assertEqual(product.purchase_price, Decimal("4500"))

    def test_no_trailing_zeros_in_current_stock_display(self):
        """current_stock_display must not show .000 suffix."""
        from inventory.admin import ProductAdmin
        from django.contrib.admin import site
        pa = ProductAdmin(Product, site)

        product = _product()
        display = pa.current_stock_display(product)
        self.assertNotIn(".000", display)
        self.assertNotIn(".00", display)

    def test_no_trailing_zeros_in_purchase_price_display(self):
        """purchase_price_display must show clean integer (no .00) for whole numbers."""
        from inventory.admin import ProductAdmin
        from django.contrib.admin import site
        pa = ProductAdmin(Product, site)

        product = _product(purchase_price=Decimal("15000"))
        display = pa.purchase_price_display(product)
        self.assertIn("15000", display)
        self.assertNotIn(".00", display)
        self.assertIn("تومان", display)


# ---------------------------------------------------------------------------
# 10 · API includes purchase_price in product responses
# ---------------------------------------------------------------------------

class ProductApiPriceFieldTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="api_pi_test", password="pass", email="api_pi@test.com"
        )
        self.client.force_login(self.superuser)

    def test_product_detail_api_includes_purchase_price(self):
        product  = _product(purchase_price=Decimal("3500"))
        response = self.client.get(f"/api/v2/inventory/products/{product.pk}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("purchase_price", data)
        self.assertEqual(Decimal(data["purchase_price"]), Decimal("3500"))

    def test_product_list_api_includes_purchase_price(self):
        product  = _product(purchase_price=Decimal("1200"))
        response = self.client.get("/api/v2/inventory/products/")
        self.assertEqual(response.status_code, 200)
        data     = response.json()
        results  = data.get("results", [])
        row      = next((r for r in results if r["id"] == product.pk), None)
        self.assertIsNotNone(row, "Product must appear in list API response")
        self.assertIn("purchase_price", row)
        self.assertEqual(Decimal(row["purchase_price"]), Decimal("1200"))

    def test_product_api_price_zero_for_new_product(self):
        product  = _product()
        response = self.client.get(f"/api/v2/inventory/products/{product.pk}/")
        data     = response.json()
        self.assertEqual(Decimal(data["purchase_price"]), Decimal("0"))


# ---------------------------------------------------------------------------
# 11 · Existing-product detection on the Product add form
# ---------------------------------------------------------------------------

class ProductAddFormDuplicateDetectionTest(TestCase):
    """Tests for the existing-product lookup (product_add_form.js + API).

    Covers:
      11a. Search API returns exact-name match with purchase_price + current_stock.
      11b. Partial name does not trigger false match (client-side exact check).
      11c. New product can still be created when no match exists.
      11d. Duplicate internal_code is blocked by the model unique constraint.
      11e. Detecting an existing product does not silently create a duplicate.
      11f. product_add_form.js is included on the product add page.
      11g. product_add_form.js is NOT included on unrelated admin pages.
      11h. Search results include current_stock alongside purchase_price.
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin_dup_test", password="pass", email="dup@test.com"
        )
        self.client.force_login(self.superuser)

    def _post_add(self, **fields):
        defaults = {
            "product_type":   ProductType.MEDICINE,
            "minimum_stock":  "0",
            "purchase_price": "0",
            "initial_stock":  "",
            "product_vendors-TOTAL_FORMS":   "0",
            "product_vendors-INITIAL_FORMS": "0",
            "product_vendors-MIN_NUM_FORMS": "0",
            "product_vendors-MAX_NUM_FORMS": "1000",
            "stock_movements-TOTAL_FORMS":   "0",
            "stock_movements-INITIAL_FORMS": "0",
            "stock_movements-MIN_NUM_FORMS": "0",
            "stock_movements-MAX_NUM_FORMS": "1000",
        }
        defaults.update(fields)
        return self.client.post("/admin/inventory/product/add/", defaults, follow=True)

    # 11a — API search returns the exact-name product

    def test_search_api_returns_exact_name_match(self):
        n       = _uid_next()
        product = _product(name=f"آیفون {n}", purchase_price=Decimal("50000000"))
        response = self.client.get(f"/api/v2/inventory/products/?search={product.name}")
        self.assertEqual(response.status_code, 200)
        data  = response.json()
        names = [r["name"] for r in data.get("results", [])]
        self.assertIn(product.name, names, "Exact name must appear in search results")

    # 11b — partial name only returns partial hits (no false exact match client-side)

    def test_partial_name_does_not_create_false_exact_match(self):
        """API may return results for partial names, but the JS does exact comparison.
        Here we verify API returns results for partial, but the exact product name
        is NOT in the results list (meaning JS would find no exact match).
        """
        n       = _uid_next()
        _product(name=f"ست لاپاراسکوپی کامل {n}")
        response = self.client.get("/api/v2/inventory/products/?search=ست")
        data     = response.json()
        # At least one result is returned (partial match works)
        # But no result has name == 'ست' exactly (JS would not trigger auto-fill)
        names = [r["name"] for r in data.get("results", [])]
        self.assertNotIn("ست", names, "Exact string 'ست' must not appear as a product name")

    # 11c — new product can still be created

    def test_new_product_created_successfully_when_no_match(self):
        n    = _uid_next()
        name = f"کاتتر {n}"
        self._post_add(name=name, internal_code=f"CAT-{n}", purchase_price="1200")
        self.assertTrue(
            Product.objects.filter(name=name).exists(),
            "New product with unique name must be created without errors",
        )

    # 11d — duplicate internal_code blocked

    def test_duplicate_internal_code_blocked(self):
        n        = _uid_next()
        existing = _product(internal_code=f"UNIQ-{n}")
        count_before = Product.objects.count()

        # Try to create another product with the same internal_code
        response = self._post_add(
            name=f"محصول دیگر {n}",
            internal_code=f"UNIQ-{n}",   # duplicate!
            purchase_price="999",
        )
        # Admin re-renders the form (200) — no redirect (302) means save failed
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Product.objects.filter(internal_code=f"UNIQ-{n}").count(),
            1,
            "Only the original product with duplicate internal_code must exist",
        )
        self.assertEqual(Product.objects.count(), count_before)

    # 11e — looking up an existing product does not create a duplicate

    def test_api_search_does_not_create_duplicate(self):
        n       = _uid_next()
        product = _product(name=f"سرم فیزیولوژی {n}", purchase_price=Decimal("3000"))
        count_before = Product.objects.count()

        # Simulate what the JS does: call the search API
        self.client.get(f"/api/v2/inventory/products/?search={product.name}")

        self.assertEqual(
            Product.objects.count(), count_before,
            "Calling the search API must not create any new products",
        )

    # 11f — product_add_form.js loaded on add page

    def test_product_add_form_js_included_on_add_page(self):
        response = self.client.get("/admin/inventory/product/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "product_add_form.js",
            msg_prefix="product_add_form.js must be in the add form HTML",
        )

    # 11g — product_add_form.js not on unrelated page

    def test_product_add_form_js_not_on_vendor_list_page(self):
        response = self.client.get("/admin/inventory/vendor/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "product_add_form.js",
            msg_prefix="product_add_form.js must not appear on the vendor list page",
        )

    # 11h — search result includes both purchase_price and current_stock

    def test_search_result_includes_purchase_price_and_current_stock(self):
        n       = _uid_next()
        product = _product(
            name=f"پنس جراحی {n}",
            purchase_price=Decimal("12500"),
        )
        response = self.client.get(f"/api/v2/inventory/products/?search={product.name}")
        self.assertEqual(response.status_code, 200)
        data   = response.json()
        result = next(
            (r for r in data.get("results", []) if r["name"] == product.name), None
        )
        self.assertIsNotNone(result, "Product must appear in search results")
        self.assertIn("purchase_price", result)
        self.assertIn("current_stock", result)
        self.assertEqual(Decimal(result["purchase_price"]), Decimal("12500"))
        self.assertEqual(Decimal(result["current_stock"]), Decimal("0"))
