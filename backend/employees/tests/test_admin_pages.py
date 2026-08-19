"""Admin page smoke tests for CLI-55 (RTL responsive).

Verifies that all custom-template employee admin pages:
  - return HTTP 200 for a logged-in staff user
  - include the rtl_responsive.css stylesheet
  - redirect anonymous users
"""

import datetime
import random

from django.contrib.auth import get_user_model
from django.test import TestCase

from employees.models import Employee, JobPosition

User = get_user_model()

EMPLOYEE_LIST_URL = '/admin/employees/employee/'


def _position():
    return JobPosition.objects.create(name=f'پوزیشن_{random.randint(10000, 99999)}')


def _employee(position):
    uid = random.randint(1000000000, 9999999999)
    return Employee.objects.create(
        full_name='کارمند آزمایشی',
        national_id=str(uid),
        gender='female',
        job_position=position,
        start_date=datetime.date(2023, 1, 1),
        personal_phone='09100000001',
        emergency_contact_phone='09200000001',
    )


class EmployeeAdminPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='emp_admin_ui', password='pass',
        )
        self.pos = _position()
        self.employee = _employee(self.pos)

    def test_employee_list_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_employee_list_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertContains(resp, 'rtl_responsive.css')

    def test_employee_list_includes_employee_list_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertContains(resp, 'employee_list.css')

    def test_employee_list_includes_global_search_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertContains(resp, 'global_search.js')

    def test_employee_list_includes_table_pagination_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertContains(resp, 'table_pagination.js')

    def test_employee_list_includes_table_filters_js(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertContains(resp, 'table_filters.js')

    def test_employee_list_has_sort_controls(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertContains(resp, 'em-sort-by')
        self.assertContains(resp, 'em-sort-dir')

    def test_employee_list_search_input_has_data_attribute(self):
        self.client.force_login(self.admin)
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertContains(resp, 'data-global-search')

    def test_employee_list_redirects_anonymous(self):
        resp = self.client.get(EMPLOYEE_LIST_URL)
        self.assertIn(resp.status_code, (301, 302))

    # ── Change (edit) form ────────────────────────────────────────────

    def test_employee_change_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/employees/employee/{self.employee.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_employee_change_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/employees/employee/{self.employee.pk}/change/')
        self.assertContains(resp, 'rtl_responsive.css')

    def test_employee_change_includes_payroll_section(self):
        """The edit form must contain the wage_type field (payroll fieldset)."""
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/employees/employee/{self.employee.pk}/change/')
        self.assertContains(resp, 'wage_type')

    # ── Detail (read-only tab view) ───────────────────────────────────

    def test_employee_detail_view_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/employees/employee/{self.employee.pk}/detail/')
        self.assertEqual(resp.status_code, 200)

    def test_employee_detail_view_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/employees/employee/{self.employee.pk}/detail/')
        self.assertContains(resp, 'rtl_responsive.css')

    def test_employee_detail_view_includes_employee_detail_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/admin/employees/employee/{self.employee.pk}/detail/')
        self.assertContains(resp, 'employee_detail.css')
