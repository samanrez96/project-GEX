"""Tests for CLI-11: Product Search & Filter API (ProductViewSet)."""

import math
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import Product, ProductCategory, ProductType

LIST_URL       = "/api/v1/inventory/products/"
LOW_STOCK_URL  = "/api/v1/inventory/products/low_stock/"
EXPORT_IDS_URL = "/api/v1/inventory/products/export_ids/"


def _cat(name, parent=None):
    return ProductCategory.objects.create(name=name, parent=parent)


def _product(**kwargs):
    defaults = {
        "name":         "محصول آزمایشی",
        "internal_code": "TST-001",
        "product_type": ProductType.MEDICINE,
        "unit":         "عدد",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


class ProductSearchAPITest(TestCase):
    """Search, filter, pagination, ordering, and query-count tests."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("searcher", password="pass")

        cls.root_daro     = ProductCategory.objects.get(name="دارو",     parent=None)
        cls.root_tejhizat = ProductCategory.objects.get(name="تجهیزات", parent=None)

        cls.sub_bihushi     = _cat("بیهوشی",      parent=cls.root_daro)
        cls.sub_sub_gaz     = _cat("گاز بیهوشی",  parent=cls.sub_bihushi)
        cls.sub_jarrahi     = _cat("جراحی",        parent=cls.root_tejhizat)

        # p1 — medicine, has barcode, price 500
        cls.p1 = _product(
            name="ایزوفلوران",
            internal_code="MED-001",
            product_type=ProductType.MEDICINE,
            category=cls.sub_sub_gaz,
            purchase_price=Decimal("500"),
            barcode="123456789",
        )
        # p2 — equipment, no barcode, price 2000
        cls.p2 = _product(
            name="سوند فولی",
            internal_code="EQP-001",
            product_type=ProductType.EQUIPMENT,
            category=cls.sub_jarrahi,
            purchase_price=Decimal("2000"),
        )
        # p3 — medicine, has barcode, minimum_stock set → low-stock from the start
        cls.p3 = _product(
            name="نرمال سالین",
            internal_code="MED-002",
            product_type=ProductType.MEDICINE,
            category=cls.root_daro,
            purchase_price=Decimal("100"),
            barcode="987654321",
            minimum_stock=Decimal("10"),
        )
        # p4 — medicine, inactive
        cls.p4 = _product(
            name="محصول قدیمی",
            internal_code="MED-003",
            product_type=ProductType.MEDICINE,
            is_active=False,
        )
        # p5 — medicine, no barcode, minimum_stock set → low-stock, price 800
        cls.p5 = _product(
            name="پروپوفول",
            internal_code="MED-004",
            product_type=ProductType.MEDICINE,
            category=cls.sub_bihushi,
            purchase_price=Decimal("800"),
            minimum_stock=Decimal("5"),
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    # ------------------------------------------------------------------
    # Search tests
    # ------------------------------------------------------------------

    def test_search_by_name(self):
        res = self.client.get(LIST_URL, {"search": "ایزوفلوران"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        codes = [r["internal_code"] for r in res.data["results"]]
        self.assertIn("MED-001", codes)
        self.assertNotIn("EQP-001", codes)

    def test_search_by_internal_code(self):
        res = self.client.get(LIST_URL, {"search": "EQP-001"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["internal_code"], "EQP-001")

    def test_search_by_barcode(self):
        res = self.client.get(LIST_URL, {"search": "123456789"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["internal_code"], "MED-001")

    def test_search_by_category_name(self):
        res = self.client.get(LIST_URL, {"search": "گاز بیهوشی"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["internal_code"], "MED-001")

    def test_search_no_results(self):
        res = self.client.get(LIST_URL, {"search": "متنی که وجود ندارد xyz"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 0)
        self.assertEqual(res.data["results"], [])

    # ------------------------------------------------------------------
    # Filter: product_type
    # ------------------------------------------------------------------

    def test_filter_product_type_medicine(self):
        res = self.client.get(LIST_URL, {"product_type": "medicine"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        types = [r["product_type"] for r in res.data["results"]]
        self.assertTrue(all(t == "medicine" for t in types))
        self.assertGreater(len(types), 0)

    def test_filter_product_type_equipment(self):
        res = self.client.get(LIST_URL, {"product_type": "equipment"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["internal_code"], "EQP-001")

    # ------------------------------------------------------------------
    # Filter: category (exact) and category_tree (descendants)
    # ------------------------------------------------------------------

    def test_filter_category_exact(self):
        res = self.client.get(LIST_URL, {"category": self.sub_sub_gaz.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.p1.pk, ids)
        self.assertNotIn(self.p2.pk, ids)
        self.assertNotIn(self.p5.pk, ids)  # p5 is in parent (sub_bihushi), not sub_sub_gaz

    def test_filter_category_tree_includes_descendants(self):
        # sub_bihushi → children: sub_sub_gaz (p1) + direct p5
        res = self.client.get(LIST_URL, {"category_tree": self.sub_bihushi.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.p1.pk, ids)
        self.assertIn(self.p5.pk, ids)
        self.assertNotIn(self.p2.pk, ids)
        self.assertNotIn(self.p3.pk, ids)

    def test_filter_category_tree_root_covers_all_descendants(self):
        res = self.client.get(LIST_URL, {"category_tree": self.root_daro.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.p1.pk, ids)
        self.assertIn(self.p3.pk, ids)
        self.assertIn(self.p5.pk, ids)
        self.assertNotIn(self.p2.pk, ids)  # equipment

    def test_filter_category_tree_nonexistent_returns_empty(self):
        res = self.client.get(LIST_URL, {"category_tree": 999999})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 0)

    # ------------------------------------------------------------------
    # Filter: is_active
    # ------------------------------------------------------------------

    def test_filter_is_active_default_excludes_inactive(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        codes = [r["internal_code"] for r in res.data["results"]]
        self.assertNotIn("MED-003", codes)  # p4 is inactive

    def test_filter_is_active_false_returns_only_inactive(self):
        res = self.client.get(LIST_URL, {"is_active": "false"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        codes = [r["internal_code"] for r in res.data["results"]]
        self.assertIn("MED-003", codes)
        self.assertNotIn("MED-001", codes)

    def test_filter_is_active_true_explicit(self):
        res = self.client.get(LIST_URL, {"is_active": "true"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        codes = [r["internal_code"] for r in res.data["results"]]
        self.assertNotIn("MED-003", codes)
        self.assertIn("MED-001", codes)

    # ------------------------------------------------------------------
    # Filter: low_stock / out_of_stock
    # ------------------------------------------------------------------

    def test_filter_low_stock_true(self):
        # p3: minimum_stock=10, current_stock=0 → low stock
        # p5: minimum_stock=5,  current_stock=0 → low stock
        res = self.client.get(LIST_URL, {"low_stock": "true"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.p3.pk, ids)
        self.assertIn(self.p5.pk, ids)

    def test_filter_low_stock_excludes_products_without_minimum(self):
        # p1 has minimum_stock=0 (default) → NOT low stock
        res = self.client.get(LIST_URL, {"low_stock": "true"})
        ids = [r["id"] for r in res.data["results"]]
        self.assertNotIn(self.p1.pk, ids)

    def test_filter_out_of_stock(self):
        res = self.client.get(LIST_URL, {"out_of_stock": "true"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # All active products start with current_stock=0
        self.assertGreaterEqual(res.data["count"], 4)

    # ------------------------------------------------------------------
    # Filter: price range
    # ------------------------------------------------------------------

    def test_filter_price_min(self):
        res = self.client.get(LIST_URL, {"price_min": "500"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        prices = [Decimal(r["purchase_price"]) for r in res.data["results"]]
        self.assertTrue(all(p >= Decimal("500") for p in prices))
        self.assertGreater(len(prices), 0)

    def test_filter_price_max(self):
        res = self.client.get(LIST_URL, {"price_max": "500"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        prices = [Decimal(r["purchase_price"]) for r in res.data["results"]]
        self.assertTrue(all(p <= Decimal("500") for p in prices))

    def test_filter_price_range(self):
        res = self.client.get(LIST_URL, {"price_min": "400", "price_max": "900"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        prices = [Decimal(r["purchase_price"]) for r in res.data["results"]]
        self.assertTrue(all(Decimal("400") <= p <= Decimal("900") for p in prices))
        # p1(500) and p5(800) qualify; p2(2000) and p3(100) do not
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.p1.pk, ids)
        self.assertIn(self.p5.pk, ids)
        self.assertNotIn(self.p2.pk, ids)
        self.assertNotIn(self.p3.pk, ids)

    # ------------------------------------------------------------------
    # Filter: has_barcode
    # ------------------------------------------------------------------

    def test_filter_has_barcode_true_returns_only_products_with_barcode(self):
        # Active products with barcode: p1, p3
        res = self.client.get(LIST_URL, {"has_barcode": "true"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.p1.pk, ids)
        self.assertIn(self.p3.pk, ids)
        self.assertNotIn(self.p2.pk, ids)
        self.assertNotIn(self.p5.pk, ids)

    def test_filter_has_barcode_false_returns_only_products_without_barcode(self):
        # Active products without barcode: p2, p5
        res = self.client.get(LIST_URL, {"has_barcode": "false"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(self.p2.pk, ids)
        self.assertIn(self.p5.pk, ids)
        self.assertNotIn(self.p1.pk, ids)
        self.assertNotIn(self.p3.pk, ids)

    # ------------------------------------------------------------------
    # Filter: combined
    # ------------------------------------------------------------------

    def test_filter_combined_medicine_with_barcode_price_range(self):
        # medicine + price 400-600 + has_barcode → only p1 (500, barcode)
        res = self.client.get(LIST_URL, {
            "product_type": "medicine",
            "price_min":    "400",
            "price_max":    "600",
            "has_barcode":  "true",
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["id"], self.p1.pk)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def test_unauthenticated_returns_401(self):
        res = APIClient().get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # ------------------------------------------------------------------
    # Pagination envelope
    # ------------------------------------------------------------------

    def test_pagination_envelope_has_required_keys(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for key in ("count", "next", "previous", "page_size", "total_pages", "results"):
            self.assertIn(key, res.data, msg=f"envelope key '{key}' missing")

    def test_pagination_default_page_size_is_150(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.data["page_size"], 150)

    def test_pagination_custom_page_size(self):
        res = self.client.get(LIST_URL, {"page_size": "2"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["page_size"], 2)
        self.assertLessEqual(len(res.data["results"]), 2)

    def test_pagination_page_size_capped_at_200(self):
        res = self.client.get(LIST_URL, {"page_size": "9999"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertLessEqual(res.data["page_size"], 200)

    def test_pagination_total_pages_matches_count(self):
        res = self.client.get(LIST_URL, {"page_size": "2"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        expected = math.ceil(res.data["count"] / 2)
        self.assertEqual(res.data["total_pages"], expected)

    def test_pagination_page_2_has_previous_link(self):
        for i in range(30):
            _product(name=f"محصول صفحه‌بندی {i}", internal_code=f"PG-{i:03d}")
        res = self.client.get(LIST_URL, {"page": "2", "page_size": "10"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(res.data["previous"])
        self.assertLessEqual(len(res.data["results"]), 10)

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def test_ordering_by_purchase_price_ascending(self):
        res = self.client.get(LIST_URL, {"ordering": "purchase_price"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        prices = [Decimal(r["purchase_price"]) for r in res.data["results"]]
        self.assertEqual(prices, sorted(prices))

    def test_ordering_by_purchase_price_descending(self):
        res = self.client.get(LIST_URL, {"ordering": "-purchase_price"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        prices = [Decimal(r["purchase_price"]) for r in res.data["results"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_ordering_asc_and_desc_are_reversed(self):
        res_asc  = self.client.get(LIST_URL, {"ordering": "name"})
        res_desc = self.client.get(LIST_URL, {"ordering": "-name"})
        names_asc  = [r["name"] for r in res_asc.data["results"]]
        names_desc = [r["name"] for r in res_desc.data["results"]]
        self.assertEqual(names_asc, list(reversed(names_desc)))

    def test_ordering_by_current_stock_asc(self):
        res = self.client.get(LIST_URL, {"ordering": "current_stock"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        stocks = [Decimal(r["current_stock"]) for r in res.data["results"]]
        self.assertEqual(stocks, sorted(stocks))

    # ------------------------------------------------------------------
    # low_stock/ action
    # ------------------------------------------------------------------

    def test_low_stock_action_returns_low_stock_products(self):
        res = self.client.get(LOW_STOCK_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # low_stock returns a plain list (not paginated)
        ids = [r["id"] for r in res.data]
        self.assertIn(self.p3.pk, ids)
        self.assertIn(self.p5.pk, ids)

    def test_low_stock_action_excludes_products_with_no_minimum(self):
        res = self.client.get(LOW_STOCK_URL)
        ids = [r["id"] for r in res.data]
        self.assertNotIn(self.p1.pk, ids)  # p1.minimum_stock == 0

    def test_low_stock_action_ordered_ascending(self):
        res = self.client.get(LOW_STOCK_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        stocks = [Decimal(r["current_stock"]) for r in res.data]
        self.assertEqual(stocks, sorted(stocks))

    def test_low_stock_action_excludes_inactive(self):
        inactive_low = _product(
            name="دارو غیرفعال کم موجود",
            internal_code="INL-001",
            minimum_stock=Decimal("5"),
            is_active=False,
        )
        res = self.client.get(LOW_STOCK_URL)
        ids = [r["id"] for r in res.data]
        self.assertNotIn(inactive_low.pk, ids)

    # ------------------------------------------------------------------
    # export_ids/ action
    # ------------------------------------------------------------------

    def test_export_ids_returns_id_list_and_count(self):
        res = self.client.get(EXPORT_IDS_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("ids", res.data)
        self.assertIn("count", res.data)
        self.assertIsInstance(res.data["ids"], list)
        self.assertEqual(res.data["count"], len(res.data["ids"]))

    def test_export_ids_respects_filter(self):
        res = self.client.get(EXPORT_IDS_URL, {"product_type": "equipment"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertIn(self.p2.pk, res.data["ids"])

    def test_export_ids_over_1000_returns_400(self):
        Product.objects.bulk_create([
            Product(
                name=f"انبوه {i}",
                internal_code=f"BULK-{i:04d}",
                product_type=ProductType.MEDICINE,
                unit="عدد",
            )
            for i in range(1001)
        ])
        res = self.client.get(EXPORT_IDS_URL)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("count", res.data)
        self.assertGreater(res.data["count"], 1000)

    # ------------------------------------------------------------------
    # Query count — calibrate:
    #   1. COUNT (pagination)
    #   2. Product SELECT + category LEFT JOIN
    #   3. ProductVendor prefetch + vendor INNER JOIN  (added in CLI-13)
    # Total: 3 constant queries — not N+1.
    # ------------------------------------------------------------------

    def test_list_query_count(self):
        with self.assertNumQueries(3):
            res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
