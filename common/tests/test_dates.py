import datetime

from django.test import TestCase
from django.utils import timezone

from common.dates import (
    jalali_to_iso,
    normalize_digits,
    parse_jalali_date,
    to_jalali_date,
    to_jalali_datetime,
)


class ToJalaliDateTests(TestCase):

    def test_nowruz(self):
        # 2025-03-21 is 1404/01/01 (Nowruz — Spring equinox)
        self.assertEqual(to_jalali_date(datetime.date(2025, 3, 21)), '۱۴۰۴/۰۱/۰۱')

    def test_none_returns_dash(self):
        self.assertEqual(to_jalali_date(None), '—')

    def test_persian_digits_only(self):
        result = to_jalali_date(datetime.date(2025, 3, 21))
        for ch in result:
            if ch == '/':
                continue
            self.assertIn(ch, '۰۱۲۳۴۵۶۷۸۹', f'Non-Persian digit found: {ch!r}')

    def test_zero_padded_month_and_day(self):
        # Month 1, day 1 must be zero-padded to 2 digits
        result = to_jalali_date(datetime.date(2025, 3, 21))
        parts = result.split('/')
        self.assertEqual(len(parts), 3)
        self.assertEqual(len(parts[1]), 2)
        self.assertEqual(len(parts[2]), 2)

    def test_datetime_input_returns_date_string(self):
        # Aware datetime → strips time, returns date part
        dt = datetime.datetime(2025, 3, 21, 12, 0, tzinfo=datetime.timezone.utc)
        result = to_jalali_date(dt)
        self.assertIn('۱۴۰۴', result)

    def test_invalid_type_returns_dash(self):
        self.assertEqual(to_jalali_date('2025-03-21'), '—')
        self.assertEqual(to_jalali_date(42), '—')

    def test_known_mid_year_date(self):
        # 2025-06-17 → 1404/03/27
        self.assertEqual(to_jalali_date(datetime.date(2025, 6, 17)), '۱۴۰۴/۰۳/۲۷')

    def test_end_of_year(self):
        # 2025-03-20 is 1403/12/29 (last day of 1403)
        result = to_jalali_date(datetime.date(2025, 3, 20))
        self.assertTrue(result.startswith('۱۴۰۳'))

    def test_esfand_month_12_not_negative(self):
        # Regression: Esfand (month 12) dates used to render with negative
        # days (e.g. '۱۴۰۳/۱۲/-۲۹'). 2025-03-15 == 1403/12/25.
        self.assertEqual(to_jalali_date(datetime.date(2025, 3, 15)), '۱۴۰۳/۱۲/۲۵')


class ParseJalaliDateTests(TestCase):

    def test_jalali_slash_to_gregorian(self):
        # 1405/04/03 == 2026-06-24 (the spec example)
        self.assertEqual(
            parse_jalali_date('1405/04/03'), datetime.date(2026, 6, 24)
        )

    def test_jalali_dash_separator(self):
        self.assertEqual(
            parse_jalali_date('1405-04-03'), datetime.date(2026, 6, 24)
        )

    def test_persian_digits_accepted(self):
        self.assertEqual(
            parse_jalali_date('۱۴۰۵/۰۴/۰۳'), datetime.date(2026, 6, 24)
        )

    def test_arabic_digits_accepted(self):
        self.assertEqual(
            parse_jalali_date('١٤٠٥/٠٤/٠٣'), datetime.date(2026, 6, 24)
        )

    def test_esfand_input(self):
        # 1404/12/01 == 2026-02-20 — month 12 parses correctly
        self.assertEqual(
            parse_jalali_date('1404/12/01'), datetime.date(2026, 2, 20)
        )

    def test_none_returns_none(self):
        self.assertIsNone(parse_jalali_date(None))

    def test_blank_returns_none(self):
        self.assertIsNone(parse_jalali_date('   '))

    def test_gregorian_iso_passthrough(self):
        # Existing Gregorian query params (year >= 1700) still resolve.
        self.assertEqual(
            parse_jalali_date('2026-06-24'), datetime.date(2026, 6, 24)
        )

    def test_date_object_passthrough(self):
        d = datetime.date(2026, 6, 24)
        self.assertEqual(parse_jalali_date(d), d)

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            parse_jalali_date('1405/4')

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            parse_jalali_date('abcd/ef/gh')

    def test_out_of_range_jalali_raises(self):
        with self.assertRaises(ValueError):
            parse_jalali_date('1405/13/40')

    def test_roundtrip_display_then_parse(self):
        # Display (forward, pure-Python) and parse (backward, jdatetime) agree.
        for d in [datetime.date(2026, 6, 24), datetime.date(2025, 3, 15),
                  datetime.date(2024, 1, 1), datetime.date(2026, 2, 20)]:
            jalali = to_jalali_date(d)            # Persian-digit string
            self.assertEqual(parse_jalali_date(jalali), d)


