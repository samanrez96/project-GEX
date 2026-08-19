"""Tests for the per-product vendor price history API endpoint.

Endpoint: GET /api/v2/inventory/products/{id}/vendor-price-history/

Optional filters:
  vendor_id, date_from, date_to, currency
"""

from decimal import Decimal
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import (
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
)

PRODUCTS_URL = "/api/v2/inventory/products/"


def _price_history_url(product_id):
    return f"{PRODUCTS_URL}{product_id}/vendor-price-history/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vendor(**kwargs):
    defaults = {"name": "تأمین‌کننده آزمایشی"}
    defaults.update(kwargs)
    return Vendor.objects.create(**defaults)


def _product(**kwargs):
    defaults = {
        "name":          "ایزوفلوران",
        "internal_code": "VPH-MED-001",
        "product_type":  ProductType.MEDICINE,
        "unit":          "ml",
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def _purchase(vendor, purchase_date=None, **kwargs):
    from django.utils import timezone
    defaults = {"vendor": vendor}
    if purchase_date:
        defaults["purchase_date"] = purchase_date
    defaults.update(kwargs)
    return Purchase.objects.create(**defaults)


def _item(purchase, product, quantity=Decimal("10"), unit_price=Decimal("100"), **kwargs):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        **kwargs,
    )


