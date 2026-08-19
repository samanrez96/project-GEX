"""Phase 3 correction tests: Doctor admin URLs, doctorcontact compat
redirects, the removed standalone Specialty admin, and the in-form
Specialty create/delete utility endpoints.
"""
import datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from contacts.models import Doctor, DoctorSpecialty
from surgeries.models import SurgeryHistory, SurgeryType

User = get_user_model()


def _static_source(*parts):
    return Path(settings.BASE_DIR).joinpath('static', *parts).read_text(encoding='utf-8')


def make_specialty(name='جراحی عمومی'):
    obj, _ = DoctorSpecialty.objects.get_or_create(name=name)
    return obj


def make_doctor(**kwargs):
    defaults = {
        'full_name': 'دکتر تست',
        'specialty': make_specialty(),
        'phone_number': '09120000000',
    }
    defaults.update(kwargs)
    return Doctor.objects.create(**defaults)


class DoctorAdminUrlTest(TestCase):
    """A. Doctor admin URLs must be reachable at the renamed model paths."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='ds_admin', password='pass')
        self.client.force_login(self.superuser)

    def test_doctor_changelist_returns_200(self):
        resp = self.client.get('/admin/contacts/doctor/')
        self.assertEqual(resp.status_code, 200)

    def test_doctor_change_returns_200_for_existing_doctor(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_doctor_retains_data(self):
        doc = make_doctor(full_name='دکتر پایدار', phone_number='09121112233')
        doc.refresh_from_db()
        self.assertEqual(doc.full_name, 'دکتر پایدار')
        self.assertEqual(doc.phone_number, '09121112233')

    def test_doctor_add_returns_200(self):
        resp = self.client.get('/admin/contacts/doctor/add/')
        self.assertEqual(resp.status_code, 200)


class DoctorContactCompatRedirectTest(TestCase):
    """B. Old bookmarked DoctorContact URLs must redirect, not 404."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='ds_admin2', password='pass')
        self.client.force_login(self.superuser)

    def test_old_changelist_url_redirects_to_doctor_changelist(self):
        resp = self.client.get('/admin/contacts/doctorcontact/')
        self.assertIn(resp.status_code, (301, 302))
        self.assertEqual(resp.url, reverse('admin:contacts_doctor_changelist'))

    def test_old_change_url_redirects_preserving_id(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctorcontact/{doc.pk}/change/')
        self.assertIn(resp.status_code, (301, 302))
        self.assertEqual(resp.url, reverse('admin:contacts_doctor_change', args=[doc.pk]))

    def test_old_change_url_404s_for_nonexistent_doctor(self):
        resp = self.client.get('/admin/contacts/doctorcontact/999999/change/')
        self.assertEqual(resp.status_code, 404)

    def test_compat_redirect_requires_authentication(self):
        anon = Client()
        resp = anon.get('/admin/contacts/doctorcontact/')
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn('/admin/login/', resp.url)


class NoStaleDoctorContactLinksTest(TestCase):
    """No active template/JS/sidebar may reference the old doctorcontact URLs."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='ds_admin3', password='pass')
        self.client.force_login(self.superuser)

    def test_sidebar_has_no_doctorcontact_link(self):
        resp = self.client.get('/admin/contacts/doctor/')
        self.assertNotIn(b'doctorcontact', resp.content.lower())

    def test_sidebar_has_no_specialty_entry(self):
        resp = self.client.get('/admin/contacts/doctor/')
        self.assertNotIn('تخصص‌ها', resp.content.decode())

    def test_surgery_history_admin_has_no_doctorcontact_link(self):
        resp = self.client.get('/admin/surgeries/surgeryhistory/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'doctorcontact', resp.content.lower())

    def test_no_active_static_js_generates_doctorcontact_url(self):
        for path in (
            'admin/js/contacts_directory.js',
            'admin/js/surgery_history_list.js',
            'admin/js/doctor_specialty.js',
        ):
            content = _static_source(*path.split('/'))
            self.assertNotIn('doctorcontact', content.lower(), f'{path} references doctorcontact')

    def test_no_active_template_generates_doctorcontact_url(self):
        base_html = Path(settings.BASE_DIR, 'templates', 'admin', 'base.html').read_text(encoding='utf-8')
        self.assertNotIn('doctorcontact', base_html.lower())
        doctor_change_list = Path(
            settings.BASE_DIR, 'templates', 'admin', 'contacts', 'doctor', 'change_list.html'
        ).read_text(encoding='utf-8')
        self.assertNotIn('doctorcontact', doctor_change_list.lower())


class DoctorSpecialtyNotStandaloneTest(TestCase):
    """C. DoctorSpecialty must not be a standalone admin-managed model."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='ds_admin4', password='pass')
        self.client.force_login(self.superuser)

    def test_doctorspecialty_changelist_url_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse('admin:contacts_doctorspecialty_changelist')

    def test_doctorspecialty_not_in_app_index(self):
        resp = self.client.get('/admin/contacts/')
        self.assertNotIn(b'doctorspecialty', resp.content.lower())

    def test_doctorspecialty_model_and_rows_survive(self):
        # The model and its data must remain intact — only the standalone
        # admin registration was removed.
        make_specialty('باقی‌مانده')
        self.assertTrue(DoctorSpecialty.objects.filter(name='باقی‌مانده').exists())


class DoctorFormSpecialtyWidgetTest(TestCase):
    """D. The Doctor add/edit form must expose the Specialty selector + buttons."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='ds_admin5', password='pass')
        self.client.force_login(self.superuser)

    def test_add_form_contains_specialty_selector(self):
        resp = self.client.get('/admin/contacts/doctor/add/')
        self.assertContains(resp, 'id="id_specialty"')

    def test_change_form_contains_specialty_selector(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'id="id_specialty"')

    def test_change_form_loads_doctor_specialty_js(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'admin/js/doctor_specialty.js')

    def test_change_form_exposes_add_permission_flag(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'canAdd: true')
        self.assertContains(resp, 'canDelete: true')

    def test_form_flags_false_without_permission(self):
        staff = User.objects.create_user(username='ds_staff_noperm', password='pass', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_doctor'))
        staff.user_permissions.add(Permission.objects.get(codename='change_doctor'))
        self.client.force_login(staff)
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'canAdd: false')
        self.assertContains(resp, 'canDelete: false')

    def test_js_defines_add_button_with_title(self):
        content = _static_source('admin', 'js', 'doctor_specialty.js')
        self.assertIn('ds-add-btn', content)
        self.assertIn('افزودن تخصص جدید', content)

    def test_js_defines_delete_button_with_title(self):
        content = _static_source('admin', 'js', 'doctor_specialty.js')
        self.assertIn('ds-delete-btn', content)
        self.assertIn('حذف تخصص انتخاب‌شده', content)

    def test_js_never_reloads_the_page(self):
        content = _static_source('admin', 'js', 'doctor_specialty.js')
        self.assertNotIn('location.reload', content)
        self.assertNotIn('.submit()', content)

    def test_js_defines_activate_button(self):
        content = _static_source('admin', 'js', 'doctor_specialty.js')
        self.assertIn('ds-activate-btn', content)
        self.assertIn('فعال‌سازی تخصص انتخاب‌شده', content)

    def test_js_uses_a_single_shared_json_request_helper(self):
        content = _static_source('admin', 'js', 'doctor_specialty.js')
        # One shared helper (postJSON) used by every mutation, application/json
        # consistently, so create/delete/deactivate/activate can't drift apart.
        self.assertEqual(content.count('function postJSON'), 1)
        self.assertIn("'Content-Type': 'application/json'", content)
        self.assertIn('X-CSRFToken', content)

    def test_change_form_exposes_all_permission_flags(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'canAdd: true')
        self.assertContains(resp, 'canDelete: true')
        self.assertContains(resp, 'canChange: true')

    def test_change_form_static_assets_are_cache_busted(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertRegex(content, r'doctor_specialty\.js\?v=\d+')
        self.assertRegex(content, r'doctor_specialty\.css\?v=\d+')


class DoctorSpecialtyCreateEndpointTest(TestCase):
    """G/H. POST /admin/contacts/doctor-specialties/create/ (application/json)"""

    def setUp(self):
        self.url = reverse('admin:contacts_doctor_specialty_create')
        self.staff_with_perm = User.objects.create_user(username='ds_creator', password='pass', is_staff=True)
        self.staff_with_perm.user_permissions.add(Permission.objects.get(codename='add_doctorspecialty'))
        self.staff_no_perm = User.objects.create_user(username='ds_no_add', password='pass', is_staff=True)

    def _post(self, client, data):
        return client.post(self.url, data, content_type='application/json')

    def test_requires_authentication(self):
        resp = self._post(self.client, {'name': 'تخصص جدید'})
        self.assertIn(resp.status_code, (302, 403))

    def test_requires_permission(self):
        self.client.force_login(self.staff_no_perm)
        resp = self._post(self.client, {'name': 'تخصص جدید'})
        self.assertEqual(resp.status_code, 403)

    def test_requires_permission_returns_json_body_the_modal_js_can_parse(self):
        # A default Django PermissionDenied response is HTML — fetch()'s
        # res.json() throws on that, surfacing as a generic connection
        # error in the modal instead of this real message.
        self.client.force_login(self.staff_no_perm)
        resp = self._post(self.client, {'name': 'تخصص جدید بدون دسترسی'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp['Content-Type'], 'application/json')
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'permission_denied')
        self.assertEqual(data['message'], 'شما اجازه انجام این عملیات را ندارید.')

    def test_csrf_failure_on_ajax_request_returns_json_session_expired_message(self):
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.staff_with_perm)
        resp = self._post(strict_client, {'name': 'تخصص سی‌اس‌آراف بدون توکن'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp['Content-Type'], 'application/json')
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'csrf_failed')
        self.assertEqual(data['message'], 'نشست شما منقضی شده است. صفحه را تازه‌سازی کنید.')

    def test_get_not_allowed(self):
        self.client.force_login(self.staff_with_perm)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_valid_creation_succeeds_and_returns_id_and_name(self):
        self.client.force_login(self.staff_with_perm)
        resp = self._post(self.client, {'name': 'قلب و عروق'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('id', data)
        self.assertEqual(data['name'], 'قلب و عروق')
        self.assertTrue(DoctorSpecialty.objects.filter(pk=data['id'], name='قلب و عروق').exists())

    def test_duplicate_rejected(self):
        make_specialty('ارتوپدی')
        self.client.force_login(self.staff_with_perm)
        resp = self._post(self.client, {'name': 'ارتوپدی'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'duplicate_name')
        self.assertIn('قبلاً ثبت شده', data['message'])

    def test_whitespace_only_rejected(self):
        self.client.force_login(self.staff_with_perm)
        resp = self._post(self.client, {'name': '   '})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'empty_name')

    def test_whitespace_trimmed_and_collapsed(self):
        self.client.force_login(self.staff_with_perm)
        resp = self._post(self.client, {'name': '  گوش   و حلق  '})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['name'], 'گوش و حلق')

    def test_empty_body_rejected_not_500(self):
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self.url, data=b'', content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'empty_name')

    def test_csrf_protection_rejects_missing_token(self):
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.staff_with_perm)
        resp = self._post(strict_client, {'name': 'تخصص سی‌اس‌آراف'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(DoctorSpecialty.objects.filter(name='تخصص سی‌اس‌آراف').exists())

    def test_csrf_protected_request_with_valid_token_succeeds(self):
        # Needs to actually reach the rendered Doctor change form (not a
        # permission-denied page) so {% csrf_token %} runs and Django sets
        # the csrftoken cookie — same as a real browser page load would.
        self.staff_with_perm.user_permissions.add(
            Permission.objects.get(codename='view_doctor'),
            Permission.objects.get(codename='change_doctor'),
        )
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.staff_with_perm)
        doc = make_doctor()
        resp = strict_client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        csrf_token = strict_client.cookies['csrftoken'].value
        resp = strict_client.post(
            self.url,
            data='{"name": "تخصص با سی‌اس‌آراف معتبر"}',
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])


class DoctorSpecialtyDeleteEndpointTest(TestCase):
    """G/H/F. POST /admin/contacts/doctor-specialties/<id>/delete/"""

    def setUp(self):
        self.staff_with_perm = User.objects.create_user(username='ds_deleter', password='pass', is_staff=True)
        self.staff_with_perm.user_permissions.add(Permission.objects.get(codename='delete_doctorspecialty'))
        self.staff_no_perm = User.objects.create_user(username='ds_no_delete', password='pass', is_staff=True)

    def _url(self, pk):
        return reverse('admin:contacts_doctor_specialty_delete', args=[pk])

    def test_requires_authentication(self):
        specialty = make_specialty('بی‌نیاز از احراز')
        resp = self.client.post(self._url(specialty.pk))
        self.assertIn(resp.status_code, (302, 403))

    def test_requires_permission(self):
        specialty = make_specialty('بدون دسترسی حذف')
        self.client.force_login(self.staff_no_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 403)

    def test_get_not_allowed(self):
        specialty = make_specialty('فقط پست')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.get(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 405)

    def test_unused_specialty_can_be_deleted(self):
        specialty = make_specialty('استفاده‌نشده')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        self.assertFalse(DoctorSpecialty.objects.filter(pk=specialty.pk).exists())

    def test_used_specialty_cannot_be_deleted(self):
        specialty = make_specialty('در حال استفاده')
        doc = make_doctor(specialty=specialty, phone_number='09123334444')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'specialty_in_use')
        self.assertEqual(data['doctor_count'], 1)
        self.assertIn('قابل حذف نیست', data['message'])
        self.assertTrue(DoctorSpecialty.objects.filter(pk=specialty.pk, is_active=True).exists())
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, specialty.pk)

    def test_no_doctor_deleted_when_specialty_deletion_blocked(self):
        specialty = make_specialty('حفاظت‌شده')
        make_doctor(specialty=specialty, phone_number='09125556666')
        before = Doctor.objects.count()
        self.client.force_login(self.staff_with_perm)
        self.client.post(self._url(specialty.pk))
        self.assertEqual(Doctor.objects.count(), before)

    def test_surgery_history_clinical_doctor_unchanged_when_deletion_blocked(self):
        specialty = make_specialty('جراحی حفاظت‌شده')
        doc = make_doctor(specialty=specialty, phone_number='09127778888')
        stype = SurgeryType.objects.create(code='gen2', name='عمومی۲', base_rate=Decimal('1000000'))
        from surgeries.models import Patient
        patient = Patient.objects.create(
            full_name='بیمار تست', case_code='PAT-DS-1', phone_number='09120000001', national_id='1111111111',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype, clinical_doctor=doc,
            amount=Decimal('10000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        self.client.force_login(self.staff_with_perm)
        self.client.post(self._url(specialty.pk))
        surgery.refresh_from_db()
        self.assertEqual(surgery.clinical_doctor_id, doc.pk)


class DoctorSpecialtyDeactivateEndpointTest(TestCase):
    """POST /admin/contacts/doctor-specialties/<id>/deactivate/"""

    def setUp(self):
        self.staff_with_perm = User.objects.create_user(username='ds_deactivator', password='pass', is_staff=True)
        self.staff_with_perm.user_permissions.add(Permission.objects.get(codename='delete_doctorspecialty'))
        self.staff_no_perm = User.objects.create_user(username='ds_no_deactivate', password='pass', is_staff=True)

    def _url(self, pk):
        return reverse('admin:contacts_doctor_specialty_deactivate', args=[pk])

    def test_requires_authentication(self):
        specialty = make_specialty('غیرفعال بدون احراز')
        resp = self.client.post(self._url(specialty.pk))
        self.assertIn(resp.status_code, (302, 403))

    def test_requires_permission(self):
        specialty = make_specialty('غیرفعال بدون دسترسی')
        self.client.force_login(self.staff_no_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 403)

    def test_get_not_allowed(self):
        specialty = make_specialty('غیرفعال فقط پست')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.get(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 405)

    def test_deactivate_in_use_specialty_succeeds(self):
        specialty = make_specialty('تخصص در حال استفاده برای غیرفعال‌سازی')
        doc = make_doctor(specialty=specialty, phone_number='09129990000')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['doctor_count'], 1)
        specialty.refresh_from_db()
        self.assertFalse(specialty.is_active)
        # Still exists — not deleted.
        self.assertTrue(DoctorSpecialty.objects.filter(pk=specialty.pk).exists())
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, specialty.pk)

    def test_deactivate_does_not_change_doctor_pk_or_surgery_relations(self):
        specialty = make_specialty('تخصص جراحی برای غیرفعال‌سازی')
        doc = make_doctor(specialty=specialty, phone_number='09129991111')
        stype = SurgeryType.objects.create(code='gen3', name='عمومی۳', base_rate=Decimal('1000000'))
        from surgeries.models import Patient
        patient = Patient.objects.create(
            full_name='بیمار غیرفعال‌سازی', case_code='PAT-DS-2', phone_number='09120000002', national_id='2222222222',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype, clinical_doctor=doc,
            amount=Decimal('5000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        doctor_pk_before = doc.pk
        self.client.force_login(self.staff_with_perm)
        self.client.post(self._url(specialty.pk))
        doc.refresh_from_db()
        surgery.refresh_from_db()
        self.assertEqual(doc.pk, doctor_pk_before)
        self.assertEqual(doc.specialty_id, specialty.pk)
        self.assertEqual(surgery.clinical_doctor_id, doc.pk)

    def test_deactivate_unused_specialty_also_succeeds(self):
        specialty = make_specialty('تخصص بدون استفاده برای غیرفعال‌سازی')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['doctor_count'], 0)
        specialty.refresh_from_db()
        self.assertFalse(specialty.is_active)


class DoctorSpecialtyActivateEndpointTest(TestCase):
    """POST /admin/contacts/doctor-specialties/<id>/activate/"""

    def setUp(self):
        self.staff_with_perm = User.objects.create_user(username='ds_activator', password='pass', is_staff=True)
        self.staff_with_perm.user_permissions.add(Permission.objects.get(codename='change_doctorspecialty'))
        self.staff_no_perm = User.objects.create_user(username='ds_no_activate', password='pass', is_staff=True)

    def _url(self, pk):
        return reverse('admin:contacts_doctor_specialty_activate', args=[pk])

    def _make_inactive(self, name):
        specialty = make_specialty(name)
        specialty.is_active = False
        specialty.save(update_fields=['is_active'])
        return specialty

    def test_requires_authentication(self):
        specialty = self._make_inactive('فعال‌سازی بدون احراز')
        resp = self.client.post(self._url(specialty.pk))
        self.assertIn(resp.status_code, (302, 403))

    def test_requires_permission(self):
        specialty = self._make_inactive('فعال‌سازی بدون دسترسی')
        self.client.force_login(self.staff_no_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 403)

    def test_get_not_allowed(self):
        specialty = self._make_inactive('فعال‌سازی فقط پست')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.get(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 405)

    def test_activate_succeeds(self):
        specialty = self._make_inactive('برای فعال‌سازی')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self._url(specialty.pk))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        specialty.refresh_from_db()
        self.assertTrue(specialty.is_active)

    def test_activate_does_not_touch_doctors(self):
        specialty = make_specialty('فعال‌سازی بدون تغییر دکتر')
        doc = make_doctor(specialty=specialty, phone_number='09129992222')
        specialty.is_active = False
        specialty.save(update_fields=['is_active'])
        self.client.force_login(self.staff_with_perm)
        self.client.post(self._url(specialty.pk))
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, specialty.pk)


class DoctorSpecialtyRouteResolutionTest(TestCase):
    """B/G. All four Specialty utility routes must resolve via reverse()."""

    def test_create_route_resolves(self):
        self.assertEqual(reverse('admin:contacts_doctor_specialty_create'), '/admin/contacts/doctor-specialties/create/')

    def test_delete_route_resolves(self):
        self.assertEqual(
            reverse('admin:contacts_doctor_specialty_delete', args=[5]),
            '/admin/contacts/doctor-specialties/5/delete/',
        )

    def test_deactivate_route_resolves(self):
        self.assertEqual(
            reverse('admin:contacts_doctor_specialty_deactivate', args=[5]),
            '/admin/contacts/doctor-specialties/5/deactivate/',
        )

    def test_activate_route_resolves(self):
        self.assertEqual(
            reverse('admin:contacts_doctor_specialty_activate', args=[5]),
            '/admin/contacts/doctor-specialties/5/activate/',
        )

    def test_doctor_change_form_exposes_all_four_reversed_urls(self):
        superuser = User.objects.create_superuser(username='ds_route_admin', password='pass')
        self.client.force_login(superuser)
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('/admin/contacts/doctor-specialties/create/', content)
        self.assertIn('/admin/contacts/doctor-specialties/0/delete/', content)
        self.assertIn('/admin/contacts/doctor-specialties/0/deactivate/', content)
        self.assertIn('/admin/contacts/doctor-specialties/0/activate/', content)


class InactiveSpecialtyAdminFormTest(TestCase):
    """Inactive specialties must be hidden from new assignments but remain
    visible + selected + labeled for the Doctor that already has them."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='ds_inactive_admin', password='pass')
        self.client.force_login(self.superuser)

    @staticmethod
    def _specialty_select_html(content):
        # Phase 6 added a second <select> (the DoctorSurgeryRate inline's
        # surgery_type field) to the same page, whose <option value="N">
        # pks can coincidentally collide with a DoctorSpecialty pk — scope
        # the assertion to just the #id_specialty select to avoid a false
        # positive/negative from that unrelated dropdown.
        start = content.index('id="id_specialty"')
        end = content.index('</select>', start)
        return content[start:end]

    def test_inactive_specialty_not_offered_on_add_form(self):
        active = make_specialty('تخصص فعال برای افزودن')
        inactive = make_specialty('تخصص غیرفعال برای افزودن')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        resp = self.client.get('/admin/contacts/doctor/add/')
        specialty_html = self._specialty_select_html(resp.content.decode())
        self.assertIn(f'value="{active.pk}"', specialty_html)
        self.assertNotIn(f'value="{inactive.pk}"', specialty_html)

    def test_inactive_specialty_not_offered_to_doctor_with_other_specialty(self):
        other = make_specialty('تخصص دیگر')
        inactive = make_specialty('تخصص غیرفعال برای دکتر دیگر')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        doc = make_doctor(specialty=other, phone_number='09122223333')
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        specialty_html = self._specialty_select_html(resp.content.decode())
        self.assertNotIn(f'value="{inactive.pk}"', specialty_html)

    def test_doctor_with_inactive_specialty_still_shows_it_selected_and_labeled(self):
        inactive = make_specialty('تخصص غیرفعال فعلی دکتر')
        doc = make_doctor(specialty=inactive, phone_number='09122224444')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn(f'selected>{inactive.name} (غیرفعال)</option>', content)

    def test_saving_unrelated_field_keeps_inactive_specialty(self):
        inactive = make_specialty('تخصص غیرفعال حفظ‌شده')
        doc = make_doctor(specialty=inactive, phone_number='09122225555')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])

        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertEqual(resp.status_code, 200)

        post_data = {
            'full_name': 'دکتر به‌روزرسانی‌شده',
            'specialty': inactive.pk,
            'phone_number': doc.phone_number,
            'email': '',
            'address': '',
            'cooperation_status': 'active',
            'notes': '',
            # Phase 6 added a DoctorSurgeryRate inline to the Doctor form;
            # Django admin requires its management form data on every POST
            # even when submitting zero rate rows.
            'surgery_rates-TOTAL_FORMS': '0',
            'surgery_rates-INITIAL_FORMS': '0',
            'surgery_rates-MIN_NUM_FORMS': '0',
            'surgery_rates-MAX_NUM_FORMS': '1000',
        }
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', post_data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.full_name, 'دکتر به‌روزرسانی‌شده')
        self.assertEqual(doc.specialty_id, inactive.pk)

    def test_cannot_switch_doctor_to_a_different_inactive_specialty(self):
        current = make_specialty('تخصص فعلی برای تعویض')
        inactive = make_specialty('تخصص غیرفعال هدف تعویض')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        doc = make_doctor(specialty=current, phone_number='09122226666')

        post_data = {
            'full_name': doc.full_name,
            'specialty': inactive.pk,
            'phone_number': doc.phone_number,
            'email': '',
            'address': '',
            'cooperation_status': 'active',
            'notes': '',
            # Phase 6 added a DoctorSurgeryRate inline to the Doctor form;
            # Django admin requires its management form data on every POST
            # even when submitting zero rate rows.
            'surgery_rates-TOTAL_FORMS': '0',
            'surgery_rates-INITIAL_FORMS': '0',
            'surgery_rates-MIN_NUM_FORMS': '0',
            'surgery_rates-MAX_NUM_FORMS': '1000',
        }
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'برای انتساب جدید قابل انتخاب نیست')
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, current.pk)

    def test_cannot_create_new_doctor_with_inactive_specialty(self):
        inactive = make_specialty('تخصص غیرفعال برای دکتر جدید')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])

        post_data = {
            'full_name': 'دکتر جدید نامعتبر',
            'specialty': inactive.pk,
            'phone_number': '09122227777',
            'email': '',
            'address': '',
            'cooperation_status': 'active',
            'notes': '',
            # Phase 6 added a DoctorSurgeryRate inline to the Doctor form;
            # Django admin requires its management form data on every POST
            # even when submitting zero rate rows.
            'surgery_rates-TOTAL_FORMS': '0',
            'surgery_rates-INITIAL_FORMS': '0',
            'surgery_rates-MIN_NUM_FORMS': '0',
            'surgery_rates-MAX_NUM_FORMS': '1000',
        }
        resp = self.client.post('/admin/contacts/doctor/add/', post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'برای انتساب جدید قابل انتخاب نیست')
        self.assertFalse(Doctor.objects.filter(full_name='دکتر جدید نامعتبر').exists())


