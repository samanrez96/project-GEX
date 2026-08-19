"""Phase 5 tests: Doctor document image uploads (medical certificate /
national card).

Uses an isolated temporary MEDIA_ROOT for every test that actually writes a
file to storage, so nothing lands in the real development media directory.
"""
import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APITestCase

from common.uploads import MAX_IMAGE_UPLOAD_SIZE, validate_image_upload
from contacts.models import Doctor, DoctorSpecialty

User = get_user_model()
DOCTORS_URL = '/api/v2/contacts/doctors/'

_TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='doctor_docs_test_')


def tearDownModule():
    shutil.rmtree(_TEST_MEDIA_ROOT, ignore_errors=True)


def make_specialty(name='جراحی عمومی'):
    obj, _ = DoctorSpecialty.objects.get_or_create(name=name)
    return obj


def make_doctor(**kwargs):
    if isinstance(kwargs.get('specialty'), str):
        kwargs['specialty'] = make_specialty(kwargs['specialty'])
    defaults = {
        'full_name': 'دکتر مدارک',
        'specialty': make_specialty(),
        'phone_number': '09121234567',
    }
    defaults.update(kwargs)
    return Doctor.objects.create(**defaults)


def make_image_file(name='test.jpg', img_format='JPEG', size=(12, 12), color=(200, 40, 40)):
    buf = BytesIO()
    Image.new('RGB', size, color).save(buf, format=img_format)
    buf.seek(0)
    content_type = {
        'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp',
    }[img_format]
    return SimpleUploadedFile(name, buf.read(), content_type=content_type)


def make_fake_jpg(name='fake.jpg'):
    """Non-image binary content renamed with a .jpg extension."""
    return SimpleUploadedFile(name, b'not really an image' * 20, content_type='image/jpeg')


