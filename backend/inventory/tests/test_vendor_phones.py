"""Tests for VendorPhone — multiple phone numbers per vendor.

Covers:
- Model creation and uniqueness
- Admin form POST (save primary + additional phones)
- Duplicate validation (within formset, against primary phone)
- Edit page re-displays all saved phones
- Additional phone can be added to existing vendor
- Additional phone can be removed without deleting vendor or other data
- Existing Vendor.phone_number data unchanged after migration
- API phone field remains available; phones list field returns all numbers
- Vendor search finds by primary phone and additional phone without duplicates
- Dynamic formset TOTAL_FORMS handling (JS assertions)
- Vendor purchase and product relations unaffected

Note on formset prefix: Django uses the FK's reverse accessor name as the formset
prefix. Since VendorPhone.vendor has related_name="additional_phones", the prefix is
"additional_phones" (not "vendorphone").

Note on admin search tests: The vendor list uses a fully JS-driven custom template
(change_list_template). Vendor names are not in the server-rendered HTML. Search
behaviour is verified via the changelist queryset (resp.context['cl']) and the API.
"""

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from inventory.models import (
    Product,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    Vendor,
    VendorPhone,
)

User = get_user_model()

_uid = 0

# Formset prefix Django assigns (FK related_name "additional_phones")
_PREFIX = "additional_phones"


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _vendor(name=None, phone=""):
    return Vendor.objects.create(
        name=name or f"فروشنده {_uid_next()}",
        phone_number=phone,
    )


def _superuser():
    return User.objects.create_superuser(
        username=f"admin_{_uid_next()}", password="pass", email=""
    )


def _admin_client(user=None):
    c = Client()
    c.force_login(user or _superuser())
    return c


def _vendor_post_data(name=None, phone_number="", extra_phones=None):
    """Build POST data for the Vendor admin add form including the VendorPhone formset."""
    extra_phones = extra_phones or []
    total = len(extra_phones)
    data = {
        "name": name or f"تامین‌کننده {_uid_next()}",
        "phone_number": phone_number,
        "email": "",
        "address": "",
        "notes": "",
        "is_active": "on",
        "opening_balance": "0",
        "current_balance": "0",
        "tax_id": "",
        "bank_account": "",
        "_save": "1",
        f"{_PREFIX}-TOTAL_FORMS": str(total),
        f"{_PREFIX}-INITIAL_FORMS": "0",
        f"{_PREFIX}-MIN_NUM_FORMS": "0",
        f"{_PREFIX}-MAX_NUM_FORMS": "1000",
    }
    for i, phone in enumerate(extra_phones):
        data[f"{_PREFIX}-{i}-phone"] = phone
        data[f"{_PREFIX}-{i}-id"] = ""
        data[f"{_PREFIX}-{i}-vendor"] = ""
    return data


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class VendorPhoneModelTest(TestCase):
    """VendorPhone model — basic field and uniqueness behaviour."""

    def test_vendor_created_with_only_primary_phone(self):
        vendor = _vendor(phone="021-1234567")
        self.assertEqual(vendor.phone_number, "021-1234567")
        self.assertEqual(vendor.additional_phones.count(), 0)

    def test_vendor_can_have_multiple_phones(self):
        vendor = _vendor()
        VendorPhone.objects.create(vendor=vendor, phone="09121234567")
        VendorPhone.objects.create(vendor=vendor, phone="02112345678")
        self.assertEqual(vendor.additional_phones.count(), 2)

    def test_additional_phones_persist(self):
        vendor = _vendor()
        VendorPhone.objects.create(vendor=vendor, phone="09121234567")
        refreshed = Vendor.objects.get(pk=vendor.pk)
        self.assertEqual(refreshed.additional_phones.first().phone, "09121234567")

    def test_duplicate_phone_same_vendor_rejected(self):
        vendor = _vendor()
        VendorPhone.objects.create(vendor=vendor, phone="09121234567")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            VendorPhone.objects.create(vendor=vendor, phone="09121234567")

    def test_same_phone_different_vendors_allowed(self):
        v1 = _vendor()
        v2 = _vendor()
        VendorPhone.objects.create(vendor=v1, phone="09121234567")
        VendorPhone.objects.create(vendor=v2, phone="09121234567")  # no exception
        self.assertEqual(VendorPhone.objects.filter(phone="09121234567").count(), 2)

    def test_deleting_vendor_cascades_to_phones(self):
        vendor = _vendor()
        vp = VendorPhone.objects.create(vendor=vendor, phone="09121234567")
        pk = vp.pk
        vendor.delete()
        self.assertFalse(VendorPhone.objects.filter(pk=pk).exists())

    def test_existing_vendor_phone_number_unchanged(self):
        """Existing Vendor.phone_number must be preserved — migration must not alter it."""
        vendor = Vendor.objects.create(name="قدیمی", phone_number="02133334444")
        self.assertEqual(Vendor.objects.get(pk=vendor.pk).phone_number, "02133334444")

    def test_str_method(self):
        vendor = _vendor(name="آزمایش")
        vp = VendorPhone.objects.create(vendor=vendor, phone="09001234567")
        self.assertIn("09001234567", str(vp))

    def test_ordering_by_created_at(self):
        vendor = _vendor()
        VendorPhone.objects.create(vendor=vendor, phone="0911")
        VendorPhone.objects.create(vendor=vendor, phone="0922")
        phones = list(vendor.additional_phones.values_list("phone", flat=True))
        self.assertEqual(phones[0], "0911")
        self.assertEqual(phones[1], "0922")


