"""Empty state tests for surgery history admin page (CLI-59)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()
URL  = '/admin/surgeries/surgeryhistory/'


class SurgeryHistoryEmptyStateTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='es_sh_admin', password='pass',
        )
        self.client.force_login(self.admin)

    def test_empty_states_css_included(self):
        resp = self.client.get(URL)
        self.assertContains(resp, 'empty_states.css')

    def test_empty_state_container_present(self):
        resp = self.client.get(URL)
        self.assertContains(resp, 'sh-empty-state')

    def test_empty_state_title_has_id(self):
        resp = self.client.get(URL)
        self.assertContains(resp, 'sh-empty-title')

    def test_no_data_title_is_correct_default(self):
        resp = self.client.get(URL)
        self.assertContains(resp, 'هنوز عملی ثبت نشده است')

    def test_clear_btn_label_updated(self):
        resp = self.client.get(URL)
        self.assertContains(resp, 'پاک کردن فیلترها')

    def test_add_first_btn_present(self):
        resp = self.client.get(URL)
        self.assertContains(resp, 'sh-add-first-btn')
