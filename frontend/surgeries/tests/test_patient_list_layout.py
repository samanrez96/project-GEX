"""Rendering/regression tests for the Patient changelist layout.

The visibility filter (superuser-only) is rendered inline in the search
card as a compact <select> (see PatientVisibilityFilter.template /
visibility_filter_select.html) instead of Django's native
#changelist-filter sidebar, and the "وضعیت نمایش" table column has been
removed entirely — hidden/visible is filterable but no longer shown as a
per-row badge. These tests check the page renders the expected
structural markup (CSS itself isn't executed by the Django test client,
so this is a rendering/regression safety net, not a pixel-level check).
Full security/visibility behavior is already covered by
test_patient_visibility.py and is not re-tested here.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from surgeries.models import Patient

User = get_user_model()

LIST_URL = '/admin/surgeries/patient/'


def _patient(case_code, full_name, hidden=False):
    p = Patient.objects.create(
        full_name=full_name, case_code=case_code,
        phone_number='09120000000', national_id='5555555555',
    )
    if hidden:
        p.is_hidden = True
        p.save(update_fields=['is_hidden'])
    return p


def _staff_with_patient_perms():
    staff = User.objects.create_user(
        f'layout_staff_{User.objects.count()}', 'staff@t.com', 'pass123', is_staff=True,
    )
    staff.user_permissions.add(Permission.objects.get(codename='view_patient'))
    return staff


class PatientListLayoutSuperuserTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('layout_su', 'su@t.com', 'pass123')
        self.client.force_login(self.superuser)
        self.visible = _patient('DEMO-CASE-001', 'بیمار مشهود')
        self.hidden  = _patient('DEMO-CASE-002', 'بیمار مخفی', hidden=True)

    def test_page_loads(self):
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_patient_list_css_is_linked(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, 'admin/css/patient_list.css')

    def test_native_filter_sidebar_is_not_rendered(self):
        # Replaced by the inline filter row below — Django's own sidebar
        # markup must never render for this page anymore.
        resp = self.client.get(LIST_URL)
        self.assertNotContains(resp, 'id="changelist-filter"')

    def test_inline_filter_row_renders_for_superuser(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, 'pt-filter-row')
        self.assertContains(resp, 'pt-filter-select')

    def test_visibility_filter_options_present(self):
        resp = self.client.get(LIST_URL)
        content = resp.content.decode('utf-8')
        self.assertIn('قابل مشاهده', content)
        self.assertIn('مخفی', content)
        self.assertIn('وضعیت نمایش', content)

    def test_no_visibility_badge_column_in_table(self):
        # The status column/badge is removed for everyone, including the
        # main administrator — visibility is filterable only, never shown
        # as a per-row table column anymore.
        resp = self.client.get(LIST_URL)
        self.assertNotContains(resp, 'field-get_visibility_badge')
        self.assertNotContains(resp, 'column-get_visibility_badge')
        self.assertNotContains(resp, 'adm-badge--gray')
        self.assertNotContains(resp, 'adm-badge--green')

    def test_long_case_code_not_truncated_in_markup(self):
        # The value itself must appear in full in the rendered cell — the
        # CSS no longer forces ellipsis on case_code, and Django itself
        # never truncates the string server-side.
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, 'DEMO-CASE-002')

    def test_export_button_present_with_query_string_placeholder(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, '/admin/surgeries/patient/export-excel/')
        self.assertContains(resp, 'خروجی اکسل')

    def test_add_button_present(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, 'افزودن بیمار')

    def test_results_table_and_form_container_present(self):
        resp = self.client.get(LIST_URL)
        content = resp.content.decode('utf-8')
        self.assertIn('id="result_list"', content)
        self.assertIn('changelist-form-container', content)

    def test_filter_by_hidden_still_works(self):
        resp = self.client.get(LIST_URL, {'visibility': 'hidden'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'بیمار مخفی')
        self.assertNotContains(resp, 'بیمار مشهود')

    def test_filter_by_visible_still_works(self):
        resp = self.client.get(LIST_URL, {'visibility': 'visible'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'بیمار مشهود')
        self.assertNotContains(resp, 'بیمار مخفی')


class PatientListLayoutStaffTest(TestCase):

    def setUp(self):
        self.staff = _staff_with_patient_perms()
        self.client.force_login(self.staff)
        self.visible = _patient('DEMO-CASE-003', 'بیمار عادی')
        self.hidden  = _patient('DEMO-CASE-004', 'بیمار پنهان', hidden=True)

    def test_no_filter_sidebar_for_normal_staff(self):
        resp = self.client.get(LIST_URL)
        self.assertNotContains(resp, 'id="changelist-filter"')

    def test_no_inline_filter_row_for_normal_staff(self):
        resp = self.client.get(LIST_URL)
        self.assertNotContains(resp, 'pt-filter-row')
        self.assertNotContains(resp, 'pt-filter-select')
        self.assertNotContains(resp, 'وضعیت نمایش')

    def test_no_visibility_column_for_normal_staff(self):
        resp = self.client.get(LIST_URL)
        self.assertNotContains(resp, 'field-get_visibility_badge')
        self.assertNotContains(resp, 'column-get_visibility_badge')

    def test_table_still_renders_remaining_columns(self):
        resp = self.client.get(LIST_URL)
        content = resp.content.decode('utf-8')
        for cls in ('field-case_code', 'field-full_name', 'field-national_id', 'field-phone_number'):
            self.assertIn(cls, content)

    def test_hidden_patient_absent(self):
        resp = self.client.get(LIST_URL)
        self.assertNotContains(resp, 'بیمار پنهان')
        self.assertContains(resp, 'بیمار عادی')

    def test_export_button_present_for_staff(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, '/admin/surgeries/patient/export-excel/')

    def test_search_box_still_renders(self):
        resp = self.client.get(LIST_URL)
        self.assertContains(resp, 'id="toolbar"')
        self.assertContains(resp, 'id="changelist-search"')
