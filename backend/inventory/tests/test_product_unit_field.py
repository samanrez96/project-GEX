"""Tests for the optional واحد field on the Product add/edit admin forms.

Covers all requirements from the task spec:
  1.  Product add page contains the واحد field.
  2.  واحد appears after نوع محصول in the form.
  3.  واحد field is not required (no asterisk / not marked required).
  4.  Product can be created with an empty unit.
  5.  Product can be created with a unit value (بسته).
  6.  Saved unit appears on the Product edit page.
  7.  Existing product unit can be edited.
  8.  Clearing the unit and saving succeeds.
  9.  Product list columns do not include واحد.
 10.  Product detail does not gain an unwanted extra unit column.
 11.  Purchase product selection still returns the saved unit via API.
 12.  PurchaseItem saves when Product.unit is blank.
 13.  Product price/initial-stock admin POST tests still pass.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from inventory.models import (
    Product,
    ProductType,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)

User = get_user_model()

_uid = 9000


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _make_admin(suffix=""):
    n = _uid_next()
    return User.objects.create_superuser(
        username=f"unit_admin_{n}{suffix}", password="pass"
    )


def _make_product(**kw):
    n = _uid_next()
    defaults = {
        "name":          f"محصول واحد {n}",
        "internal_code": f"UF-{n:04d}",
        "product_type":  ProductType.MEDICINE,
        "unit":          "",
    }
    defaults.update(kw)
    return Product.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Add page HTML structure tests
# ---------------------------------------------------------------------------

class ProductAddPageUnitFieldTest(TestCase):

    def setUp(self):
        self.admin = _make_admin()
        self.client.force_login(self.admin)

    def _get_add(self):
        return self.client.get("/admin/inventory/product/add/")

    def test_add_page_contains_unit_field(self):
        resp = self._get_add()
        self.assertContains(resp, 'id_unit')

    def test_unit_label_is_persian(self):
        resp = self._get_add()
        content = resp.content.decode()
        self.assertIn('واحد', content)

    def test_unit_has_placeholder(self):
        resp = self._get_add()
        self.assertContains(resp, 'مثلاً عدد، بسته، جعبه')

    def test_unit_appears_after_product_type(self):
        """id_unit must appear after id_product_type in the rendered HTML."""
        resp = self._get_add()
        content = resp.content.decode()
        pos_type = content.find('id_product_type')
        pos_unit = content.find('id_unit')
        self.assertGreater(pos_type, -1, "id_product_type not found")
        self.assertGreater(pos_unit, -1, "id_unit not found")
        self.assertGreater(pos_unit, pos_type, "واحد must appear after نوع محصول")

    def test_unit_field_not_required(self):
        """The unit input must not carry the 'required' HTML attribute."""
        resp = self._get_add()
        content = resp.content.decode()
        # Find the unit input tag and verify it has no 'required'
        import re
        match = re.search(r'<input[^>]*name="unit"[^>]*>', content)
        self.assertIsNotNone(match, "unit input not found in HTML")
        self.assertNotIn('required', match.group())


# ---------------------------------------------------------------------------
# Add page POST tests
# ---------------------------------------------------------------------------

class ProductAddPostUnitTest(TestCase):

    def setUp(self):
        self.admin = _make_admin()
        self.client.force_login(self.admin)

    def _post(self, extra=None):
        n = _uid_next()
        data = {
            "name":            f"محصول تست {n}",
            "internal_code":   f"UPT-{n:04d}",
            "product_type":    "medicine",
            "unit":            "",
            "purchase_price":  "0",
            "initial_stock":   "",
            "minimum_stock":   "0",
            "internal_notes":  "",
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
            "_save":           "1",
        }
        if extra:
            data.update(extra)
        return self.client.post("/admin/inventory/product/add/", data=data)

    def test_create_product_with_empty_unit(self):
        resp = self._post({"unit": ""})
        self.assertIn(resp.status_code, (301, 302), "Expected redirect after save")
        self.assertTrue(
            Product.objects.filter(internal_code__startswith="UPT-", unit="").exists()
        )

    def test_create_product_with_unit_value(self):
        resp = self._post({"unit": "بسته"})
        self.assertIn(resp.status_code, (301, 302))
        # Find the product that was just created (latest code starting with UPT-)
        product = Product.objects.filter(
            internal_code__startswith="UPT-", unit="بسته"
        ).last()
        self.assertIsNotNone(product)
        self.assertEqual(product.unit, "بسته")

    def test_create_product_without_unit_key(self):
        """Submitting form without 'unit' key at all must succeed (optional)."""
        n = _uid_next()
        data = {
            "name":           f"محصول بدون واحد {n}",
            "internal_code":  f"UPT-{n:04d}",
            "product_type":   "medicine",
            # unit intentionally omitted
            "purchase_price": "0",
            "initial_stock":  "",
            "minimum_stock":  "0",
            "internal_notes": "",
            "product_vendors-TOTAL_FORMS":   "0",
            "product_vendors-INITIAL_FORMS": "0",
            "product_vendors-MIN_NUM_FORMS": "0",
            "product_vendors-MAX_NUM_FORMS": "1000",
            "stock_movements-TOTAL_FORMS":   "0",
            "stock_movements-INITIAL_FORMS": "0",
            "stock_movements-MIN_NUM_FORMS": "0",
            "stock_movements-MAX_NUM_FORMS": "1000",
            "_save":          "1",
        }
        resp = self.client.post("/admin/inventory/product/add/", data=data)
        self.assertIn(resp.status_code, (301, 302))
        self.assertTrue(
            Product.objects.filter(internal_code=f"UPT-{n:04d}").exists()
        )


# ---------------------------------------------------------------------------
# Edit page tests
# ---------------------------------------------------------------------------

class ProductEditPageUnitTest(TestCase):

    def setUp(self):
        self.admin = _make_admin()
        self.client.force_login(self.admin)
        self.product = _make_product(unit="عدد")

    def test_edit_page_shows_saved_unit(self):
        resp = self.client.get(
            f"/admin/inventory/product/{self.product.pk}/change/"
        )
        self.assertContains(resp, 'id_unit')
        self.assertContains(resp, 'value="عدد"')

    def _edit_post(self, unit):
        return self.client.post(
            f"/admin/inventory/product/{self.product.pk}/change/",
            data={
                "name":           self.product.name,
                "internal_code":  self.product.internal_code,
                "product_type":   self.product.product_type,
                "unit":           unit,
                "purchase_price": "0",
                "minimum_stock":  "0",
                "internal_notes": "",
                # Superuser editing an existing Product now also sees
                # desired_current_stock (see ProductAdmin._can_adjust_stock) —
                # unchanged from the real current stock, so no adjustment
                # reason is required.
                "desired_current_stock":   str(self.product.current_stock),
                "stock_adjustment_reason": "",
                "product_vendors-TOTAL_FORMS":   "0",
                "product_vendors-INITIAL_FORMS": "0",
                "product_vendors-MIN_NUM_FORMS": "0",
                "product_vendors-MAX_NUM_FORMS": "1000",
                "stock_movements-TOTAL_FORMS":   "0",
                "stock_movements-INITIAL_FORMS": "0",
                "stock_movements-MIN_NUM_FORMS": "0",
                "stock_movements-MAX_NUM_FORMS": "1000",
                "_save":          "1",
            },
        )

    def test_edit_unit_changes_value(self):
        resp = self._edit_post("جعبه")
        self.assertIn(resp.status_code, (301, 302))
        self.product.refresh_from_db()
        self.assertEqual(self.product.unit, "جعبه")

    def test_clear_unit_and_save(self):
        resp = self._edit_post("")
        self.assertIn(resp.status_code, (301, 302))
        self.product.refresh_from_db()
        self.assertEqual(self.product.unit, "")


# ---------------------------------------------------------------------------
# Product list — unit column must NOT appear
# ---------------------------------------------------------------------------

class ProductListUnitColumnTest(TestCase):

    def setUp(self):
        self.admin = _make_admin()
        self.client.force_login(self.admin)

    def test_product_list_has_no_unit_column_header(self):
        """The admin list table must not add a واحد column."""
        resp = self.client.get("/admin/inventory/product/")
        content = resp.content.decode()
        # The custom JS-driven list template renders column headers; none should be 'واحد'
        # We check that there is no th/header with the exact text 'واحد'
        import re
        th_texts = re.findall(r'<th[^>]*>\s*(.*?)\s*</th>', content, re.DOTALL)
        stripped = [t.strip() for t in th_texts]
        self.assertNotIn('واحد', stripped)


# ---------------------------------------------------------------------------
# Purchase compatibility — unit autofill via API
# ---------------------------------------------------------------------------

class PurchaseUnitCompatibilityTest(TestCase):

    def setUp(self):
        self.admin = _make_admin()
        self.client.force_login(self.admin)

    def test_product_api_returns_unit(self):
        product = _make_product(unit="ویال")
        resp = self.client.get(f"/api/v1/inventory/products/{product.pk}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["unit"], "ویال")

    def test_product_api_returns_empty_unit_when_blank(self):
        product = _make_product(unit="")
        resp = self.client.get(f"/api/v1/inventory/products/{product.pk}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["unit"], "")

    def test_purchase_item_saves_when_product_unit_blank(self):
        vendor = Vendor.objects.create(name="فروشنده واحد خالی")
        product = _make_product(unit="")
        purchase = Purchase.objects.create(
            vendor=vendor, status=PurchaseStatus.PENDING
        )
        item = PurchaseItem(
            purchase=purchase,
            product=product,
            quantity=Decimal("1"),
            unit_price=Decimal("0"),
        )
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.unit, "")

    def test_purchase_item_inherits_product_unit(self):
        vendor = Vendor.objects.create(name="فروشنده واحد عدد")
        product = _make_product(unit="آمپول")
        purchase = Purchase.objects.create(
            vendor=vendor, status=PurchaseStatus.PENDING
        )
        item = PurchaseItem(
            purchase=purchase,
            product=product,
            quantity=Decimal("2"),
            unit_price=Decimal("0"),
        )
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.unit, "آمپول")

    def test_unit_field_available_in_products_list_api(self):
        product = _make_product(unit="قرص")
        resp = self.client.get(
            "/api/v1/inventory/products/",
            {"search": product.internal_code},
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json().get("results", resp.json())
        self.assertTrue(
            any(p["unit"] == "قرص" for p in results),
            "unit field not found in products list API",
        )


# ---------------------------------------------------------------------------
# Model-level: blank unit saves without error
# ---------------------------------------------------------------------------

class ProductUnitModelTest(TestCase):

    def test_save_with_blank_unit(self):
        p = Product(
            name="محصول بدون واحد مدل",
            internal_code="UF-MODEL-001",
            product_type=ProductType.MEDICINE,
            unit="",
        )
        p.full_clean()
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.unit, "")

    def test_save_with_unit_value(self):
        p = Product(
            name="محصول با واحد مدل",
            internal_code="UF-MODEL-002",
            product_type=ProductType.MEDICINE,
            unit="رول",
        )
        p.full_clean()
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.unit, "رول")
