"""Tests for the finance dashboard admin page."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

BALANCE_URL = '/api/v1/finance/reports/balance/'
TREND_URL   = '/api/v1/finance/reports/trend/'


class FinanceDashboardPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='dashboard_admin',
            password='adminpass',
        )

    def test_dashboard_page_loads_for_staff(self):
        """The dashboard admin page must return HTTP 200 for a logged-in staff user."""
        self.client.force_login(self.admin)
        resp = self.client.get('/admin/finance/dashboard/')
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_page_redirects_anonymous(self):
        """Anonymous users must be redirected to the login page."""
        resp = self.client.get('/admin/finance/dashboard/')
        self.assertIn(resp.status_code, (302, 301))


class FinanceAPIFiltersTest(APITestCase):
    """Verify that the Balance and Trend API endpoints accept the filter params
    the dashboard JS sends (regression guard for frontend ↔ backend contract)."""

    def setUp(self):
        from django.contrib.auth.models import Group
        self.user = User.objects.create_user(username='dash_api_user', password='pass')
        g, _ = Group.objects.get_or_create(name='finance_user')
        self.user.groups.add(g)
        self.client.force_authenticate(user=self.user)

    def test_balance_api_accepts_date_range_params(self):
        resp = self.client.get(BALANCE_URL, {
            'start_date': '2026-01-01',
            'end_date':   '2026-12-31',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('total_income',  resp.data)
        self.assertIn('total_expense', resp.data)
        self.assertIn('final_balance', resp.data)

    def test_balance_api_accepts_year_month_params(self):
        resp = self.client.get(BALANCE_URL, {'year': '2026', 'month': '3'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_trend_api_accepts_year_param(self):
        resp = self.client.get(TREND_URL, {'year': '2026'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)

    def test_balance_response_has_all_required_fields(self):
        resp = self.client.get(BALANCE_URL)
        required = [
            'total_income', 'total_expense', 'final_balance',
            'total_employee_cost', 'total_equipment_cost',
            'total_medicine_cost', 'center_commission_income',
        ]
        for field in required:
            self.assertIn(field, resp.data, f"Missing field: {field}")

    def test_unauthenticated_cannot_access_balance(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(BALANCE_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_cannot_access_trend(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(TREND_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
