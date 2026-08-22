"""Tests for Phase 4: custom admin index dashboard.

Verifies that /admin/ renders the custom Persian RTL dashboard and
no longer shows the default Django Admin module-list content.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

ADMIN_INDEX_URL = '/admin/'


class AdminIndexDashboardTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='dash_admin', password='pass',
        )

    # ── Authentication ─────────────────────────────────────────────

    def test_index_returns_200_for_staff(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertEqual(resp.status_code, 200)

    def test_index_redirects_anonymous(self):
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertIn(resp.status_code, (301, 302))

    # ── Custom content present ─────────────────────────────────────

    def test_index_contains_dashboard_title(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'داشبورد اصلی')

    def test_index_contains_section_label(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'نمای کلی مرکز')

    def test_index_loads_dashboard_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'main_dashboard.css')

    def test_index_loads_dashboard_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'main_dashboard.js')

    def test_index_contains_metric_card_root(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'id="md-cards"')

    def test_index_contains_recent_surgeries_table(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'id="md-surgeries-tbody"')

    def test_index_contains_api_balance_variable(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'MD_API_BALANCE')

    def test_index_contains_api_history_variable(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'MD_API_HISTORY')

    # ── Default Django app list NOT present ────────────────────────

    def test_index_excludes_default_app_list_inventory(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        # Django's default app list renders class="app-inventory"
        self.assertNotContains(resp, 'class="app-inventory"')

    def test_index_excludes_default_app_list_employees(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertNotContains(resp, 'class="app-employees"')

    def test_index_excludes_default_app_list_finance(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertNotContains(resp, 'class="app-finance"')

    # ── Shared layout still present ────────────────────────────────

    def test_index_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'rtl_responsive.css')

    def test_index_includes_shared_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'shared.css')

    def test_index_includes_custom_admin_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'custom_admin.css')

    # ── Other admin pages still work ───────────────────────────────

    def test_product_list_still_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/inventory/product/')
        self.assertEqual(resp.status_code, 200)

    def test_surgery_list_still_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/surgeries/surgeryhistory/')
        self.assertEqual(resp.status_code, 200)

    def test_finance_dashboard_still_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/finance/dashboard/')
        self.assertEqual(resp.status_code, 200)

    # ── Accordion sidebar structure ─────────────────────────────────

    def test_sidebar_has_accordion_sections(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'data-sidebar-section')

    def test_sidebar_has_toggle_buttons(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'ca-nav-toggle')

    def test_sidebar_has_submenu_links(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'ca-nav-link')

    def test_sidebar_contains_admin_home_link(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, 'داشبورد اصلی')

    def test_sidebar_contains_inventory_links(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, '/admin/inventory/product/')

    def test_sidebar_contains_surgery_link(self):
        self.client.force_login(self.admin)
        resp = self.client.get(ADMIN_INDEX_URL)
        self.assertContains(resp, '/admin/surgeries/surgeryhistory/')