class InactiveSpecialtyApiValidationTest(APITestCase):
    """Server-side (DRF) rejection of inactive-specialty assignment."""

    def setUp(self):
        self.user = User.objects.create_user(username='ds_api_user', password='pass')
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v2/contacts/doctors/'

    def test_cannot_create_doctor_via_api_with_inactive_specialty(self):
        inactive = make_specialty('API تخصص غیرفعال جدید')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        resp = self.client.post(self.url, {
            'full_name': 'دکتر ای‌پی‌آی',
            'specialty': inactive.pk,
            'phone_number': '09122228888',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('specialty', resp.data)

    def test_cannot_update_doctor_via_api_to_a_different_inactive_specialty(self):
        current = make_specialty('API تخصص فعلی')
        inactive = make_specialty('API تخصص غیرفعال هدف')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        doc = make_doctor(specialty=current, phone_number='09122229999')
        resp = self.client.patch(
            f'{self.url}{doc.pk}/', {'specialty': inactive.pk}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, current.pk)

    def test_can_update_doctor_via_api_keeping_its_own_inactive_specialty(self):
        inactive = make_specialty('API تخصص غیرفعال فعلی حفظ‌شده')
        doc = make_doctor(specialty=inactive, phone_number='09122220000')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        resp = self.client.patch(
            f'{self.url}{doc.pk}/',
            {'full_name': 'دکتر حفظ‌شده به‌روزرسانی‌شده'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, inactive.pk)
        self.assertEqual(doc.full_name, 'دکتر حفظ‌شده به‌روزرسانی‌شده')
