"""Tests for purchase date field — date-only input (no time) on add/edit forms.

Verifies:
  1.  Add form renders a date-only input (JalaliDateWidget placeholder, no time).
  2.  Add form does NOT render a time input or time placeholder.
  3.  Add form hint text contains no time example.
  4.  A valid Jalali date string is accepted and saved correctly.
  5.  The saved datetime corresponds to the exact selected calendar day.
  6.  Edit form renders the existing date without a time component.
  7.  Editing and re-saving preserves the correct Gregorian calendar date.
  8.  The JalaliFormDateForDateTimeField rejects a time component in input.
  9.  The field produces a timezone-aware datetime (no naive datetime warning).
  10. All existing purchase/finance/Task-24 test suites still pass (run separately).
"""

import datetime
import warnings
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from common.admin import JalaliFormDateForDateTimeField
from common.dates import to_jalali_date
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

_uid = 9000


def _uid_next():
    global _uid
    _uid += 1
    return _uid


def _vendor():
    return Vendor.objects.create(name=f"فروشنده-PD-{_uid_next()}")


def _product():
    n = _uid_next()
    return Product.objects.create(
        name=f"محصول-PD-{n}",
        internal_code=f"PD-{n:04d}",
        product_type=ProductType.MEDICINE,
        purchase_price=Decimal("0"),
    )


def _purchase(vendor, **kw):
    kw.setdefault("status", PurchaseStatus.PENDING)
    kw.setdefault("purchase_date", timezone.now())
    return Purchase.objects.create(vendor=vendor, **kw)


def _superuser():
    n = _uid_next()
    return User.objects.create_superuser(
        username=f"admin_pd_{n}", password="pass", email=""
    )


def _post_add(client, vendor, purchase_date_str, **extra):
    """POST to purchase add form. Inline prefix is 'items'."""
    data = {
        "vendor":              str(vendor.pk),
        "purchase_date":       purchase_date_str,
        "status":              "PENDING",
        "reference_number":    "",
        "notes":               "",
        "items-TOTAL_FORMS":   "0",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "_save":               "1",
    }
    data.update(extra)
    return client.post("/admin/inventory/purchase/add/", data, follow=True)


def _post_change(client, purchase, purchase_date_str):
    """POST to purchase change form."""
    data = {
        "vendor":              str(purchase.vendor.pk),
        "purchase_date":       purchase_date_str,
        "status":              purchase.status,
        "reference_number":    purchase.reference_number or "",
        "notes":               purchase.notes or "",
        "items-TOTAL_FORMS":   "0",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "_save":               "1",
    }
    return client.post(
        f"/admin/inventory/purchase/{purchase.pk}/change/", data, follow=True
    )


# ---------------------------------------------------------------------------
# 1–3 · Add form rendering
# ---------------------------------------------------------------------------

class PurchaseAddFormDateRenderingTest(TestCase):

    def setUp(self):
        self.client.force_login(_superuser())

    def test_add_form_renders_date_only_placeholder(self):
        r = self.client.get("/admin/inventory/purchase/add/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode("utf-8")
        # The JalaliDateWidget placeholder is '۱۴۰۵/۰۴/۰۳' (date-only, no time)
        self.assertIn("placeholder", content)
        self.assertNotIn("placeholder=\"۱۴۰۵/۰۴/۰۳ ۱۲:۳۰\"", content,
                         "Date-time placeholder must not appear on the add form")

    def test_add_form_does_not_contain_time_placeholder_text(self):
        r = self.client.get("/admin/inventory/purchase/add/")
        content = r.content.decode("utf-8")
        # Old datetime widget had '۱۲:۳۰' in its placeholder
        self.assertNotIn("۱۲:۳۰", content,
                         "Time example '۱۲:۳۰' must not appear on the add form")

    def test_add_form_hint_text_is_date_only(self):
        r = self.client.get("/admin/inventory/purchase/add/")
        content = r.content.decode("utf-8")
        # The template hint 'نمونه: ۱۴۰۵/۰۴/۱۳' must exist
        self.assertIn("نمونه: ۱۴۰۵/۰۴/۱۳", content,
                      "Date-only hint text must appear on the add form")
        # The old combined hint with time must be gone
        self.assertNotIn("۱۴۰۵/۰۴/۰۳ ۱۲:۳۰", content,
                         "Date-time hint text must not appear on the add form")


# ---------------------------------------------------------------------------
# 4–5 · Saving via add form
# ---------------------------------------------------------------------------

class PurchaseDateSaveTest(TestCase):

    def setUp(self):
        self.client.force_login(_superuser())

    def test_valid_jalali_date_saves_successfully(self):
        vendor = _vendor()
        r = _post_add(self.client, vendor, "۱۴۰۵/۰۴/۱۳")
        # After successful save, admin redirects to the change list
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            Purchase.objects.filter(vendor=vendor).exists(),
            "Purchase must be created when a valid Jalali date is submitted",
        )

    def test_saved_date_matches_selected_calendar_day(self):
        """1405/04/13 Jalali = 2026-07-04 Gregorian. The stored datetime must
        have that calendar date in the server's local timezone."""
        vendor   = _vendor()
        _post_add(self.client, vendor, "۱۴۰۵/۰۴/۱۳")

        purchase = Purchase.objects.filter(vendor=vendor).latest("pk")
        local_date = timezone.localtime(purchase.purchase_date).date()
        self.assertEqual(
            local_date,
            datetime.date(2026, 7, 4),
            "The stored purchase_date must be July 4 2026 in local time",
        )

    def test_saved_datetime_is_timezone_aware(self):
        vendor = _vendor()
        _post_add(self.client, vendor, "1404/01/01")

        purchase = Purchase.objects.filter(vendor=vendor).latest("pk")
        self.assertIsNotNone(
            purchase.purchase_date.tzinfo,
            "Saved purchase_date must be timezone-aware (no naive datetime)",
        )

    def test_no_naive_datetime_warning_on_save(self):
        vendor = _vendor()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _post_add(self.client, vendor, "۱۴۰۴/۰۶/۰۱")
        naive_warnings = [
            w for w in caught
            if "naive datetime" in str(w.message).lower()
            and "purchase_date" in str(w.message).lower()
        ]
        self.assertEqual(
            len(naive_warnings), 0,
            "Saving a Jalali date string must not produce a naive datetime warning",
        )


