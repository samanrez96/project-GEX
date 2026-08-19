"""API Permission Tests (CLI-64).

Tests the permission matrix for all sensitive API endpoints in the project.

Permission system overview:
  - Default: IsAuthenticated (JWT or session) — all authenticated users
  - IsAdminOrFinanceUser: superuser | admin group | finance_user group
  - IsAdminOrInventoryUser: superuser | admin group | inventory_user group
  - IsAdminOrEmployeeManager: superuser | admin group | employee_manager group

Permission_classes by endpoint:
  GET /api/v1/inventory/products/           → IsAuthenticated
  GET /api/v1/inventory/purchases/          → IsAuthenticated
  GET /api/v1/inventory/reports/stock/      → IsAuthenticated
  GET /api/v1/inventory/reports/cost/       → IsAdminOrFinanceUser  ← role-restricted
  GET /api/v1/employees/                    → IsAuthenticated
  GET /api/v1/payroll/wages/                → IsAuthenticated
  GET /api/v1/payroll/report/               → IsAdminOrFinanceUser  ← role-restricted (fix(api))
  GET /api/v1/payroll/reports/employee-cost/ → IsAdminOrFinanceUser ← role-restricted
  GET /api/v1/finance/categories/           → IsAuthenticated
  GET /api/v1/finance/transactions/         → IsAuthenticated
  GET /api/v1/finance/reports/balance/      → IsAdminOrFinanceUser  ← role-restricted (fix(api))
  GET /api/v1/surgeries/history/            → IsAuthenticated
  GET /api/v1/surgeries/reports/profit/     → IsAdminOrFinanceUser  ← role-restricted
  GET /api/v1/contacts/doctors/             → IsAuthenticated

NOT duplicated (already comprehensively covered in existing tests):
  - ProductCostReportView permissions  → inventory/tests/test_product_cost_report.py  (6 scenarios)
  - EmployeeCostReportView permissions → payroll/tests/test_employee_cost_report.py   (6 scenarios)
  - SurgeryProfitReportView permissions→ surgeries/tests/test_surgery_profit_report.py (5 scenarios)
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from accounts.permissions import (
    IsAdminOrFinanceUser,
    IsAdminOrInventoryUser,
    IsAdminOrEmployeeManager,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

PRODUCTS_URL          = '/api/v1/inventory/products/'
PURCHASES_URL         = '/api/v1/inventory/purchases/'
STOCK_REPORT_URL      = '/api/v1/inventory/reports/stock/'
COST_REPORT_URL       = '/api/v1/inventory/reports/cost/'
EMPLOYEES_URL         = '/api/v1/employees/'
WAGES_URL             = '/api/v1/payroll/wages/'
PAYROLL_REPORT_URL    = '/api/v1/payroll/report/'
EMP_COST_URL          = '/api/v1/payroll/reports/employee-cost/'
FINANCE_CAT_URL       = '/api/v1/finance/categories/'
FINANCE_TX_URL        = '/api/v1/finance/transactions/'
BALANCE_REPORT_URL    = '/api/v1/finance/reports/balance/'
SURGERY_HISTORY_URL   = '/api/v1/surgeries/history/'
SURGERY_PROFIT_URL    = '/api/v1/surgeries/reports/profit/'
CONTACTS_URL          = '/api/v1/contacts/doctors/'

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


# ---------------------------------------------------------------------------
# User factory helpers
# ---------------------------------------------------------------------------

_uid = 0


def _uid_str():
    global _uid
    _uid += 1
    return str(_uid).zfill(6)


def _user(username=None, groups=None, is_superuser=False):
    uid = _uid_str()
    u = User.objects.create_user(
        username=username or f'testuser_{uid}',
        password='testpass123',
    )
    if is_superuser:
        u.is_superuser = True
        u.is_staff = True
        u.save()
    for group_name in (groups or []):
        g, _ = Group.objects.get_or_create(name=group_name)
        u.groups.add(g)
    return u


def _superuser():    return _user(is_superuser=True)
def _admin():        return _user(groups=['admin'])
def _finance():      return _user(groups=['finance_user'])
def _inventory():    return _user(groups=['inventory_user'])
def _emp_manager():  return _user(groups=['employee_manager'])
def _regular():      return _user()   # no groups


# ---------------------------------------------------------------------------
# 1. Permission class unit tests
# ---------------------------------------------------------------------------

class IsAdminOrFinanceUserTest(APITestCase):
    """Direct unit tests for the IsAdminOrFinanceUser permission class.

    These test the logic of the permission class itself without going through
    the full API stack.
    """

    def setUp(self):
        self.factory    = APIRequestFactory()
        self.permission = IsAdminOrFinanceUser()

    def _allows(self, user):
        req = self.factory.get('/')
        req.user = user
        return self.permission.has_permission(req, None)

    def test_superuser_allowed(self):
        self.assertTrue(self._allows(_superuser()))

    def test_admin_group_allowed(self):
        self.assertTrue(self._allows(_admin()))

    def test_finance_user_allowed(self):
        self.assertTrue(self._allows(_finance()))

    def test_inventory_user_denied(self):
        self.assertFalse(self._allows(_inventory()))

    def test_employee_manager_denied(self):
        self.assertFalse(self._allows(_emp_manager()))

    def test_regular_user_denied(self):
        self.assertFalse(self._allows(_regular()))

    def test_unauthenticated_denied(self):
        from django.contrib.auth.models import AnonymousUser
        req = self.factory.get('/')
        req.user = AnonymousUser()
        self.assertFalse(self.permission.has_permission(req, None))


class IsAdminOrInventoryUserTest(APITestCase):
    """Direct unit tests for the IsAdminOrInventoryUser permission class."""

    def setUp(self):
        self.factory    = APIRequestFactory()
        self.permission = IsAdminOrInventoryUser()

    def _allows(self, user):
        req = self.factory.get('/')
        req.user = user
        return self.permission.has_permission(req, None)

    def test_superuser_allowed(self):
        self.assertTrue(self._allows(_superuser()))

    def test_admin_group_allowed(self):
        self.assertTrue(self._allows(_admin()))

    def test_inventory_user_allowed(self):
        self.assertTrue(self._allows(_inventory()))

    def test_finance_user_denied(self):
        self.assertFalse(self._allows(_finance()))

    def test_employee_manager_denied(self):
        self.assertFalse(self._allows(_emp_manager()))

    def test_regular_user_denied(self):
        self.assertFalse(self._allows(_regular()))


# ---------------------------------------------------------------------------
# 2. Unauthenticated access
# ---------------------------------------------------------------------------

class UnauthenticatedAccessTest(APITestCase):
    """All API endpoints must reject unauthenticated requests with 401."""

    def _check_401(self, url):
        resp = self.client.get(url)
        self.assertEqual(
            resp.status_code, status.HTTP_401_UNAUTHORIZED,
            f"Expected 401 for {url}, got {resp.status_code}",
        )

    def test_products_requires_auth(self):
        self._check_401(PRODUCTS_URL)

    def test_purchases_requires_auth(self):
        self._check_401(PURCHASES_URL)

    def test_stock_report_requires_auth(self):
        self._check_401(STOCK_REPORT_URL)

    def test_cost_report_requires_auth(self):
        self._check_401(COST_REPORT_URL)

    def test_employees_requires_auth(self):
        self._check_401(EMPLOYEES_URL)

    def test_wages_requires_auth(self):
        self._check_401(WAGES_URL)

    def test_payroll_report_requires_auth(self):
        self._check_401(PAYROLL_REPORT_URL)

    def test_employee_cost_report_requires_auth(self):
        self._check_401(EMP_COST_URL)

    def test_finance_categories_requires_auth(self):
        self._check_401(FINANCE_CAT_URL)

    def test_finance_transactions_requires_auth(self):
        self._check_401(FINANCE_TX_URL)

    def test_balance_report_requires_auth(self):
        self._check_401(BALANCE_REPORT_URL)

    def test_surgery_history_requires_auth(self):
        self._check_401(SURGERY_HISTORY_URL)

    def test_surgery_profit_report_requires_auth(self):
        self._check_401(SURGERY_PROFIT_URL)

    def test_contacts_requires_auth(self):
        self._check_401(CONTACTS_URL)


# ---------------------------------------------------------------------------
# 3. Finance user permissions
# ---------------------------------------------------------------------------

class FinanceUserPermissionTest(APITestCase):
    """Finance user should be able to access finance-related and IsAuthenticated endpoints."""

    def setUp(self):
        self.client.force_authenticate(user=_finance())

    def test_balance_report_allowed(self):
        resp = self.client.get(BALANCE_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_finance_categories_allowed(self):
        resp = self.client.get(FINANCE_CAT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_finance_transactions_allowed(self):
        resp = self.client.get(FINANCE_TX_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_employee_cost_report_allowed(self):
        """EmployeeCostReportView uses IsAdminOrFinanceUser — finance user should pass."""
        resp = self.client.get(EMP_COST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_surgery_profit_report_allowed(self):
        """SurgeryProfitReportView uses IsAdminOrFinanceUser — finance user should pass."""
        resp = self.client.get(SURGERY_PROFIT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_inventory_products_allowed(self):
        """Finance user can access IsAuthenticated inventory endpoints."""
        resp = self.client.get(PRODUCTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_payroll_report_allowed(self):
        """PayrollReportView now uses IsAdminOrFinanceUser; finance user is allowed."""
        resp = self.client.get(PAYROLL_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_surgery_history_allowed(self):
        resp = self.client.get(SURGERY_HISTORY_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cost_report_allowed(self):
        """ProductCostReportView uses IsAdminOrFinanceUser — finance user should pass."""
        resp = self.client.get(COST_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 4. Inventory user permissions
# ---------------------------------------------------------------------------

class InventoryUserPermissionTest(APITestCase):
    """Inventory user can access IsAuthenticated endpoints but not IsAdminOrFinanceUser."""

    def setUp(self):
        self.client.force_authenticate(user=_inventory())

    # ── Allowed (IsAuthenticated) ─────────────────────────────────────────

    def test_products_allowed(self):
        resp = self.client.get(PRODUCTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_purchases_allowed(self):
        resp = self.client.get(PURCHASES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_stock_report_allowed(self):
        resp = self.client.get(STOCK_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_balance_report_denied(self):
        """BalanceReportView now uses IsAdminOrFinanceUser; inventory user is denied."""
        resp = self.client.get(BALANCE_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_payroll_report_denied(self):
        """PayrollReportView now uses IsAdminOrFinanceUser; inventory user is denied."""
        resp = self.client.get(PAYROLL_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ── Denied (IsAdminOrFinanceUser) ─────────────────────────────────────

    def test_cost_report_denied(self):
        """ProductCostReportView uses IsAdminOrFinanceUser; inventory user is denied."""
        resp = self.client.get(COST_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_cost_report_denied(self):
        """EmployeeCostReportView uses IsAdminOrFinanceUser; inventory user is denied."""
        resp = self.client.get(EMP_COST_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_surgery_profit_report_denied(self):
        """SurgeryProfitReportView uses IsAdminOrFinanceUser; inventory user is denied."""
        resp = self.client.get(SURGERY_PROFIT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# 5. Admin user permissions
# ---------------------------------------------------------------------------

class AdminUserPermissionTest(APITestCase):
    """Admin group user has access to all endpoints including restricted reports."""

    def setUp(self):
        self.client.force_authenticate(user=_admin())

    def test_products_allowed(self):
        self.assertEqual(self.client.get(PRODUCTS_URL).status_code, 200)

    def test_purchases_allowed(self):
        self.assertEqual(self.client.get(PURCHASES_URL).status_code, 200)

    def test_stock_report_allowed(self):
        self.assertEqual(self.client.get(STOCK_REPORT_URL).status_code, 200)

    def test_cost_report_allowed(self):
        self.assertEqual(self.client.get(COST_REPORT_URL).status_code, 200)

    def test_employees_allowed(self):
        self.assertEqual(self.client.get(EMPLOYEES_URL).status_code, 200)

    def test_wages_allowed(self):
        self.assertEqual(self.client.get(WAGES_URL).status_code, 200)

    def test_payroll_report_allowed(self):
        self.assertEqual(self.client.get(PAYROLL_REPORT_URL).status_code, 200)

    def test_employee_cost_report_allowed(self):
        self.assertEqual(self.client.get(EMP_COST_URL).status_code, 200)

    def test_balance_report_allowed(self):
        self.assertEqual(self.client.get(BALANCE_REPORT_URL).status_code, 200)

    def test_surgery_history_allowed(self):
        self.assertEqual(self.client.get(SURGERY_HISTORY_URL).status_code, 200)

    def test_surgery_profit_report_allowed(self):
        self.assertEqual(self.client.get(SURGERY_PROFIT_URL).status_code, 200)

    def test_contacts_allowed(self):
        self.assertEqual(self.client.get(CONTACTS_URL).status_code, 200)


# ---------------------------------------------------------------------------
# 6. Regular user (no groups) permissions
# ---------------------------------------------------------------------------

class RegularUserPermissionTest(APITestCase):
    """Authenticated user with no group can access IsAuthenticated endpoints
    but is denied IsAdminOrFinanceUser endpoints."""

    def setUp(self):
        self.client.force_authenticate(user=_regular())

    # ── Allowed (IsAuthenticated) ─────────────────────────────────────────

    def test_stock_report_allowed(self):
        resp = self.client.get(STOCK_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # ── Denied (IsAdminOrFinanceUser) ─────────────────────────────────────

    def test_balance_report_denied(self):
        """BalanceReportView now uses IsAdminOrFinanceUser; regular user is denied."""
        resp = self.client.get(BALANCE_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_payroll_report_denied(self):
        """PayrollReportView now uses IsAdminOrFinanceUser; regular user is denied."""
        resp = self.client.get(PAYROLL_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cost_report_denied(self):
        resp = self.client.get(COST_REPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_cost_report_denied(self):
        resp = self.client.get(EMP_COST_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_surgery_profit_report_denied(self):
        resp = self.client.get(SURGERY_PROFIT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# 7. Excel export permissions
# ---------------------------------------------------------------------------

class ExcelExportPermissionTest(APITestCase):
    """?export=excel queries must respect the same permission_classes as
    the normal GET response — no permission bypass through the export path."""

    # ── Unauthenticated: always 401 ───────────────────────────────────────

    def test_balance_export_unauthenticated_denied(self):
        resp = self.client.get(BALANCE_REPORT_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_employee_cost_export_unauthenticated_denied(self):
        resp = self.client.get(EMP_COST_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_surgery_history_export_unauthenticated_denied(self):
        resp = self.client.get(SURGERY_HISTORY_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_products_export_unauthenticated_denied(self):
        resp = self.client.get(PRODUCTS_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── Inventory user: denied for IsAdminOrFinanceUser exports ──────────

    def test_employee_cost_export_inventory_user_denied(self):
        self.client.force_authenticate(user=_inventory())
        resp = self.client.get(EMP_COST_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotEqual(resp.get('Content-Type', ''), XLSX)

    def test_surgery_profit_export_inventory_user_denied(self):
        self.client.force_authenticate(user=_inventory())
        resp = self.client.get(SURGERY_PROFIT_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cost_report_export_inventory_user_denied(self):
        self.client.force_authenticate(user=_inventory())
        resp = self.client.get(COST_REPORT_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ── Finance user: allowed for IsAdminOrFinanceUser exports ────────────

    def test_employee_cost_export_finance_user_returns_xlsx(self):
        self.client.force_authenticate(user=_finance())
        resp = self.client.get(EMP_COST_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(XLSX, resp.get('Content-Type', ''))

    def test_balance_report_export_finance_user_returns_xlsx(self):
        """BalanceReportView is IsAuthenticated; finance user can export."""
        self.client.force_authenticate(user=_finance())
        resp = self.client.get(BALANCE_REPORT_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(XLSX, resp.get('Content-Type', ''))

    # ── Admin: allowed for all exports ────────────────────────────────────

    def test_employee_cost_export_admin_returns_xlsx(self):
        self.client.force_authenticate(user=_admin())
        resp = self.client.get(EMP_COST_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(XLSX, resp.get('Content-Type', ''))

    def test_surgery_profit_export_admin_returns_xlsx(self):
        self.client.force_authenticate(user=_admin())
        resp = self.client.get(SURGERY_PROFIT_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(XLSX, resp.get('Content-Type', ''))

    def test_products_export_admin_returns_xlsx(self):
        """Products export is IsAuthenticated; admin can export."""
        self.client.force_authenticate(user=_admin())
        resp = self.client.get(PRODUCTS_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(XLSX, resp.get('Content-Type', ''))

    def test_surgery_history_export_admin_returns_xlsx(self):
        self.client.force_authenticate(user=_admin())
        resp = self.client.get(SURGERY_HISTORY_URL, {'export': 'excel'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(XLSX, resp.get('Content-Type', ''))


# ---------------------------------------------------------------------------
# 8. CRUD mutation authentication
# ---------------------------------------------------------------------------

class MutationAuthTest(APITestCase):
    """Create/update/delete operations also require authentication."""

    def test_create_product_requires_auth(self):
        resp = self.client.post(PRODUCTS_URL, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_purchase_requires_auth(self):
        resp = self.client.post(PURCHASES_URL, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_surgery_requires_auth(self):
        resp = self.client.post(SURGERY_HISTORY_URL, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_wage_requires_auth(self):
        resp = self.client.post(WAGES_URL, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_finance_tx_requires_auth(self):
        resp = self.client.post(FINANCE_TX_URL, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# 9. Report permission matrix summary
# ---------------------------------------------------------------------------

class ReportPermissionMatrixTest(APITestCase):
    """Explicit permission matrix for all report endpoints.

    Endpoint                         | unauth | regular | inventory | finance | admin
    ----------------------------------|--------|---------|-----------|---------|------
    /inventory/reports/stock/        | 401    | 200     | 200       | 200     | 200
    /inventory/reports/cost/         | 401    | 403     | 403       | 200     | 200
    /payroll/report/                 | 401    | 403     | 403       | 200     | 200  (fix(api))
    /payroll/reports/employee-cost/  | 401    | 403     | 403       | 200     | 200
    /finance/reports/balance/        | 401    | 403     | 403       | 200     | 200  (fix(api))
    /surgeries/reports/profit/       | 401    | 403     | 403       | 200     | 200
    """

    REPORTS = [
        # (url, is_restricted)  — True = IsAdminOrFinanceUser, False = IsAuthenticated
        (STOCK_REPORT_URL,   False),
        (COST_REPORT_URL,    True),
        (PAYROLL_REPORT_URL, True),   # fix(api): was False
        (EMP_COST_URL,       True),
        (BALANCE_REPORT_URL, True),   # fix(api): was False
        (SURGERY_PROFIT_URL, True),
    ]

    def _assert_status(self, user, url, expected):
        if user:
            self.client.force_authenticate(user=user)
        else:
            self.client.force_authenticate(user=None)
        resp = self.client.get(url)
        self.assertEqual(
            resp.status_code, expected,
            f"User={getattr(user, 'username', 'anon')} URL={url}: "
            f"expected {expected}, got {resp.status_code}",
        )

    def test_unauthenticated_all_reports_401(self):
        for url, _ in self.REPORTS:
            with self.subTest(url=url):
                self._assert_status(None, url, 401)

    def test_regular_user_open_reports_200(self):
        u = _regular()
        for url, restricted in self.REPORTS:
            if not restricted:
                with self.subTest(url=url):
                    self._assert_status(u, url, 200)

    def test_regular_user_restricted_reports_403(self):
        u = _regular()
        for url, restricted in self.REPORTS:
            if restricted:
                with self.subTest(url=url):
                    self._assert_status(u, url, 403)

    def test_inventory_user_open_reports_200(self):
        u = _inventory()
        for url, restricted in self.REPORTS:
            if not restricted:
                with self.subTest(url=url):
                    self._assert_status(u, url, 200)

    def test_inventory_user_restricted_reports_403(self):
        u = _inventory()
        for url, restricted in self.REPORTS:
            if restricted:
                with self.subTest(url=url):
                    self._assert_status(u, url, 403)

    def test_finance_user_all_reports_200(self):
        u = _finance()
        for url, _ in self.REPORTS:
            with self.subTest(url=url):
                self._assert_status(u, url, 200)

    def test_admin_user_all_reports_200(self):
        u = _admin()
        for url, _ in self.REPORTS:
            with self.subTest(url=url):
                self._assert_status(u, url, 200)

    def test_superuser_all_reports_200(self):
        u = _superuser()
        for url, _ in self.REPORTS:
            with self.subTest(url=url):
                self._assert_status(u, url, 200)
