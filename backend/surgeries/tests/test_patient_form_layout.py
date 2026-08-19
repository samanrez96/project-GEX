"""Targeted rendering tests for the Patient add/change form layout cleanup.

Covers only markup/CSS-scoping concerns — Patient model fields, validation
rules, and hidden-Patient security are unchanged (see test_patient_admin.py,
test_patient_age_gender.py, test_patient_internal_code.py, and
test_patient_visibility.py for those, all still green after this change).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from surgeries.models import Gender, Patient

User = get_user_model()

_ctr = [0]


def _make_patient(**kwargs):
    _ctr[0] += 1
    defaults = {
        'full_name': f'بیمار چیدمان {_ctr[0]}',
        'case_code': f'LAYOUT-{_ctr[0]:05d}',
        'phone_number': '09120000000',
        'national_id': '5555555555',
        'age': 40,
        'gender': Gender.MALE,
    }
    defaults.update(kwargs)
    return Patient.objects.create(**defaults)


def _superuser(name='layout_superuser'):
    _ctr[0] += 1
    return User.objects.create_superuser(f'{name}_{_ctr[0]}', f'{name}{_ctr[0]}@example.com', 'pass12345')


def _staff_user(name='layout_staff'):
    _ctr[0] += 1
    return User.objects.create_user(f'{name}_{_ctr[0]}', f'{name}{_ctr[0]}@example.com', 'pass12345', is_staff=True)


class PatientFormAssetsAndGridTest(TestCase):
    """The add/change page loads the updated CSS and the new grid hooks."""

    def setUp(self):
        self.superuser = _superuser()
        self.client.force_login(self.superuser)

    def test_add_page_returns_200(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertEqual(resp.status_code, 200)

    def test_change_page_returns_200(self):
        patient = _make_patient()
        resp = self.client.get(f'/admin/surgeries/patient/{patient.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_page_loads_patient_form_css(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertContains(resp, 'patient_form.css')

    def test_form_card_class_present(self):
        """The CSS-grid hook class added to PatientAdmin.get_fieldsets()."""
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertContains(resp, 'patient-form-card')

    def test_status_section_class_present_for_superuser(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertContains(resp, 'patient-status-section')

    def test_all_patient_fields_render_on_add_form(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        content = resp.content.decode()
        for field_id in (
            'id_full_name', 'id_national_id', 'id_case_code', 'id_internal_code',
            'id_age', 'id_gender', 'id_phone_number', 'id_description',
        ):
            self.assertIn(field_id, content)

    def test_age_field_is_numeric_input(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        content = resp.content.decode()
        # Locate the actual <input id="id_age" ...> tag (not the <label
        # for="id_age"> that precedes it) and confirm it declares a
        # numeric type.
        marker = 'id="id_age"'
        marker_pos = content.index(marker)
        tag_start = content.rfind('<input', 0, marker_pos)
        tag_end = content.index('>', marker_pos)
        tag = content[tag_start:tag_end]
        self.assertIn('type="number"', tag)

    def test_gender_options_are_only_male_and_female(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        content = resp.content.decode()
        select_start = content.index('id_gender')
        select_end = content.index('</select>', select_start)
        select_html = content[select_start:select_end]
        self.assertIn('مرد', select_html)
        self.assertIn('زن', select_html)
        self.assertNotIn('سایر', select_html)

    def test_help_text_renders_for_case_code(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertContains(resp, 'کد پرونده باید منحصربه‌فرد باشد.')

    def test_help_text_renders_for_internal_code(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertContains(resp, 'اختیاری — در صورت تکمیل، باید منحصربه‌فرد باشد.')


class PatientFormHiddenControlPermissionTest(TestCase):
    """The hidden-Patient control (is_hidden) must stay superuser-only —
    unchanged by the layout work, just re-verified under the new markup."""

    def test_superuser_sees_is_hidden_field(self):
        self.client.force_login(_superuser())
        patient = _make_patient()
        resp = self.client.get(f'/admin/surgeries/patient/{patient.pk}/change/')
        self.assertContains(resp, 'id_is_hidden')

    def test_normal_staff_does_not_see_is_hidden_field(self):
        staff = _staff_user()
        staff.user_permissions.clear()
        from django.contrib.auth.models import Permission
        for codename in ('view_patient', 'change_patient'):
            perm = Permission.objects.get(codename=codename)
            staff.user_permissions.add(perm)
        self.client.force_login(staff)
        patient = _make_patient()
        resp = self.client.get(f'/admin/surgeries/patient/{patient.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('id_is_hidden', resp.content.decode())
        self.assertNotContains(resp, 'patient-status-section')


class PatientFormValidationPreservesValuesTest(TestCase):
    """Invalid submissions must still re-render with the submitted values
    and errors visible — the layout change must not swallow either."""

    def setUp(self):
        self.superuser = _superuser()
        self.client.force_login(self.superuser)

    def test_invalid_submission_preserves_submitted_values(self):
        _make_patient(case_code='DUPLICATE-CODE')
        resp = self.client.post('/admin/surgeries/patient/add/', {
            'full_name': 'بیمار تکراری',
            'national_id': '1112223334',
            'case_code': 'DUPLICATE-CODE',  # triggers uniqueness error
            'phone_number': '09121234567',
            'age': '33',
            'gender': Gender.FEMALE,
            'description': '',
        })
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors, not redirected
        content = resp.content.decode()
        self.assertIn('errorlist', content)
        self.assertIn('value="بیمار تکراری"', content)
        self.assertIn('value="1112223334"', content)
        self.assertIn('value="33"', content)

    def test_missing_age_shows_error_and_preserves_other_fields(self):
        resp = self.client.post('/admin/surgeries/patient/add/', {
            'full_name': 'بیمار بدون سن',
            'national_id': '',
            'case_code': 'NEW-CODE-001',
            'phone_number': '09121234567',
            'gender': Gender.MALE,
            'description': '',
        })
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('errorlist', content)
        self.assertIn('value="بیمار بدون سن"', content)


class PatientCreateEditRegressionTest(TestCase):
    """Confirms Patient creation/editing itself — untouched business logic
    — still works end to end through the redesigned form."""

    def setUp(self):
        self.superuser = _superuser()
        self.client.force_login(self.superuser)

    def test_create_patient_via_form(self):
        resp = self.client.post('/admin/surgeries/patient/add/', {
            'full_name': 'بیمار جدید فرم',
            'national_id': '4443332221',
            'case_code': 'FORM-NEW-001',
            'phone_number': '09129998877',
            'age': '27',
            'gender': Gender.FEMALE,
            'description': 'یادداشت آزمایشی',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        patient = Patient.objects.get(case_code='FORM-NEW-001')
        self.assertEqual(patient.age, 27)
        self.assertEqual(patient.gender, Gender.FEMALE)

    def test_edit_patient_via_form(self):
        patient = _make_patient(age=30, gender=Gender.MALE)
        resp = self.client.post(f'/admin/surgeries/patient/{patient.pk}/change/', {
            'full_name': patient.full_name,
            'national_id': patient.national_id,
            'case_code': patient.case_code,
            'phone_number': patient.phone_number,
            'age': '31',
            'gender': Gender.MALE,
            'description': '',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        patient.refresh_from_db()
        self.assertEqual(patient.age, 31)
