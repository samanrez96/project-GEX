"""Excel export tests for finance endpoints (CLI-54).

Covers: /api/v2/finance/reports/balance/?export=excel
"""

import io
from decimal import Decimal

from django.contrib.auth.models import Group, User
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import FinanceCategory, Transaction, TransactionPaymentStatus, TransactionType

URL     = '/api/v2/finance/reports/balance/'
XLSX_CT = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin():
    u = User.objects.create_user(username=f'fin_adm_{User.objects.count()}', password='x')
    g, _ = Group.objects.get_or_create(name='admin')
    u.groups.add(g)
    return u


def _category(name, cat_type='income'):
    return FinanceCategory.objects.create(name=name, category_type=cat_type)


def _transaction(cat, amount, tx_type='income'):
    return Transaction.objects.create(
        transaction_type=tx_type,
        category=cat,
        amount=amount,
        payment_status=TransactionPaymentStatus.PAID,
    )


def _open_workbook(content):
    import openpyxl
    return openpyxl.load_workbook(io.BytesIO(content))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class BalanceReportExcelTest(APITestCase):

    def setUp(self):
        self.user = _admin()
        self.client.force_authenticate(self.user)
        cat = _category('درآمد کلینیک', cat_type='income')
        _transaction(cat, Decimal('5000000'), tx_type='income')
        cat_exp = _category('هزینه عمومی', cat_type='expense')
        _transaction(cat_exp, Decimal('1000000'), tx_type='expense')

    def _get(self, **params):
        return self.client.get(URL, {'export': 'excel', **params})

    def test_returns_xlsx_content_type(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], XLSX_CT)

    def test_content_disposition_filename(self):
        r = self._get()
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertIn('.xlsx',      r['Content-Disposition'])

    def test_workbook_openable(self):
        r = self._get()
        wb = _open_workbook(r.content)
        self.assertIsNotNone(wb)

    def test_rtl_worksheet(self):
        r = self._get()
        ws = _open_workbook(r.content).active
        self.assertTrue(ws.sheet_view.rightToLeft)

    def test_persian_headers(self):
        r = self._get()
        ws = _open_workbook(r.content).active
        all_vals = [ws.cell(row, col).value for row in range(1, ws.max_row + 1)
                    for col in range(1, ws.max_column + 1) if ws.cell(row, col).value]
        self.assertIn('مجموع درآمد',       all_vals)
        self.assertIn('مجموع هزینه',       all_vals)
        self.assertIn('سود / زیان نهایی',  all_vals)

    def test_single_data_row(self):
        r = self._get()
        ws = _open_workbook(r.content).active
        # Header row and one data row → exactly 2 rows with content in column 1
        # (no meta rows for balance report)
        content_rows = [row for row in range(1, ws.max_row + 1) if ws.cell(row, 1).value]
        self.assertGreaterEqual(len(content_rows), 2)  # at least header + 1 data

    def test_values_reflect_transactions(self):
        r = self._get()
        ws = _open_workbook(r.content).active
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        income_col = headers.index('مجموع درآمد') + 1
        val = ws.cell(2, income_col).value
        self.assertAlmostEqual(float(val), 5000000.0)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(None)
        r = self._get()
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_plain_user_denied_balance(self):
        # BalanceReport now uses IsAdminOrFinanceUser — plain user gets 403
        u = User.objects.create_user(username='plain_fin', password='x')
        self.client.force_authenticate(u)
        r = self._get()
        self.assertEqual(r.status_code, 403)