def _confirmed_purchase(vendor, product, unit_price=Decimal("100"),
                        qty=Decimal("10"), purchase_date=None):
    p = _purchase(vendor, purchase_date=purchase_date)
    _item(p, product, quantity=qty, unit_price=unit_price)
    p.confirm()
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class VendorPriceHistoryAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="hist_user", password="pass")
        self.client.force_authenticate(user=self.user)

        self.vendor  = _vendor(name="فروشنده اول")
        self.product = _product()

    # ── Basic behaviour ───────────────────────────────────────────────

    def test_returns_200_for_valid_product(self):
        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_returns_404_for_nonexistent_product(self):
        resp = self.client.get(_price_history_url(99999))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── Data correctness ──────────────────────────────────────────────

    def test_history_returns_confirmed_purchases_only(self):
        _confirmed_purchase(self.vendor, self.product, unit_price=Decimal("200"))
        # PENDING purchase — must NOT appear
        pending = _purchase(self.vendor)
        _item(pending, self.product, unit_price=Decimal("999"))

        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_history_contains_required_fields(self):
        _confirmed_purchase(self.vendor, self.product,
                            unit_price=Decimal("500"), qty=Decimal("3"))
        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = resp.data[0]

        for field in [
            "product_id", "product_name",
            "vendor_id", "vendor_name",
            "purchase_id", "reference_id",
            "purchase_date",
            "unit_price", "quantity", "total_amount",
            "currency",
        ]:
            self.assertIn(field, row, msg=f"Missing field: {field}")

    def test_total_amount_is_correct(self):
        _confirmed_purchase(self.vendor, self.product,
                            unit_price=Decimal("250"), qty=Decimal("4"))
        resp = self.client.get(_price_history_url(self.product.pk))
        row = resp.data[0]
        # Convert both to Decimal for comparison — avoids trailing-zero format differences
        self.assertEqual(Decimal(row["total_amount"]), Decimal("250") * Decimal("4"))

    def test_product_fields_populated(self):
        _confirmed_purchase(self.vendor, self.product, unit_price=Decimal("100"))
        resp = self.client.get(_price_history_url(self.product.pk))
        row = resp.data[0]
        self.assertEqual(row["product_id"],   self.product.pk)
        self.assertEqual(row["product_name"], self.product.name)
        self.assertEqual(row["vendor_id"],    self.vendor.pk)
        self.assertEqual(row["vendor_name"],  self.vendor.name)

    def test_excludes_other_product_items(self):
        other = _product(internal_code="VPH-OTHER-001", name="محصول دیگر")
        vendor2 = _vendor(name="فروشنده دوم")

        p = _purchase(vendor2)
        _item(p, other, unit_price=Decimal("999"))
        p.confirm()

        _confirmed_purchase(self.vendor, self.product, unit_price=Decimal("100"))

        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(int(resp.data[0]["product_id"]), self.product.pk)

    # ── Vendor filter ─────────────────────────────────────────────────

    def test_vendor_filter_returns_only_matching_vendor(self):
        vendor2 = _vendor(name="فروشنده دوم")
        _confirmed_purchase(self.vendor,  self.product, unit_price=Decimal("100"))
        _confirmed_purchase(vendor2,      self.product, unit_price=Decimal("200"))

        resp = self.client.get(
            _price_history_url(self.product.pk),
            {"vendor_id": self.vendor.pk},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(int(resp.data[0]["vendor_id"]), self.vendor.pk)

    def test_vendor_filter_invalid_returns_400(self):
        resp = self.client.get(
            _price_history_url(self.product.pk),
            {"vendor_id": "abc"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Date range filter ─────────────────────────────────────────────

    def test_date_from_filter(self):
        from django.utils import timezone as tz
        import datetime

        early = tz.make_aware(datetime.datetime(2024, 1, 15))
        late  = tz.make_aware(datetime.datetime(2024, 6, 15))

        _confirmed_purchase(self.vendor, self.product,
                            unit_price=Decimal("100"), purchase_date=early)
        _confirmed_purchase(self.vendor, self.product,
                            unit_price=Decimal("200"), purchase_date=late)

        resp = self.client.get(
            _price_history_url(self.product.pk),
            {"date_from": "2024-04-01"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["unit_price"], "200.00")

    def test_date_to_filter(self):
        from django.utils import timezone as tz
        import datetime

        early = tz.make_aware(datetime.datetime(2024, 1, 15))
        late  = tz.make_aware(datetime.datetime(2024, 6, 15))

        _confirmed_purchase(self.vendor, self.product,
                            unit_price=Decimal("100"), purchase_date=early)
        _confirmed_purchase(self.vendor, self.product,
                            unit_price=Decimal("200"), purchase_date=late)

        resp = self.client.get(
            _price_history_url(self.product.pk),
            {"date_to": "2024-03-31"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["unit_price"], "100.00")

    def test_date_from_invalid_returns_400(self):
        resp = self.client.get(
            _price_history_url(self.product.pk),
            {"date_from": "invalid-date"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_date_to_invalid_returns_400(self):
        resp = self.client.get(
            _price_history_url(self.product.pk),
            {"date_to": "not-a-date"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Currency filter ───────────────────────────────────────────────

    def test_currency_filter(self):
        vendor_usd = _vendor(name="فروشنده USD")
        # Create ProductVendor link for self.vendor with IRR
        ProductVendor.objects.create(
            product=self.product,
            vendor=self.vendor,
            unit_price=Decimal("100"),
            currency="IRR",
        )
        # Create ProductVendor link for vendor_usd with USD
        ProductVendor.objects.create(
            product=self.product,
            vendor=vendor_usd,
            unit_price=Decimal("5"),
            currency="USD",
        )

        _confirmed_purchase(self.vendor,   self.product, unit_price=Decimal("100"))
        _confirmed_purchase(vendor_usd,    self.product, unit_price=Decimal("5"))

        resp = self.client.get(
            _price_history_url(self.product.pk),
            {"currency": "USD"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(int(resp.data[0]["vendor_id"]), vendor_usd.pk)

    # ── Ordering ──────────────────────────────────────────────────────

    def test_results_sorted_by_purchase_date_ascending(self):
        from django.utils import timezone as tz
        import datetime

        dates = [
            tz.make_aware(datetime.datetime(2024, 3, 1)),
            tz.make_aware(datetime.datetime(2024, 1, 1)),
            tz.make_aware(datetime.datetime(2024, 6, 1)),
        ]
        prices = [Decimal("300"), Decimal("100"), Decimal("600")]

        for d, price in zip(dates, prices):
            _confirmed_purchase(self.vendor, self.product,
                                unit_price=price, purchase_date=d)

        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        returned_prices = [row["unit_price"] for row in resp.data]
        self.assertEqual(returned_prices, ["100.00", "300.00", "600.00"])

    # ── Empty result ──────────────────────────────────────────────────

    def test_empty_history_returns_empty_list(self):
        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    def test_no_pagination_envelope(self):
        """Result must be a plain list, not wrapped in count/results."""
        _confirmed_purchase(self.vendor, self.product)
        resp = self.client.get(_price_history_url(self.product.pk))
        self.assertIsInstance(resp.data, list)