class JalaliToIsoTests(TestCase):

    def test_returns_iso_string(self):
        self.assertEqual(jalali_to_iso('1405/04/03'), '2026-06-24')

    def test_none_for_blank(self):
        self.assertIsNone(jalali_to_iso(''))
        self.assertIsNone(jalali_to_iso(None))

    def test_gregorian_passthrough(self):
        self.assertEqual(jalali_to_iso('2026-06-24'), '2026-06-24')


class NormalizeDigitsTests(TestCase):

    def test_persian_to_ascii(self):
        self.assertEqual(normalize_digits('۱۴۰۵'), '1405')

    def test_arabic_to_ascii(self):
        self.assertEqual(normalize_digits('١٤٠٥'), '1405')

    def test_none_is_empty(self):
        self.assertEqual(normalize_digits(None), '')


class AdminJalaliFormFieldTests(TestCase):

    def test_datefield_parses_jalali(self):
        from common.admin import JalaliFormDateField
        f = JalaliFormDateField(required=False)
        self.assertEqual(f.clean('1405/04/03'), datetime.date(2026, 6, 24))

    def test_datefield_blank_returns_none(self):
        from common.admin import JalaliFormDateField
        f = JalaliFormDateField(required=False)
        self.assertIsNone(f.clean(''))

    def test_datefield_invalid_raises(self):
        from django.core.exceptions import ValidationError
        from common.admin import JalaliFormDateField
        f = JalaliFormDateField(required=False)
        with self.assertRaises(ValidationError):
            f.clean('1405/13/40')

    def test_datefield_widget_displays_jalali(self):
        from common.admin import JalaliDateWidget
        w = JalaliDateWidget()
        self.assertEqual(w.format_value(datetime.date(2026, 6, 24)), '۱۴۰۵/۰۴/۰۳')

    def test_datetimefield_preserves_time(self):
        from common.admin import JalaliFormDateTimeField
        f = JalaliFormDateTimeField(required=False)
        result = f.clean('1405/04/03 14:30')
        self.assertEqual((result.year, result.month, result.day), (2026, 6, 24))
        self.assertEqual((result.hour, result.minute), (14, 30))

    def test_datetimefield_date_only_defaults_midnight(self):
        from common.admin import JalaliFormDateTimeField
        f = JalaliFormDateTimeField(required=False)
        result = f.clean('۱۴۰۵/۰۴/۰۳')   # Persian digits, no time
        self.assertEqual((result.year, result.month, result.day), (2026, 6, 24))
        self.assertEqual((result.hour, result.minute), (0, 0))


class ToJalaliDatetimeTests(TestCase):

    def test_aware_datetime(self):
        dt = datetime.datetime(2025, 3, 21, 10, 30, tzinfo=datetime.timezone.utc)
        result = to_jalali_datetime(dt)
        self.assertIn('۱۴۰۴', result)
        self.assertIn(':', result)

    def test_none_returns_dash(self):
        self.assertEqual(to_jalali_datetime(None), '—')

    def test_time_part_has_persian_digits(self):
        dt = datetime.datetime(2025, 3, 21, 9, 5, tzinfo=datetime.timezone.utc)
        result = to_jalali_datetime(dt)
        # Time part should appear as Persian digits
        for ch in result:
            if ch in '/ :':
                continue
            self.assertIn(ch, '۰۱۲۳۴۵۶۷۸۹', f'Non-Persian digit: {ch!r}')

    def test_date_only_input(self):
        d = datetime.date(2025, 3, 21)
        result = to_jalali_datetime(d)
        self.assertEqual(result, '۱۴۰۴/۰۱/۰۱')

    def test_invalid_type_returns_dash(self):
        self.assertEqual(to_jalali_datetime('2025-03-21T10:30'), '—')


class ExcelJalaliTests(TestCase):

    def test_excel_cell_value_uses_jalali(self):
        from common.excel import _cell_value
        d = datetime.date(2025, 3, 21)
        self.assertEqual(_cell_value(d), '۱۴۰۴/۰۱/۰۱')

    def test_excel_cell_value_none_is_empty(self):
        from common.excel import _cell_value
        self.assertEqual(_cell_value(None), '')

    def test_excel_cell_value_datetime_uses_jalali(self):
        from common.excel import _cell_value
        import datetime
        dt = datetime.datetime(2025, 3, 21, 10, 30, tzinfo=datetime.timezone.utc)
        result = _cell_value(dt)
        self.assertIn('۱۴۰۴', result)
