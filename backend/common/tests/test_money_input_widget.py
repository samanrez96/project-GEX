"""
Focused tests for the MoneyInput widget in common/admin.py.

Covers:
 - format_value(): comma separators, trailing-zero stripping, empty/None
 - value_from_datadict(): strip commas, normalise Persian/Arabic digits
 - HTML rendering: data-money-input attribute, inputmode=decimal
"""

from django import forms
from django.test import SimpleTestCase

from common.admin import MoneyInput


class MoneyInputFormatValueTest(SimpleTestCase):

    def setUp(self):
        self.widget = MoneyInput()

    def test_integer_value_gets_commas(self):
        self.assertEqual(self.widget.format_value('1000000'), '1,000,000')

    def test_decimal_value_strips_trailing_zeros(self):
        self.assertEqual(self.widget.format_value('15000.00'), '15,000')

    def test_decimal_value_keeps_significant_decimals(self):
        self.assertEqual(self.widget.format_value('1500.50'), '1,500.5')

    def test_small_value_no_commas(self):
        self.assertEqual(self.widget.format_value('999'), '999')

    def test_zero_value(self):
        self.assertEqual(self.widget.format_value('0'), '0')

    def test_none_returns_empty(self):
        self.assertEqual(self.widget.format_value(None), '')

    def test_empty_string_returns_empty(self):
        self.assertEqual(self.widget.format_value(''), '')

    def test_large_value(self):
        self.assertEqual(self.widget.format_value('4999950000'), '4,999,950,000')


class MoneyInputValueFromDatadictTest(SimpleTestCase):

    def setUp(self):
        self.widget = MoneyInput()

    def _get(self, raw):
        return self.widget.value_from_datadict({'field': raw}, {}, 'field')

    def test_strips_commas(self):
        self.assertEqual(self._get('1,000,000'), '1000000')

    def test_strips_multiple_commas(self):
        self.assertEqual(self._get('4,999,950,000'), '4999950000')

    def test_normalises_persian_digits(self):
        self.assertEqual(self._get('۱۵۰۰'), '1500')

    def test_normalises_arabic_indic_digits(self):
        self.assertEqual(self._get('٢٥٠٠'), '2500')

    def test_mixed_persian_and_commas(self):
        self.assertEqual(self._get('۱,۵۰۰,۰۰۰'), '1500000')

    def test_plain_ascii_digits_unchanged(self):
        self.assertEqual(self._get('12345'), '12345')

    def test_decimal_point_preserved(self):
        self.assertEqual(self._get('1,500.50'), '1500.50')

    def test_empty_string_returned_as_is(self):
        self.assertEqual(self._get(''), '')

    def test_none_data_returns_none(self):
        result = self.widget.value_from_datadict({}, {}, 'missing')
        self.assertIsNone(result)


class MoneyInputRenderTest(SimpleTestCase):

    def setUp(self):
        self.widget = MoneyInput()

    def test_renders_data_money_input_attribute(self):
        html = self.widget.render('amount', None)
        self.assertIn('data-money-input', html)

    def test_renders_inputmode_decimal(self):
        html = self.widget.render('amount', None)
        self.assertIn('inputmode="decimal"', html)

    def test_renders_as_text_input_not_number(self):
        html = self.widget.render('amount', None)
        self.assertIn('type="text"', html)
        self.assertNotIn('type="number"', html)

    def test_renders_formatted_existing_value(self):
        html = self.widget.render('amount', '2000000')
        self.assertIn('2,000,000', html)

    def test_custom_attrs_preserved(self):
        widget = MoneyInput(attrs={'placeholder': 'مبلغ'})
        html = widget.render('amount', None)
        self.assertIn('placeholder', html)


class MoneyInputFormIntegrationTest(SimpleTestCase):
    """MoneyInput works correctly as a DecimalField widget end-to-end."""

    class _TestForm(forms.Form):
        amount = forms.DecimalField(
            max_digits=14, decimal_places=2, widget=MoneyInput()
        )

    def test_form_cleans_comma_value(self):
        form = self._TestForm(data={'amount': '1,500,000'})
        self.assertTrue(form.is_valid(), form.errors)
        from decimal import Decimal
        self.assertEqual(form.cleaned_data['amount'], Decimal('1500000'))

    def test_form_cleans_persian_digit_value(self):
        form = self._TestForm(data={'amount': '۲۵۰۰'})
        self.assertTrue(form.is_valid(), form.errors)
        from decimal import Decimal
        self.assertEqual(form.cleaned_data['amount'], Decimal('2500'))

    def test_form_rejects_non_numeric(self):
        form = self._TestForm(data={'amount': 'abc'})
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