def make_corrupted_png(name='corrupt.png'):
    buf = BytesIO()
    Image.new('RGB', (20, 20)).save(buf, format='PNG')
    truncated = buf.getvalue()[: len(buf.getvalue()) // 2]
    return SimpleUploadedFile(name, truncated, content_type='image/png')


def make_svg_file(name='test.svg'):
    content = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
    return SimpleUploadedFile(name, content, content_type='image/svg+xml')


def make_pdf_file(name='test.pdf'):
    content = b'%PDF-1.4\n%\xc7\xec\x8f\xa2\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF'
    return SimpleUploadedFile(name, content, content_type='application/pdf')


def make_empty_file(name='empty.jpg'):
    return SimpleUploadedFile(name, b'', content_type='image/jpeg')


# ---------------------------------------------------------------------------
# Validator unit tests — no DB/storage needed for most of these.
# ---------------------------------------------------------------------------

class ImageUploadValidatorTest(TestCase):

    def test_valid_jpeg_accepted(self):
        validate_image_upload(make_image_file(img_format='JPEG'))

    def test_valid_png_accepted(self):
        validate_image_upload(make_image_file(name='t.png', img_format='PNG'))

    def test_valid_webp_accepted(self):
        validate_image_upload(make_image_file(name='t.webp', img_format='WEBP'))

    def test_file_pointer_reset_after_success(self):
        f = make_image_file()
        validate_image_upload(f)
        self.assertEqual(f.tell(), 0)

    def test_file_pointer_reset_after_failure(self):
        f = make_fake_jpg()
        with self.assertRaises(ValidationError):
            validate_image_upload(f)
        self.assertEqual(f.tell(), 0)

    def test_oversized_rejected(self):
        f = make_image_file()
        f.size = MAX_IMAGE_UPLOAD_SIZE + 1
        with self.assertRaises(ValidationError) as cm:
            validate_image_upload(f)
        self.assertEqual(cm.exception.code, 'file_too_large')
        self.assertIn('۵ مگابایت', str(cm.exception.message))

    def test_file_exactly_at_limit_is_accepted(self):
        f = make_image_file()
        f.size = MAX_IMAGE_UPLOAD_SIZE
        validate_image_upload(f)  # must not raise

    def test_fake_jpg_renamed_binary_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            validate_image_upload(make_fake_jpg())
        self.assertEqual(cm.exception.code, 'invalid_image')

    def test_corrupted_png_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            validate_image_upload(make_corrupted_png())
        self.assertEqual(cm.exception.code, 'invalid_image')

    def test_svg_rejected(self):
        with self.assertRaises(ValidationError):
            validate_image_upload(make_svg_file())

    def test_pdf_rejected(self):
        with self.assertRaises(ValidationError):
            validate_image_upload(make_pdf_file())

    def test_empty_upload_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            validate_image_upload(make_empty_file())
        self.assertEqual(cm.exception.code, 'invalid_image')

    def test_unsupported_but_decodable_format_rejected(self):
        # BMP: a format Pillow can decode but that's outside our whitelist.
        buf = BytesIO()
        Image.new('RGB', (10, 10)).save(buf, format='BMP')
        buf.seek(0)
        f = SimpleUploadedFile('test.bmp', buf.read(), content_type='image/bmp')
        with self.assertRaises(ValidationError) as cm:
            validate_image_upload(f)
        self.assertEqual(cm.exception.code, 'unsupported_format')
        self.assertIn('JPG', str(cm.exception.message))

    def test_none_is_a_noop(self):
        validate_image_upload(None)  # must not raise


# ---------------------------------------------------------------------------
# Model / migration data-preservation
# ---------------------------------------------------------------------------

class DoctorDocumentModelTest(TestCase):

    def test_existing_doctor_valid_without_documents(self):
        doc = make_doctor()
        doc.full_clean(exclude=['id'])
        self.assertFalse(doc.medical_certificate_image)
        self.assertFalse(doc.national_card_image)

    def test_both_fields_optional(self):
        doc = Doctor(full_name='دکتر بدون مدرک', specialty=make_specialty(), phone_number='0912')
        doc.full_clean(exclude=['id'])  # must not raise for the document fields

    def test_doctor_pk_unchanged_after_adding_documents(self):
        doc = make_doctor()
        pk_before = doc.pk
        doc.notes = 'یادداشت'
        doc.save()
        self.assertEqual(doc.pk, pk_before)

    def test_specialty_relation_unchanged(self):
        specialty = make_specialty('تخصص حفظ‌شده مدارک')
        doc = make_doctor(specialty=specialty)
        doc.notes = 'x'
        doc.save()
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, specialty.pk)

    def test_surgery_history_relation_unchanged(self):
        import datetime
        from surgeries.models import Patient, SurgeryHistory, SurgeryType
        doc = make_doctor(phone_number='09127778899')
        stype = SurgeryType.objects.create(code='doc-test', name='تست مدارک', base_rate=Decimal('1000000'))
        patient = Patient.objects.create(
            full_name='بیمار تست مدارک', case_code='PAT-DOC-1', phone_number='09120000009', national_id='3333333333',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype, clinical_doctor=doc,
            amount=Decimal('1000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        doc.notes = 'changed'
        doc.save()
        surgery.refresh_from_db()
        self.assertEqual(surgery.clinical_doctor_id, doc.pk)


# ---------------------------------------------------------------------------
# Storage lifecycle: replace / clear / delete cleanup
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=_TEST_MEDIA_ROOT)
class DoctorDocumentStorageLifecycleTest(TestCase):

    def test_uploading_saves_file(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        self.assertTrue(doc.medical_certificate_image.name)
        self.assertTrue(default_storage.exists(doc.medical_certificate_image.name))

    def test_replacing_removes_old_file_after_save(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        old_name = doc.medical_certificate_image.name
        with self.captureOnCommitCallbacks(execute=True):
            doc.medical_certificate_image = make_image_file(name='new.jpg')
            doc.save()
        self.assertFalse(default_storage.exists(old_name))
        self.assertTrue(default_storage.exists(doc.medical_certificate_image.name))

    def test_replacing_one_field_does_not_touch_other(self):
        doc = make_doctor(
            medical_certificate_image=make_image_file(name='cert.jpg'),
            national_card_image=make_image_file(name='card.jpg'),
        )
        card_name = doc.national_card_image.name
        with self.captureOnCommitCallbacks(execute=True):
            doc.medical_certificate_image = make_image_file(name='new_cert.jpg')
            doc.save()
        self.assertTrue(default_storage.exists(card_name))
        doc.refresh_from_db()
        self.assertEqual(doc.national_card_image.name, card_name)

    def test_clearing_removes_file_after_save(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        old_name = doc.medical_certificate_image.name
        with self.captureOnCommitCallbacks(execute=True):
            doc.medical_certificate_image = None
            doc.save()
        self.assertFalse(default_storage.exists(old_name))
        doc.refresh_from_db()
        self.assertFalse(doc.medical_certificate_image)

    def test_clearing_one_preserves_other(self):
        doc = make_doctor(
            medical_certificate_image=make_image_file(name='cert2.jpg'),
            national_card_image=make_image_file(name='card2.jpg'),
        )
        card_name = doc.national_card_image.name
        with self.captureOnCommitCallbacks(execute=True):
            doc.medical_certificate_image = None
            doc.save()
        self.assertTrue(default_storage.exists(card_name))

    def test_unchanged_field_is_not_deleted(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        name = doc.medical_certificate_image.name
        with self.captureOnCommitCallbacks(execute=True):
            doc.notes = 'یادداشت جدید'
            doc.save()
        self.assertTrue(default_storage.exists(name))

    def test_doctor_deletion_cleans_up_both_files(self):
        doc = make_doctor(
            medical_certificate_image=make_image_file(name='cert3.jpg'),
            national_card_image=make_image_file(name='card3.jpg'),
        )
        cert_name = doc.medical_certificate_image.name
        card_name = doc.national_card_image.name
        with self.captureOnCommitCallbacks(execute=True):
            doc.delete()
        self.assertFalse(default_storage.exists(cert_name))
        self.assertFalse(default_storage.exists(card_name))

    def test_deleting_doctor_without_documents_does_not_crash(self):
        doc = make_doctor()
        with self.captureOnCommitCallbacks(execute=True):
            doc.delete()  # must not raise

    def test_duplicate_cleanup_does_not_crash(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        name = doc.medical_certificate_image.name
        default_storage.delete(name)  # simulate the file already being gone
        with self.captureOnCommitCallbacks(execute=True):
            doc.medical_certificate_image = None
            doc.save()  # must not raise even though the "old" file is already gone


# ---------------------------------------------------------------------------
# Admin form: layout, upload, replace/clear via real HTTP, preview rendering
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=_TEST_MEDIA_ROOT)
class DoctorDocumentAdminFormTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='doc_admin', password='pass')
        self.client.force_login(self.superuser)

    def _base_post_data(self, doc):
        return {
            'full_name': doc.full_name,
            'national_id': doc.national_id,
            'medical_system_number': doc.medical_system_number,
            'specialty': doc.specialty_id,
            'collaboration_start_date': '',
            'license_last_renewal_date': '',
            'phone_number': doc.phone_number,
            'clinic_phone': doc.clinic_phone,
            'email': doc.email,
            'address': doc.address,
            'cooperation_status': doc.cooperation_status,
            'notes': doc.notes,
            # Phase 6 added a DoctorSurgeryRate inline to the Doctor form;
            # Django admin requires its management form data on every POST
            # even when submitting zero rate rows.
            'surgery_rates-TOTAL_FORMS': '0',
            'surgery_rates-INITIAL_FORMS': '0',
            'surgery_rates-MIN_NUM_FORMS': '0',
            'surgery_rates-MAX_NUM_FORMS': '1000',
        }

    def test_form_is_multipart(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'enctype="multipart/form-data"')

    def test_documents_section_after_contact_info(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        contact_pos = content.index('fieldset-heading">اطلاعات تماس</h2>')
        docs_pos = content.index('fieldset-heading">مدارک پزشک</h2>')
        financial_pos = content.index('fieldset-heading">مالی</h2>')
        self.assertTrue(contact_pos < docs_pos < financial_pos)

    def test_medical_certificate_before_national_card(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertTrue(
            content.index('id_medical_certificate_image') < content.index('id_national_card_image')
        )

    def test_add_page_shows_both_fields_no_broken_preview(self):
        resp = self.client.get('/admin/contacts/doctor/add/')
        content = resp.content.decode()
        self.assertIn('id_medical_certificate_image', content)
        self.assertIn('id_national_card_image', content)
        self.assertIn('ثبت نشده', content)

    def test_first_save_upload_works_on_add_form(self):
        specialty = make_specialty('تخصص آپلود اول')
        data = {
            'full_name': 'دکتر جدید با مدرک',
            'national_id': '', 'medical_system_number': '', 'specialty': specialty.pk,
            'collaboration_start_date': '', 'license_last_renewal_date': '',
            'phone_number': '09121110000', 'clinic_phone': '', 'email': '', 'address': '',
            'cooperation_status': 'active', 'notes': '',
            'surgery_rates-TOTAL_FORMS': '0', 'surgery_rates-INITIAL_FORMS': '0',
            'surgery_rates-MIN_NUM_FORMS': '0', 'surgery_rates-MAX_NUM_FORMS': '1000',
        }
        data['medical_certificate_image'] = make_image_file()
        resp = self.client.post('/admin/contacts/doctor/add/', data)
        self.assertEqual(resp.status_code, 302)
        doc = Doctor.objects.get(full_name='دکتر جدید با مدرک')
        self.assertTrue(doc.medical_certificate_image)

    def test_both_files_can_be_uploaded_together(self):
        doc = make_doctor()
        data = self._base_post_data(doc)
        data['medical_certificate_image'] = make_image_file(name='c1.jpg')
        data['national_card_image'] = make_image_file(name='c2.jpg')
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertTrue(doc.medical_certificate_image)
        self.assertTrue(doc.national_card_image)

    def test_only_one_file_can_be_uploaded(self):
        doc = make_doctor()
        data = self._base_post_data(doc)
        data['medical_certificate_image'] = make_image_file()
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertTrue(doc.medical_certificate_image)
        self.assertFalse(doc.national_card_image)

    def test_existing_file_remains_when_editing_unrelated_field(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        original_name = doc.medical_certificate_image.name
        data = self._base_post_data(doc)
        data['full_name'] = 'دکتر ویرایش‌شده'
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.medical_certificate_image.name, original_name)

    def test_replacing_medical_certificate_works(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        old_name = doc.medical_certificate_image.name
        data = self._base_post_data(doc)
        data['medical_certificate_image'] = make_image_file(name='replacement.jpg')
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertNotEqual(doc.medical_certificate_image.name, old_name)
        self.assertFalse(default_storage.exists(old_name))

    def test_replacing_national_card_does_not_affect_certificate(self):
        doc = make_doctor(
            medical_certificate_image=make_image_file(name='cert.jpg'),
            national_card_image=make_image_file(name='card.jpg'),
        )
        cert_name = doc.medical_certificate_image.name
        data = self._base_post_data(doc)
        data['national_card_image'] = make_image_file(name='new_card.jpg')
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.medical_certificate_image.name, cert_name)

    def test_clearing_medical_certificate_via_form(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        data = self._base_post_data(doc)
        data['medical_certificate_image-clear'] = 'on'
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertFalse(doc.medical_certificate_image)

    def test_clearing_national_card_preserves_certificate(self):
        doc = make_doctor(
            medical_certificate_image=make_image_file(name='cert.jpg'),
            national_card_image=make_image_file(name='card.jpg'),
        )
        cert_name = doc.medical_certificate_image.name
        data = self._base_post_data(doc)
        data['national_card_image-clear'] = 'on'
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertFalse(doc.national_card_image)
        self.assertEqual(doc.medical_certificate_image.name, cert_name)

    def test_validation_failure_does_not_delete_existing_file(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        original_name = doc.medical_certificate_image.name
        data = self._base_post_data(doc)
        data['phone_number'] = ''  # required field left blank -> validation error
        data['medical_certificate_image'] = make_fake_jpg()  # also invalid
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors
        doc.refresh_from_db()
        self.assertEqual(doc.medical_certificate_image.name, original_name)
        self.assertTrue(default_storage.exists(original_name))

    def test_edit_form_shows_thumbnail_and_view_action(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('doc-preview-thumb', content)
        self.assertIn('مشاهده فایل', content)
        self.assertIn('target="_blank"', content)
        self.assertIn('rel="noopener noreferrer"', content)

    def test_empty_document_shows_placeholder(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'ثبت نشده')

    def test_no_raw_filesystem_path_in_rendered_html(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertNotIn(str(settings.MEDIA_ROOT), content)
        self.assertNotIn(doc.medical_certificate_image.name, content)


# ---------------------------------------------------------------------------
# Protected document endpoints
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=_TEST_MEDIA_ROOT)
class DoctorDocumentProtectedAccessTest(TestCase):

    def setUp(self):
        self.doctor = make_doctor(medical_certificate_image=make_image_file(), national_card_image=make_image_file(name='c.jpg'))
        self.authorized = User.objects.create_user(username='doc_viewer', password='pass', is_staff=True)
        self.authorized.user_permissions.add(Permission.objects.get(codename='view_doctor'))
        self.unauthorized = User.objects.create_user(username='doc_no_perm', password='pass', is_staff=True)

    def _cert_url(self, pk=None):
        return reverse('admin:contacts_doctor_medical_certificate', args=[pk or self.doctor.pk])

    def _card_url(self, pk=None):
        return reverse('admin:contacts_doctor_national_card', args=[pk or self.doctor.pk])

    def test_authorized_user_can_access_medical_certificate(self):
        self.client.force_login(self.authorized)
        resp = self.client.get(self._cert_url())
        self.assertEqual(resp.status_code, 200)

    def test_authorized_user_can_access_national_card(self):
        self.client.force_login(self.authorized)
        resp = self.client.get(self._card_url())
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_user_denied(self):
        resp = self.client.get(self._cert_url())
        self.assertIn(resp.status_code, (302, 403))

    def test_unauthorized_user_denied(self):
        self.client.force_login(self.unauthorized)
        resp = self.client.get(self._cert_url())
        self.assertEqual(resp.status_code, 403)

    def test_missing_document_returns_404(self):
        empty_doctor = make_doctor(phone_number='09129998888')
        self.client.force_login(self.authorized)
        resp = self.client.get(self._cert_url(pk=empty_doctor.pk))
        self.assertEqual(resp.status_code, 404)

    def test_invalid_doctor_id_returns_404(self):
        self.client.force_login(self.authorized)
        resp = self.client.get(self._cert_url(pk=999999))
        self.assertEqual(resp.status_code, 404)

    def test_response_has_safe_content_type(self):
        self.client.force_login(self.authorized)
        resp = self.client.get(self._cert_url())
        self.assertIn(resp['Content-Type'], ('image/jpeg', 'image/jpg'))

    def test_response_has_nosniff_header(self):
        self.client.force_login(self.authorized)
        resp = self.client.get(self._cert_url())
        self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')

    def test_response_does_not_reveal_absolute_path(self):
        self.client.force_login(self.authorized)
        resp = self.client.get(self._cert_url())
        for header_value in resp.headers.values():
            self.assertNotIn(str(settings.MEDIA_ROOT), str(header_value))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=_TEST_MEDIA_ROOT)
class DoctorDocumentApiTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='doc_api_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_api_returns_null_for_empty_documents(self):
        doc = make_doctor()
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        self.assertIsNone(resp.data['medical_certificate_image'])
        self.assertIsNone(resp.data['national_card_image'])

    def test_api_returns_protected_url_for_existing_document(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        url = resp.data['medical_certificate_image']
        self.assertIsNotNone(url)
        self.assertIn(f'/contacts/doctor/{doc.pk}/documents/medical-certificate/', url)

    def test_api_does_not_return_local_path(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        url = resp.data['medical_certificate_image']
        self.assertNotIn(str(settings.MEDIA_ROOT), url)
        self.assertNotIn('media/doctors', url)

    def test_partial_update_omitting_files_preserves_existing(self):
        doc = make_doctor(medical_certificate_image=make_image_file())
        original_name = doc.medical_certificate_image.name
        resp = self.client.patch(f'{DOCTORS_URL}{doc.pk}/', {'full_name': 'دکتر ای‌پی‌آی به‌روزرسانی‌شده'}, format='json')
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.medical_certificate_image.name, original_name)

    def test_invalid_api_upload_rejected(self):
        doc = make_doctor()
        resp = self.client.patch(
            f'{DOCTORS_URL}{doc.pk}/',
            {'medical_certificate_image': make_fake_jpg()},
            format='multipart',
        )
        self.assertEqual(resp.status_code, 400)

    def test_valid_api_upload_succeeds(self):
        doc = make_doctor()
        resp = self.client.patch(
            f'{DOCTORS_URL}{doc.pk}/',
            {'medical_certificate_image': make_image_file()},
            format='multipart',
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertTrue(doc.medical_certificate_image)

    def test_api_permissions_still_enforced(self):
        self.client.force_authenticate(user=None)
        doc = make_doctor()
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Cross-phase regression spot-checks (full Phase 3/4 suites are re-run
# separately — these only cover new interaction points introduced here).
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=_TEST_MEDIA_ROOT)
class Phase5RegressionSpotCheckTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='doc_regress_admin', password='pass')
        self.client.force_login(self.superuser)

    def test_jalali_date_fields_still_present_alongside_documents(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('id_collaboration_start_date', content)
        self.assertIn('id_license_last_renewal_date', content)
        self.assertIn('id_medical_certificate_image', content)

    def test_specialty_selector_and_controls_still_present(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('id="id_specialty"', content)
        self.assertIn('admin/js/doctor_specialty.js', content)

    def test_no_specialty_sidebar_entry(self):
        resp = self.client.get('/admin/contacts/doctor/')
        self.assertNotIn('تخصص‌ها', resp.content.decode())

    def test_no_standalone_doctor_detail_page(self):
        # Django admin registers a generic '<path:object_id>/' redirect for
        # any model that bounces an unrecognized sub-path to the change
        # view — this is stock Django behavior for every model, not
        # evidence of (or a substitute for) a dedicated Doctor detail view.
        # No detail template/view/URL name was ever registered for Doctor.
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/detail/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.endswith('/change/'))

    def test_doctor_change_url_still_works(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_old_doctorcontact_redirect_still_works(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctorcontact/{doc.pk}/change/')
        self.assertIn(resp.status_code, (301, 302))
