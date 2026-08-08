"""Admin page smoke tests for CLI-55 (RTL responsive).

Verifies that the custom-template contacts admin page:
  - returns HTTP 200 for a logged-in staff user
  - includes the rtl_responsive.css stylesheet
  - redirects anonymous users
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

CONTACTS_LIST_URL = '/admin/contacts/doctor/'


class ContactsAdminPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='ct_admin_ui', password='pass',
        )

    def test_contacts_list_returns_200(self):
        self.client.force_login(self.admin)
        resp = self.client.get(CONTACTS_LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_contacts_list_includes_rtl_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(CONTACTS_LIST_URL)
        self.assertContains(resp, 'rtl_responsive.css')

    def test_contacts_list_includes_contacts_css(self):
        self.client.force_login(self.admin)
        resp = self.client.get(CONTACTS_LIST_URL)
        self.assertContains(resp, 'contacts_directory.css')

    def test_contacts_list_redirects_anonymous(self):
        resp = self.client.get(CONTACTS_LIST_URL)
        self.assertIn(resp.status_code, (301, 302))
