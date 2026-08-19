"""Empty state tests for inventory admin pages (CLI-59).

Verifies:
- empty_states.css is included in list page responses
- empty state containers exist in templates
- dynamic title and description elements exist
- clear-all button and add-first button are present
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

PRODUCT_LIST_URL  = '/admin/inventory/product/'
PURCHASE_LIST_URL = '/admin/inventory/purchase/'


class ProductListEmptyStateTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='es_inv_admin', password='pass',
        )
        self.client.force_login(self.admin)

    def test_empty_states_css_included(self):
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'empty_states.css')

    def test_empty_state_container_present(self):
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'pl-empty-state')

    def test_empty_state_title_has_id(self):
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'pl-empty-title')

    def test_empty_state_desc_has_id(self):
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'pl-empty-desc')

    def test_empty_state_clear_btn_present(self):
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'pl-clear-filters-all')

    def test_empty_state_add_btn_present(self):
        # Top-level add button replaces the old pl-add-first-btn
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'pl-add-btn')

    def test_no_data_title_is_correct_default(self):
        resp = self.client.get(PRODUCT_LIST_URL)
        self.assertContains(resp, 'هنوز محصولی ثبت نشده')


class PurchaseListEmptyStateTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='es_pu_admin', password='pass',
        )
        self.client.force_login(self.admin)

    def test_empty_states_css_included(self):
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'empty_states.css')

    def test_empty_state_container_present(self):
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'pu-empty-state')

    def test_empty_state_title_has_id(self):
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'pu-empty-title')

    def test_no_data_title_is_correct_default(self):
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'هنوز خریدی ثبت نشده است')

    def test_clear_btn_label_updated(self):
        resp = self.client.get(PURCHASE_LIST_URL)
        self.assertContains(resp, 'پاک کردن فیلترها')