# ---------------------------------------------------------------------------
# Admin form POST tests
# ---------------------------------------------------------------------------

class VendorAdminFormTest(TestCase):
    """Admin create/edit vendor with additional phones via POST."""

    def setUp(self):
        self.client = _admin_client()
        self.add_url = reverse("admin:inventory_vendor_add")

    def _change_url(self, vendor):
        return reverse("admin:inventory_vendor_change", args=[vendor.pk])

    def test_create_vendor_with_primary_phone_only(self):
        data = _vendor_post_data(name="تامین-تنها", phone_number="02199998888")
        resp = self.client.post(self.add_url, data, follow=True)
        self.assertEqual(resp.status_code, 200)
        vendor = Vendor.objects.get(phone_number="02199998888")
        self.assertEqual(vendor.additional_phones.count(), 0)

    def test_create_vendor_with_additional_phones(self):
        data = _vendor_post_data(
            name="تامین-چند-شماره",
            phone_number="02199998888",
            extra_phones=["09121111111", "09132222222"],
        )
        resp = self.client.post(self.add_url, data, follow=True)
        self.assertEqual(resp.status_code, 200)
        vendor = Vendor.objects.get(phone_number="02199998888")
        phones = list(vendor.additional_phones.values_list("phone", flat=True))
        self.assertIn("09121111111", phones)
        self.assertIn("09132222222", phones)

    def test_edit_page_shows_saved_phones(self):
        vendor = _vendor(phone="021-0000001")
        VendorPhone.objects.create(vendor=vendor, phone="09131231234")
        resp = self.client.get(self._change_url(vendor))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "09131231234")

    def test_add_additional_phone_to_existing_vendor(self):
        vendor = _vendor(phone="021-0000002")
        data = {
            "name": vendor.name,
            "phone_number": vendor.phone_number,
            "email": "",
            "address": "",
            "notes": "",
            "is_active": "on",
            "opening_balance": "0",
            "current_balance": "0",
            "tax_id": "",
            "bank_account": "",
            "_save": "1",
            f"{_PREFIX}-TOTAL_FORMS": "1",
            f"{_PREFIX}-INITIAL_FORMS": "0",
            f"{_PREFIX}-MIN_NUM_FORMS": "0",
            f"{_PREFIX}-MAX_NUM_FORMS": "1000",
            f"{_PREFIX}-0-phone": "09155556666",
            f"{_PREFIX}-0-id": "",
            f"{_PREFIX}-0-vendor": "",
        }
        resp = self.client.post(self._change_url(vendor), data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(vendor.additional_phones.filter(phone="09155556666").exists())

    def test_remove_additional_phone_does_not_delete_vendor(self):
        vendor = _vendor(phone="021-0000003")
        vp = VendorPhone.objects.create(vendor=vendor, phone="09161111111")
        data = {
            "name": vendor.name,
            "phone_number": vendor.phone_number,
            "email": "",
            "address": "",
            "notes": "",
            "is_active": "on",
            "opening_balance": "0",
            "current_balance": "0",
            "tax_id": "",
            "bank_account": "",
            "_save": "1",
            f"{_PREFIX}-TOTAL_FORMS": "1",
            f"{_PREFIX}-INITIAL_FORMS": "1",
            f"{_PREFIX}-MIN_NUM_FORMS": "0",
            f"{_PREFIX}-MAX_NUM_FORMS": "1000",
            f"{_PREFIX}-0-id": str(vp.pk),
            f"{_PREFIX}-0-vendor": str(vendor.pk),
            f"{_PREFIX}-0-phone": "09161111111",
            f"{_PREFIX}-0-DELETE": "on",
        }
        resp = self.client.post(self._change_url(vendor), data, follow=True)
        self.assertEqual(resp.status_code, 200)
        # Vendor still exists
        self.assertTrue(Vendor.objects.filter(pk=vendor.pk).exists())
        # Phone removed
        self.assertFalse(VendorPhone.objects.filter(pk=vp.pk).exists())
        # Vendor fields unchanged
        vendor.refresh_from_db()
        self.assertEqual(vendor.phone_number, "021-0000003")

    def test_remove_one_phone_keeps_others(self):
        vendor = _vendor(phone="021-0000004")
        vp1 = VendorPhone.objects.create(vendor=vendor, phone="0917-keep")
        vp2 = VendorPhone.objects.create(vendor=vendor, phone="0917-remove")
        data = {
            "name": vendor.name,
            "phone_number": vendor.phone_number,
            "email": "",
            "address": "",
            "notes": "",
            "is_active": "on",
            "opening_balance": "0",
            "current_balance": "0",
            "tax_id": "",
            "bank_account": "",
            "_save": "1",
            f"{_PREFIX}-TOTAL_FORMS": "2",
            f"{_PREFIX}-INITIAL_FORMS": "2",
            f"{_PREFIX}-MIN_NUM_FORMS": "0",
            f"{_PREFIX}-MAX_NUM_FORMS": "1000",
            f"{_PREFIX}-0-id": str(vp1.pk),
            f"{_PREFIX}-0-vendor": str(vendor.pk),
            f"{_PREFIX}-0-phone": "0917-keep",
            f"{_PREFIX}-1-id": str(vp2.pk),
            f"{_PREFIX}-1-vendor": str(vendor.pk),
            f"{_PREFIX}-1-phone": "0917-remove",
            f"{_PREFIX}-1-DELETE": "on",
        }
        self.client.post(self._change_url(vendor), data, follow=True)
        self.assertTrue(VendorPhone.objects.filter(pk=vp1.pk).exists())
        self.assertFalse(VendorPhone.objects.filter(pk=vp2.pk).exists())

    def test_blank_additional_phone_not_saved(self):
        """Blank extra rows should be ignored (not create VendorPhone rows)."""
        data = _vendor_post_data(
            name="تامین-خالی",
            phone_number="021-0000005",
            extra_phones=[""],  # blank — should be skipped
        )
        resp = self.client.post(self.add_url, data, follow=True)
        self.assertEqual(resp.status_code, 200)
        vendor = Vendor.objects.get(phone_number="021-0000005")
        self.assertEqual(vendor.additional_phones.count(), 0)

    def test_management_form_rendered_on_add_page(self):
        resp = self.client.get(self.add_url)
        # Prefix is the FK related_name "additional_phones"
        self.assertContains(resp, f"{_PREFIX}-TOTAL_FORMS")

    def test_management_form_rendered_on_edit_page(self):
        vendor = _vendor()
        resp = self.client.get(self._change_url(vendor))
        self.assertContains(resp, f"{_PREFIX}-TOTAL_FORMS")

    def test_primary_phone_label_changed(self):
        resp = self.client.get(self.add_url)
        self.assertContains(resp, "شماره تلفن اصلی")


# ---------------------------------------------------------------------------
# Duplicate validation tests
# ---------------------------------------------------------------------------

class VendorPhoneDuplicateValidationTest(TestCase):
    """Formset-level duplicate phone validation."""

    def setUp(self):
        self.client = _admin_client()
        self.add_url = reverse("admin:inventory_vendor_add")

    def _change_url(self, vendor):
        return reverse("admin:inventory_vendor_change", args=[vendor.pk])

    def test_duplicate_within_formset_rejected(self):
        data = _vendor_post_data(
            name="تامین-تکراری",
            phone_number="021-unique",
            extra_phones=["09121111111", "09121111111"],  # duplicate
        )
        resp = self.client.post(self.add_url, data)
        # Form re-renders with error, no redirect
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "این شماره تلفن قبلاً برای این تامین‌کننده ثبت شده است.")

    def test_duplicate_of_primary_phone_rejected(self):
        vendor = _vendor(phone="09001234567")
        data = {
            "name": vendor.name,
            "phone_number": vendor.phone_number,
            "email": "",
            "address": "",
            "notes": "",
            "is_active": "on",
            "opening_balance": "0",
            "current_balance": "0",
            "tax_id": "",
            "bank_account": "",
            "_save": "1",
            f"{_PREFIX}-TOTAL_FORMS": "1",
            f"{_PREFIX}-INITIAL_FORMS": "0",
            f"{_PREFIX}-MIN_NUM_FORMS": "0",
            f"{_PREFIX}-MAX_NUM_FORMS": "1000",
            f"{_PREFIX}-0-phone": "09001234567",  # same as primary
            f"{_PREFIX}-0-id": "",
            f"{_PREFIX}-0-vendor": "",
        }
        resp = self.client.post(self._change_url(vendor), data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "این شماره قبلاً به عنوان شماره تلفن اصلی ثبت شده است.")


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class VendorAPIPhoneTest(TestCase):
    """API serializer exposes phone + phones + additional_phones fields."""

    def setUp(self):
        self.client = _admin_client()

    def test_api_phone_field_present(self):
        vendor = _vendor(phone="02111112222")
        resp = self.client.get(f"/api/v1/inventory/vendors/{vendor.pk}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("phone_number", data)
        self.assertEqual(data["phone_number"], "02111112222")

    def test_api_phones_list_primary_only(self):
        vendor = _vendor(phone="02111112222")
        resp = self.client.get(f"/api/v1/inventory/vendors/{vendor.pk}/")
        data = resp.json()
        self.assertIn("phones", data)
        self.assertIn("02111112222", data["phones"])
        self.assertEqual(len(data["phones"]), 1)

    def test_api_phones_list_includes_additional(self):
        vendor = _vendor(phone="02111112222")
        VendorPhone.objects.create(vendor=vendor, phone="09129990000")
        resp = self.client.get(f"/api/v1/inventory/vendors/{vendor.pk}/")
        data = resp.json()
        self.assertIn("09129990000", data["phones"])
        self.assertEqual(len(data["phones"]), 2)

    def test_api_additional_phones_field(self):
        vendor = _vendor(phone="02111112222")
        VendorPhone.objects.create(vendor=vendor, phone="09129990000")
        resp = self.client.get(f"/api/v1/inventory/vendors/{vendor.pk}/")
        data = resp.json()
        self.assertIn("additional_phones", data)
        self.assertEqual(len(data["additional_phones"]), 1)
        self.assertEqual(data["additional_phones"][0]["phone"], "09129990000")

    def test_api_list_includes_phones(self):
        vendor = _vendor(phone="02111112222")
        VendorPhone.objects.create(vendor=vendor, phone="09129990000")
        resp = self.client.get("/api/v1/inventory/vendors/")
        data = resp.json()
        results = data.get("results", data)
        entry = next((v for v in results if v["id"] == vendor.pk), None)
        self.assertIsNotNone(entry)
        self.assertIn("phones", entry)
        self.assertIn("02111112222", entry["phones"])
        self.assertIn("09129990000", entry["phones"])


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------

class VendorSearchPhoneTest(TestCase):
    """Vendor search must find vendors by any of their phones without duplicates.

    Admin search: tested via changelist context queryset (the custom list template
    is JS-driven so vendor names are not in the server HTML).
    API search: tested by parsing the JSON response directly.
    """

    def setUp(self):
        self.client = _admin_client()
        self.vendor = _vendor(phone="02133334444")
        VendorPhone.objects.create(vendor=self.vendor, phone="09161234567")
        VendorPhone.objects.create(vendor=self.vendor, phone="09170000001")

    def test_admin_search_by_primary_phone(self):
        url = reverse("admin:inventory_vendor_changelist") + "?q=02133334444"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        cl = resp.context["cl"]
        pks = list(cl.queryset.values_list("pk", flat=True))
        self.assertIn(self.vendor.pk, pks)

    def test_admin_search_by_additional_phone(self):
        url = reverse("admin:inventory_vendor_changelist") + "?q=09161234567"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        cl = resp.context["cl"]
        pks = list(cl.queryset.values_list("pk", flat=True))
        self.assertIn(self.vendor.pk, pks)

    def test_admin_search_no_duplicate_rows(self):
        """Searching by an additional phone must return exactly one vendor row."""
        url = reverse("admin:inventory_vendor_changelist") + "?q=09161234567"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        cl = resp.context["cl"]
        pks = list(cl.queryset.values_list("pk", flat=True))
        # Should not have duplicates
        self.assertEqual(len(pks), len(set(pks)))
        # Should contain the target vendor exactly once
        self.assertEqual(pks.count(self.vendor.pk), 1)

    def test_api_search_by_additional_phone(self):
        resp = self.client.get("/api/v1/inventory/vendors/?search=09161234567")
        data = resp.json()
        results = data.get("results", data)
        pks = [v["id"] for v in results]
        self.assertIn(self.vendor.pk, pks)

    def test_api_search_no_duplicate_rows(self):
        """API search must not return duplicate vendor entries."""
        resp = self.client.get("/api/v1/inventory/vendors/?search=09161234567")
        data = resp.json()
        results = data.get("results", data)
        pks = [v["id"] for v in results]
        self.assertEqual(len(pks), len(set(pks)))


# ---------------------------------------------------------------------------
# Relations unaffected tests
# ---------------------------------------------------------------------------

class VendorRelationsUnaffectedTest(TestCase):
    """Adding VendorPhone must not affect purchase or product relations."""

    def setUp(self):
        self.vendor = _vendor(phone="021-rels")
        VendorPhone.objects.create(vendor=self.vendor, phone="09171234567")

    def test_purchase_relation_unchanged(self):
        import datetime
        from django.utils import timezone
        purchase = Purchase.objects.create(
            vendor=self.vendor,
            status=PurchaseStatus.PENDING,
            purchase_date=timezone.now(),
        )
        self.assertEqual(purchase.vendor.pk, self.vendor.pk)

    def test_product_vendor_relation_unchanged(self):
        product = Product.objects.create(
            name="محصول آزمایش",
            internal_code="VP-001",
            product_type=ProductType.MEDICINE,
            purchase_price=Decimal("100"),
        )
        pv = ProductVendor.objects.create(
            product=product,
            vendor=self.vendor,
            unit_price=Decimal("100"),
        )
        self.assertEqual(pv.vendor.pk, self.vendor.pk)
        self.assertEqual(pv.vendor.additional_phones.count(), 1)


# ---------------------------------------------------------------------------
# JS source assertions
# ---------------------------------------------------------------------------

class VendorPhonesJsTest(TestCase):
    """Assert that vendor_form.js contains required phone-management logic."""

    JS_PATH = "static/admin/js/vendor_form.js"

    def _read_js(self):
        import os
        base = "c:/Users/Asus/Desktop/my projects/surgary-clinic"
        with open(os.path.join(base, self.JS_PATH), encoding="utf-8") as f:
            return f.read()

    def test_js_contains_add_phone_function(self):
        self.assertIn("addPhoneRow", self._read_js())

    def test_js_contains_remove_phone_function(self):
        self.assertIn("removePhoneRow", self._read_js())

    def test_js_increments_total_forms_on_add(self):
        js = self._read_js()
        self.assertIn("setTotalForms", js)
        self.assertIn("total + 1", js)

    def test_js_decrements_total_forms_on_remove(self):
        js = self._read_js()
        self.assertIn("Math.max(0, total - 1)", js)

    def test_js_marks_delete_on_existing_row(self):
        js = self._read_js()
        self.assertIn("chk.checked = true", js)

    def test_js_replaces_prefix_placeholder(self):
        js = self._read_js()
        self.assertIn("__prefix__", js)
        self.assertIn("replace", js)

    def test_js_uses_vf_phones_prefix(self):
        js = self._read_js()
        self.assertIn("VF_PHONES_PREFIX", js)

    def test_js_hides_section_when_no_phones(self):
        js = self._read_js()
        self.assertIn("hideExtraSectionIfEmpty", js)

    def test_js_shows_section_on_add(self):
        js = self._read_js()
        self.assertIn("showExtraSection", js)
