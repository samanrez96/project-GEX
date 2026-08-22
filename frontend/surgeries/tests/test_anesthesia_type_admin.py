"""Targeted tests for the AnesthesiaType in-form modal AJAX endpoints
(mirrors contacts/tests/test_doctor_specialty_admin.py's endpoint tests) and
for the JSON-error-contract fix: permission-denied and CSRF-failure
responses must be JSON, never Django's default HTML page, since the modal
JS always calls res.json() on the response.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from surgeries.models import AnesthesiaType, Patient, SurgeryHistory, SurgeryType

User = get_user_model()


def make_anesthesia_type(name='بیهوشی عمومی'):
    obj, _ = AnesthesiaType.objects.get_or_create(name=name)
    return obj


def make_surgery_history(**kwargs):
    defaults = {
        'patient': Patient.objects.create(
            full_name='بیمار تست', case_code='PAT-AT-1', phone_number='09120000000', national_id='1111111111',
        ),
        'surgery_type': SurgeryType.objects.create(code='at_gen', name='عمومی', base_rate=Decimal('1000000')),
        'amount': Decimal('10000000'),
        'surgery_date': datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    }
    defaults.update(kwargs)
    return SurgeryHistory.objects.create(**defaults)


class AnesthesiaTypeCreateEndpointTest(TestCase):
    def setUp(self):
        self.url = reverse('admin:surgeries_anesthesia_type_create')
        self.staff_with_perm = User.objects.create_user(username='at_creator', password='pass', is_staff=True)
        self.staff_with_perm.user_permissions.add(Permission.objects.get(codename='add_anesthesiatype'))
        self.staff_no_perm = User.objects.create_user(username='at_no_add', password='pass', is_staff=True)

    def _post(self, client, data):
        return client.post(self.url, data, content_type='application/json')

    def test_requires_authentication(self):
        resp = self._post(self.client, {'name': 'بیهوشی جدید'})
        self.assertIn(resp.status_code, (302, 403))

    def test_requires_permission_returns_json_403(self):
        self.client.force_login(self.staff_no_perm)
        resp = self._post(self.client, {'name': 'بیهوشی جدید'})
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'permission_denied')
        self.assertEqual(data['message'], 'شما اجازه انجام این عملیات را ندارید.')

    def test_get_not_allowed(self):
        self.client.force_login(self.staff_with_perm)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_valid_creation_succeeds_and_returns_id_and_name(self):
        self.client.force_login(self.staff_with_perm)
        resp = self._post(self.client, {'name': 'بیهوشی موضعی'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('id', data)
        self.assertEqual(data['name'], 'بیهوشی موضعی')
        self.assertEqual(data['message'], 'نوع بیهوشی با موفقیت اضافه شد.')
        self.assertTrue(AnesthesiaType.objects.filter(pk=data['id'], name='بیهوشی موضعی').exists())

    def test_duplicate_rejected(self):
        make_anesthesia_type('اسپاینال')
        self.client.force_login(self.staff_with_perm)
        resp = self._post(self.client, {'name': 'اسپاینال'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'duplicate_name')

    def test_empty_name_rejected(self):
        self.client.force_login(self.staff_with_perm)
        resp = self._post(self.client, {'name': '   '})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'empty_name')

    def test_csrf_protection_rejects_missing_token(self):
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.staff_with_perm)
        resp = self._post(strict_client, {'name': 'بیهوشی سی‌اس‌آراف'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(AnesthesiaType.objects.filter(name='بیهوشی سی‌اس‌آراف').exists())

    def test_csrf_failure_on_ajax_request_returns_json_session_expired_message(self):
        # Same scenario as above, but asserts the fixed JSON contract: an
        # AJAX (application/json) request that fails CSRF must get a JSON
        # body the modal JS can parse, not Django's default HTML page.
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.staff_with_perm)
        resp = self._post(strict_client, {'name': 'بیهوشی سی‌اس‌آراف ۲'})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp['Content-Type'], 'application/json')
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'csrf_failed')
        self.assertEqual(data['message'], 'نشست شما منقضی شده است. صفحه را تازه‌سازی کنید.')

    def test_csrf_protected_request_with_valid_token_succeeds(self):
        self.staff_with_perm.user_permissions.add(
            Permission.objects.get(codename='view_surgeryhistory'),
            Permission.objects.get(codename='change_surgeryhistory'),
        )
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.force_login(self.staff_with_perm)
        surgery = make_surgery_history()
        resp = strict_client.get(f'/admin/surgeries/surgeryhistory/{surgery.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        csrf_token = strict_client.cookies['csrftoken'].value
        resp = strict_client.post(
            self.url,
            data='{"name": "بیهوشی با سی‌اس‌آراف معتبر"}',
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])


class AnesthesiaTypeDeleteEndpointTest(TestCase):
    def setUp(self):
        self.staff_with_perm = User.objects.create_user(username='at_deleter', password='pass', is_staff=True)
        self.staff_with_perm.user_permissions.add(Permission.objects.get(codename='delete_anesthesiatype'))
        self.staff_no_perm = User.objects.create_user(username='at_no_delete', password='pass', is_staff=True)

    def _url(self, pk):
        return reverse('admin:surgeries_anesthesia_type_delete', args=[pk])

    def test_requires_permission_returns_json_403(self):
        anesthesia_type = make_anesthesia_type('بدون دسترسی حذف')
        self.client.force_login(self.staff_no_perm)
        resp = self.client.post(self._url(anesthesia_type.pk))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['code'], 'permission_denied')

    def test_unused_type_can_be_deleted(self):
        anesthesia_type = make_anesthesia_type('استفاده‌نشده')
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self._url(anesthesia_type.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        self.assertFalse(AnesthesiaType.objects.filter(pk=anesthesia_type.pk).exists())

    def test_used_type_cannot_be_deleted(self):
        anesthesia_type = make_anesthesia_type('در حال استفاده')
        make_surgery_history(anesthesia_type=anesthesia_type)
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(self._url(anesthesia_type.pk))
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data['code'], 'anesthesia_type_in_use')
        self.assertTrue(AnesthesiaType.objects.filter(pk=anesthesia_type.pk, is_active=True).exists())


class AnesthesiaTypeDeactivateActivateEndpointTest(TestCase):
    def setUp(self):
        self.staff_with_perm = User.objects.create_user(username='at_toggler', password='pass', is_staff=True)
        self.staff_with_perm.user_permissions.add(
            Permission.objects.get(codename='delete_anesthesiatype'),
            Permission.objects.get(codename='change_anesthesiatype'),
        )

    def test_deactivate_in_use_type_succeeds(self):
        anesthesia_type = make_anesthesia_type('برای غیرفعال‌سازی')
        make_surgery_history(anesthesia_type=anesthesia_type)
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(reverse('admin:surgeries_anesthesia_type_deactivate', args=[anesthesia_type.pk]))
        self.assertEqual(resp.status_code, 200)
        anesthesia_type.refresh_from_db()
        self.assertFalse(anesthesia_type.is_active)

    def test_activate_succeeds(self):
        anesthesia_type = make_anesthesia_type('برای فعال‌سازی')
        anesthesia_type.is_active = False
        anesthesia_type.save(update_fields=['is_active'])
        self.client.force_login(self.staff_with_perm)
        resp = self.client.post(reverse('admin:surgeries_anesthesia_type_activate', args=[anesthesia_type.pk]))
        self.assertEqual(resp.status_code, 200)
        anesthesia_type.refresh_from_db()
        self.assertTrue(anesthesia_type.is_active)


class AnesthesiaTypeFormWidgetTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='at_widget_admin', password='pass')
        self.client.force_login(self.superuser)

    def test_change_form_loads_anesthesia_type_js(self):
        surgery = make_surgery_history()
        resp = self.client.get(f'/admin/surgeries/surgeryhistory/{surgery.pk}/change/')
        self.assertContains(resp, 'admin/js/anesthesia_type.js')

    def test_change_form_exposes_all_four_reversed_urls(self):
        surgery = make_surgery_history()
        resp = self.client.get(f'/admin/surgeries/surgeryhistory/{surgery.pk}/change/')
        content = resp.content.decode()
        self.assertIn('/admin/surgeries/surgeryhistory/anesthesia-type/create/', content)
        self.assertIn('/admin/surgeries/surgeryhistory/anesthesia-type/0/delete/', content)
        self.assertIn('/admin/surgeries/surgeryhistory/anesthesia-type/0/deactivate/', content)
        self.assertIn('/admin/surgeries/surgeryhistory/anesthesia-type/0/activate/', content)
