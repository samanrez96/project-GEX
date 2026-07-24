"""Tests for the searchable product selector in purchase item rows.

The selector shows a trigger div (displays current selection) that opens a
body-appended dropdown.  The dropdown contains:
  • a visible search input at the top  (class pf-product-search-input)
  • a scrollable results list below    (class pf-product-search-results)

Verifies:
  1.  Add form renders the empty-form template containing a product <select>.
  2.  Edit form renders the product <select> in existing item rows.
  3.  The empty-form template product select uses __prefix__ in its name.
  4.  The empty form template is inside a <template> element.
  5.  The products API returns internal_code in each result.
  6.  The products API returns name in each result.
  7.  The products API search-by-name returns the matching product.
  8.  The products API search-by-internal_code returns the matching product.
  9.  The products API default ordering is internal_code ascending.
  10. The products API returns an empty list when no product matches.
  11. The products API respects the page_size parameter.
  12. JS defines initProductSelector (the per-row setup function).
  13. JS calls initProductSelector from bindRowEvents.
  14. JS dropdown contains the visible pf-product-search-input element.
  15. JS search input placeholder is the required Persian text.
  16. JS uses Persian loading / empty-state messages.
  17. JS dispatches a change event after selection (triggers price/unit fill).
  18. PurchaseItem saves correctly when product id is posted.
  19. TOTAL_FORMS handling is correct in JS.
"""

import os
from decimal import Decimal
import datetime

from django.contrib.auth.models import User
from django.test import TestCase, Client