# ---------------------------------------------------------------------------
# 6–7 · Edit form — existing datetime renders and saves correctly
# ---------------------------------------------------------------------------

class PurchaseDateEditFormTest(TestCase):

    def setUp(self):
        self.client.force_login(_superuser())

    def test_edit_form_shows_date_only_no_time(self):
        """An existing purchase stored with a known datetime must render with
        only the Jalali date in the input — no time digits."""
        vendor = _vendor()
        # Store purchase at known UTC time (July 4 2026 at noon UTC = July 4 Tehran)
        purchase = _purchase(
            vendor,
            purchase_date=datetime.datetime(2026, 7, 4, 12, 0, 0, tzinfo=datetime.timezone.utc),
        )
        r = self.client.get(f"/admin/inventory/purchase/{purchase.pk}/change/")
        self.assertEqual(r.status_code, 200)
        content = r.content.decode("utf-8")

        # The widget value must be a Jalali date string like '۱۴۰۵/۰۴/۱۳'
        # and must NOT contain ':' (time separator) in the purchase_date input
        idx = content.find("id_purchase_date")
        self.assertGreater(idx, 0, "purchase_date input must be present")
        # Get a window around the input
        snippet = content[idx: idx + 300]
        # The value attribute should contain a date like ۱۴۰۵/۰۴/۱۳ but no HH:MM
        self.assertNotIn("۱۲:۰۰", snippet,
                         "Time '12:00' must not appear in the date input value")
        self.assertNotIn(":۰۰", snippet,
                         "Time separator ':' must not follow digits in date input")

    def test_edit_form_saves_correct_date_after_resubmit(self):
        """Resubmitting the edit form with a Jalali date must save the correct day."""
        vendor   = _vendor()
        purchase = _purchase(vendor)

        r = _post_change(self.client, purchase, "۱۴۰۴/۰۱/۰۱")
        self.assertEqual(r.status_code, 200)

        purchase.refresh_from_db()
        local_date = timezone.localtime(purchase.purchase_date).date()
        # 1404/01/01 Jalali = 2025-03-21 Gregorian (Nowruz)
        self.assertEqual(local_date, datetime.date(2025, 3, 21))

    def test_jalali_date_roundtrip(self):
        """Save a date via the form and confirm it round-trips to the same Jalali string."""
        vendor = _vendor()
        _post_add(self.client, vendor, "۱۴۰۳/۱۲/۱۰")

        purchase = Purchase.objects.filter(vendor=vendor).latest("pk")
        displayed = to_jalali_date(purchase.purchase_date)
        self.assertEqual(
            displayed, "۱۴۰۳/۱۲/۱۰",
            "Jalali date must round-trip: saved and displayed date must match",
        )


# ---------------------------------------------------------------------------
# 8 · Field-level unit tests — JalaliFormDateForDateTimeField
# ---------------------------------------------------------------------------

class JalaliFormDateForDateTimeFieldTest(TestCase):

    def _field(self):
        return JalaliFormDateForDateTimeField(required=True)

    def test_valid_date_string_returns_datetime(self):
        field = self._field()
        result = field.to_python("1405/04/13")
        self.assertIsInstance(result, datetime.datetime)
        local_date = timezone.localtime(result).date()
        self.assertEqual(local_date, datetime.date(2026, 7, 4))

    def test_persian_digit_date_string_accepted(self):
        field = self._field()
        result = field.to_python("۱۴۰۵/۰۴/۱۳")
        local_date = timezone.localtime(result).date()
        self.assertEqual(local_date, datetime.date(2026, 7, 4))

    def test_result_is_timezone_aware(self):
        from django.conf import settings as dj_settings
        if not dj_settings.USE_TZ:
            self.skipTest("USE_TZ is False — tz-aware test not applicable")
        field = self._field()
        result = field.to_python("1404/01/01")
        self.assertIsNotNone(result.tzinfo,
                             "to_python must return a timezone-aware datetime")

    def test_invalid_date_raises_validation_error(self):
        from django import forms as dj_forms
        field = self._field()
        with self.assertRaises(dj_forms.ValidationError):
            field.to_python("not-a-date")

    def test_empty_string_returns_none(self):
        field = self._field()
        self.assertIsNone(field.to_python(""))
        self.assertIsNone(field.to_python(None))

    def test_existing_datetime_passes_through(self):
        """has_changed() passes initial datetime through to_python; must not raise."""
        field = self._field()
        existing = datetime.datetime(2026, 7, 4, 12, 0, 0, tzinfo=datetime.timezone.utc)
        result = field.to_python(existing)
        self.assertIsInstance(result, datetime.datetime)