from inventory.models import (
    Product,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid = 7000


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _vendor():
    return Vendor.objects.create(name=f"تامین‌AC-{_uid_next()}")


def _product(code_prefix="AC", price=Decimal("500")):
    n = _uid_next()
    return Product.objects.create(
        name=f"محصول-AC-{n}",
        internal_code=f"{code_prefix}-{n:04d}",
        product_type=ProductType.MEDICINE,
        purchase_price=price,
    )


def _purchase(vendor):
    return Purchase.objects.create(
        vendor=vendor,
        status=PurchaseStatus.PENDING,
        purchase_date=datetime.datetime(2025, 6, 1, 10, 0, 0),
    )


def _superuser():
    n = _uid_next()
    return User.objects.create_superuser(
        username=f"admin_ac_{n}", password="pass", email=""
    )


# ---------------------------------------------------------------------------
# 1–4 · Template rendering
# ---------------------------------------------------------------------------

class PurchaseItemProductSelectTemplateTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def test_add_form_renders_empty_form_template_with_product_select(self):
        """Add form must include the JS-cloning template with a product select."""
        r = self.client.get("/admin/inventory/purchase/add/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode("utf-8")
        self.assertIn("pf-empty-form-container", content,
                      "Empty-form template container must be present on add form")

    def test_edit_form_renders_product_select_in_existing_rows(self):
        """Edit form with a saved PurchaseItem must render a product select."""
        vendor  = _vendor()
        product = _product()
        purchase = _purchase(vendor)
        PurchaseItem.objects.create(
            purchase=purchase, product=product,
            quantity=2, unit_price=Decimal("300"),
        )
        r = self.client.get(f"/admin/inventory/purchase/{purchase.pk}/change/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode("utf-8")
        self.assertIn('name="items-0-product"', content,
                      "Existing row must have product select with name items-0-product")

    def test_empty_form_product_select_uses_prefix_placeholder(self):
        """The product select in the empty-form template must use __prefix__."""
        r = self.client.get("/admin/inventory/purchase/add/")
        content = r.content.decode("utf-8")
        self.assertIn('name="items-__prefix__-product"', content,
                      "Product select in template must use __prefix__")

    def test_empty_form_template_is_inside_template_element(self):
        """The cloning container must be a <template> element."""
        r = self.client.get("/admin/inventory/purchase/add/")
        content = r.content.decode("utf-8")
        idx = content.find('id="pf-empty-form-container"')
        self.assertGreater(idx, 0, "pf-empty-form-container must exist")
        snippet = content[max(0, idx - 20): idx]
        self.assertIn("<template", snippet,
                      "pf-empty-form-container must be a <template> element")


# ---------------------------------------------------------------------------
# 5–11 · Products API
# ---------------------------------------------------------------------------

class ProductsApiForAutocompleteTest(TestCase):
    """The /api/v1/inventory/products/ endpoint must return the fields and
    ordering that the search dropdown relies on."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())
        self.p1 = Product.objects.create(
            name="آلبومین ۲۵٪",
            internal_code="MED-0001",
            product_type=ProductType.MEDICINE,
            purchase_price=Decimal("1000"),
        )
        self.p2 = Product.objects.create(
            name="باند گاز",
            internal_code="SUP-0002",
            product_type=ProductType.EQUIPMENT,
            purchase_price=Decimal("200"),
        )
        self.p3 = Product.objects.create(
            name="سرنگ ۵cc",
            internal_code="SUP-0003",
            product_type=ProductType.EQUIPMENT,
            purchase_price=Decimal("150"),
        )

    def _get(self, **params):
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = "/api/v1/inventory/products/" + (f"?{qs}" if qs else "")
        return self.client.get(url)

    def test_api_result_includes_internal_code(self):
        r = self._get(search="MED-0001")
        self.assertEqual(r.status_code, 200)
        results = r.json().get("results", [])
        self.assertTrue(len(results) > 0, "Search must return at least one result")
        self.assertIn("internal_code", results[0])
        self.assertEqual(results[0]["internal_code"], "MED-0001")

    def test_api_result_includes_name(self):
        r = self._get(search="MED-0001")
        self.assertEqual(r.status_code, 200)
        results = r.json().get("results", [])
        self.assertTrue(len(results) > 0)
        self.assertIn("name", results[0])
        self.assertEqual(results[0]["name"], "آلبومین ۲۵٪")

    def test_api_search_by_name_finds_product(self):
        r = self._get(search="باند گاز")
        self.assertEqual(r.status_code, 200)
        names = [p["name"] for p in r.json().get("results", [])]
        self.assertIn("باند گاز", names)

    def test_api_search_by_internal_code_finds_product(self):
        r = self._get(search="SUP-0003")
        self.assertEqual(r.status_code, 200)
        codes = [p["internal_code"] for p in r.json().get("results", [])]
        self.assertIn("SUP-0003", codes)

    def test_api_default_ordering_by_internal_code_ascending(self):
        """Without ordering param, results must be sorted by internal_code ASC."""
        r = self._get()
        self.assertEqual(r.status_code, 200)
        results = r.json().get("results", [])
        target = {"MED-0001", "SUP-0002", "SUP-0003"}
        filtered = [p["internal_code"] for p in results if p["internal_code"] in target]
        self.assertEqual(filtered, sorted(filtered),
                         "Products must appear in internal_code ascending order")

    def test_api_search_no_match_returns_empty_results(self):
        r = self._get(search="XXXXNOTEXISTXXXX")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("results", []), [])

    def test_api_page_size_limits_result_count(self):
        for _ in range(3):
            _product()
        r = self._get(page_size=2)
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(len(r.json().get("results", [])), 2)


# ---------------------------------------------------------------------------
# 12–19 · JavaScript source tests
# ---------------------------------------------------------------------------

class PurchaseFormJsSelectorTest(TestCase):
    """The purchase_form.js source must contain the correct selector
    implementation with a visible search input inside the dropdown."""

    @classmethod
    def _js(cls):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static", "admin", "js", "purchase_form.js",
        )
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_js_defines_init_product_selector(self):
        self.assertIn("initProductSelector", self._js(),
                      "JS must define initProductSelector")

    def test_js_calls_init_product_selector_from_bind_row_events(self):
        src = self._js()
        bind_idx = src.find("function bindRowEvents")
        self.assertGreater(bind_idx, 0)
        next_fn = src.find("\n    function ", bind_idx + 1)
        body = src[bind_idx: next_fn if next_fn > 0 else bind_idx + 2000]
        self.assertIn("initProductSelector", body,
                      "bindRowEvents must call initProductSelector")

    def test_js_creates_visible_search_input_in_dropdown(self):
        """The JS must create an element with class pf-product-search-input."""
        src = self._js()
        self.assertIn("pf-product-search-input", src,
                      "JS must create the visible pf-product-search-input element")

    def test_js_creates_search_header_in_dropdown(self):
        """Dropdown must have a search-header section above the results."""
        src = self._js()
        self.assertIn("pf-product-search-header", src,
                      "JS must create pf-product-search-header inside the dropdown")

    def test_js_search_input_placeholder_is_persian(self):
        self.assertIn("جستجو بر اساس نام یا کد داخلی", self._js(),
                      "Search input placeholder must be the Persian search hint")

    def test_js_uses_persian_loading_text(self):
        self.assertIn("در حال جستجو", self._js(),
                      "Loading state must use Persian text 'در حال جستجو'")

    def test_js_uses_persian_empty_text(self):
        self.assertIn("محصولی پیدا نشد", self._js(),
                      "Empty state must use Persian text 'محصولی پیدا نشد'")

    def test_js_uses_persian_error_text(self):
        self.assertIn("خطا در دریافت محصولات", self._js(),
                      "Error state must use Persian text 'خطا در دریافت محصولات'")

    def test_js_dispatches_change_event_on_selection(self):
        src = self._js()
        self.assertIn("dispatchEvent", src)
        self.assertIn("'change'", src,
                      "JS must dispatch a 'change' event after product selection")

    def test_js_fetch_product_unit_still_exists(self):
        """fetchProductUnit must still be present so price/unit autofill works."""
        self.assertIn("fetchProductUnit", self._js())

    def test_js_uses_correct_querySelector_for_total_forms(self):
        src = self._js()
        self.assertNotIn("getElementById(PREFIX + '-TOTAL_FORMS')", src)
        self.assertIn("querySelector('[name=\"' + PREFIX + '-TOTAL_FORMS\"]')", src)


# ---------------------------------------------------------------------------
# 18 · PurchaseItem save integration
# ---------------------------------------------------------------------------

class PurchaseItemSaveWithSelectorTest(TestCase):
    """Form POST must still create PurchaseItems correctly; the selector is
    pure front-end and must not affect server-side save logic."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def _post_with_item(self, purchase, product, qty="3", price="750"):
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
            "items-0-quantity":    qty,
            "items-0-unit_price":  price,
            "items-0-notes":       "",
            "items-0-id":          "",
            "_save":               "1",
        }
        return self.client.post(
            f"/admin/inventory/purchase/{purchase.pk}/change/", data
        )

    def test_purchase_item_saves_with_correct_product(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        r = self._post_with_item(purchase, product)
        self.assertIn(r.status_code, [301, 302],
                      f"Save must redirect; got {r.status_code}")
        self.assertEqual(purchase.items.count(), 1)
        self.assertEqual(purchase.items.first().product_id, product.pk)

    def test_purchase_item_saves_correct_quantity_and_price(self):
        vendor   = _vendor()
        product  = _product()
        purchase = _purchase(vendor)
        self._post_with_item(purchase, product, qty="5", price="1200")
        item = purchase.items.first()
        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, Decimal("5"))
        self.assertEqual(item.unit_price, Decimal("1200"))
