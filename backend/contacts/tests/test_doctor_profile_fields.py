"""Phase 4 tests: Doctor base-information/contact fields.

Covers the model/migration-safety, national-id, medical-system-number,
phone, Jalali date, admin-form-layout, detail/list/search, and API items
from Phase 4's test plan. Phase 3 Specialty-workflow regression is covered
by contacts/tests/test_doctor_specialty_admin.py, which is re-run unchanged
as part of the full contacts suite (no Phase 3 endpoint/JS contract touched
in this phase).
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from contacts.models import Doctor, DoctorSpecialty
from common.text import normalize_identifier

User = get_user_model()
DOCTORS_URL = '/api/v2/contacts/doctors/'


def make_specialty(name='جراحی عمومی'):
    obj, _ = DoctorSpecialty.objects.get_or_create(name=name)
    return obj


def make_doctor(**kwargs):
    if isinstance(kwargs.get('specialty'), str):
        kwargs['specialty'] = make_specialty(kwargs['specialty'])
    defaults = {
        'full_name': 'دکتر تست پروفایل',
        'specialty': make_specialty(),
        'phone_number': '09121234567',
    }
    defaults.update(kwargs)
    return Doctor.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model / data-preservation
# ---------------------------------------------------------------------------

class DoctorProfileFieldsModelTest(TestCase):

    def test_new_fields_blank_by_default(self):
        doc = make_doctor()
        self.assertEqual(doc.national_id, '')
        self.assertEqual(doc.medical_system_number, '')
        self.assertEqual(doc.clinic_phone, '')
        self.assertIsNone(doc.collaboration_start_date)
        self.assertIsNone(doc.license_last_renewal_date)

    def test_new_fields_are_nullable_optional(self):
        doc = Doctor(
            full_name='دکتر خالی', specialty=make_specialty(), phone_number='0912',
        )
        doc.full_clean(exclude=['id'])  # should not raise for the 5 new fields

    def test_no_fake_dates_are_created(self):
        doc = make_doctor()
        self.assertIsNone(doc.collaboration_start_date)
        self.assertIsNone(doc.license_last_renewal_date)

    def test_existing_specialty_relation_preserved_on_save(self):
        specialty = make_specialty('تخصص حفظ‌شده')
        doc = make_doctor(specialty=specialty)
        doc.full_name = 'دکتر ویرایش‌شده'
        doc.save()
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, specialty.pk)

    def test_pk_unchanged_after_unrelated_update(self):
        doc = make_doctor()
        pk_before = doc.pk
        doc.notes = 'یادداشت جدید'
        doc.save()
        self.assertEqual(doc.pk, pk_before)


# ---------------------------------------------------------------------------
# National ID
# ---------------------------------------------------------------------------

class DoctorNationalIdTest(TestCase):

    def test_saves_and_reloads(self):
        doc = make_doctor(national_id='0012345678')
        doc.refresh_from_db()
        self.assertEqual(doc.national_id, '0012345678')

    def test_leading_zero_preserved(self):
        doc = make_doctor(national_id='0123456789')
        doc.refresh_from_db()
        self.assertTrue(doc.national_id.startswith('0'))
        self.assertEqual(doc.national_id, '0123456789')

    def test_persian_digits_normalized(self):
        doc = make_doctor(national_id='۰۱۲۳۴۵۶۷۸۹')
        doc.refresh_from_db()
        self.assertEqual(doc.national_id, '0123456789')

    def test_arabic_digits_normalized(self):
        doc = make_doctor(national_id='٠١٢٣٤٥٦٧٨٩')
        doc.refresh_from_db()
        self.assertEqual(doc.national_id, '0123456789')

    def test_whitespace_trimmed(self):
        doc = make_doctor(national_id='  0012345678  ')
        doc.refresh_from_db()
        self.assertEqual(doc.national_id, '0012345678')

    def test_not_stored_as_integer(self):
        doc = make_doctor(national_id='0012345678')
        doc.refresh_from_db()
        self.assertIsInstance(doc.national_id, str)


# ---------------------------------------------------------------------------
# Medical system number
# ---------------------------------------------------------------------------

class DoctorMedicalSystemNumberTest(TestCase):

    def test_saves_and_reloads(self):
        doc = make_doctor(medical_system_number='045678')
        doc.refresh_from_db()
        self.assertEqual(doc.medical_system_number, '045678')

    def test_leading_zero_preserved(self):
        doc = make_doctor(medical_system_number='0456')
        doc.refresh_from_db()
        self.assertEqual(doc.medical_system_number, '0456')

    def test_whitespace_trimmed(self):
        doc = make_doctor(medical_system_number='  045678  ')
        doc.refresh_from_db()
        self.assertEqual(doc.medical_system_number, '045678')

    def test_persian_arabic_digits_normalized(self):
        doc = make_doctor(medical_system_number='۰۴۵۶۷۸')
        doc.refresh_from_db()
        self.assertEqual(doc.medical_system_number, '045678')
        doc2 = make_doctor(phone_number='09120000011', medical_system_number='٠٤٥٦٧٩')
        doc2.refresh_from_db()
        self.assertEqual(doc2.medical_system_number, '045679')

    def test_not_stored_as_integer(self):
        doc = make_doctor(medical_system_number='045678')
        doc.refresh_from_db()
        self.assertIsInstance(doc.medical_system_number, str)


# ---------------------------------------------------------------------------
# Phones
# ---------------------------------------------------------------------------

class DoctorPhoneFieldsTest(TestCase):

    def test_mobile_phone_field_name_unchanged(self):
        self.assertTrue(hasattr(Doctor, 'phone_number'))

    def test_mobile_phone_label_updated(self):
        field = Doctor._meta.get_field('phone_number')
        self.assertEqual(field.verbose_name, 'شماره تلفن همراه')

    def test_clinic_phone_saves_and_reloads(self):
        doc = make_doctor(clinic_phone='02188776655')
        doc.refresh_from_db()
        self.assertEqual(doc.clinic_phone, '02188776655')

    def test_clinic_phone_preserves_leading_zero(self):
        doc = make_doctor(clinic_phone='0218877')
        doc.refresh_from_db()
        self.assertTrue(doc.clinic_phone.startswith('0'))

    def test_clinic_phone_accepts_landline_and_extension_formats(self):
        # Not validated as mobile-only — landline/international formats pass.
        doc = make_doctor(clinic_phone='+98 21 8877-6655')
        doc.full_clean()
        doc.refresh_from_db()
        self.assertIn('8877', doc.clinic_phone)

    def test_existing_mobile_phone_value_not_altered_by_save(self):
        doc = make_doctor(phone_number='۰۹۱۲۱۲۳۴۵۶۷')
        doc.refresh_from_db()
        # No existing project behavior normalizes phone_number — it is
        # stored exactly as submitted (Persian digits untouched).
        self.assertEqual(doc.phone_number, '۰۹۱۲۱۲۳۴۵۶۷')


# ---------------------------------------------------------------------------
# Jalali dates
# ---------------------------------------------------------------------------

class DoctorDateFieldsTest(TestCase):

    def test_collaboration_start_date_saves_as_datefield(self):
        d = datetime.date(2024, 5, 10)
        doc = make_doctor(collaboration_start_date=d)
        doc.refresh_from_db()
        self.assertEqual(doc.collaboration_start_date, d)
        self.assertIsInstance(doc.collaboration_start_date, datetime.date)

    def test_license_last_renewal_date_saves_as_datefield(self):
        d = datetime.date(2023, 11, 2)
        doc = make_doctor(license_last_renewal_date=d)
        doc.refresh_from_db()
        self.assertEqual(doc.license_last_renewal_date, d)

    def test_both_dates_accept_null(self):
        doc = make_doctor()
        self.assertIsNone(doc.collaboration_start_date)
        self.assertIsNone(doc.license_last_renewal_date)

    def test_both_dates_can_be_cleared(self):
        doc = make_doctor(
            collaboration_start_date=datetime.date(2024, 1, 1),
            license_last_renewal_date=datetime.date(2024, 1, 1),
        )
        doc.collaboration_start_date = None
        doc.license_last_renewal_date = None
        doc.save()
        doc.refresh_from_db()
        self.assertIsNone(doc.collaboration_start_date)
        self.assertIsNone(doc.license_last_renewal_date)


class DoctorAdminJalaliDateWidgetTest(TestCase):
    """Admin form round-trip for the two new date fields via the project's
    existing JalaliFormDateField/JalaliDateWidget (no custom JS/parser)."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='pf_admin', password='pass')
        self.client.force_login(self.superuser)

    def _post_data(self, doc, **overrides):
        data = {
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
        data.update(overrides)
        return data

    def test_add_form_has_no_time_or_hour_minute_input(self):
        resp = self.client.get('/admin/contacts/doctor/add/')
        content = resp.content.decode()
        self.assertNotIn('datetime-local', content)
        self.assertNotIn('id_collaboration_start_date_1', content)  # split-datetime hour widget suffix
        self.assertIn('id="id_collaboration_start_date"', content)
        self.assertIn('id="id_license_last_renewal_date"', content)

    def test_jalali_date_round_trips_without_shifting(self):
        doc = make_doctor()
        resp = self.client.post(
            f'/admin/contacts/doctor/{doc.pk}/change/',
            self._post_data(doc, collaboration_start_date='1404/04/18'),
        )
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.collaboration_start_date, datetime.date(2025, 7, 9))

        resp2 = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp2, '۱۴۰۴/۰۴/۱۸')

    def test_leap_year_jalali_date_handled_correctly(self):
        # 1403/12/30 only exists in a leap Jalali year — 1403 is leap.
        doc = make_doctor()
        resp = self.client.post(
            f'/admin/contacts/doctor/{doc.pk}/change/',
            self._post_data(doc, license_last_renewal_date='1403/12/30'),
        )
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.license_last_renewal_date, datetime.date(2025, 3, 20))

        resp2 = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp2, '۱۴۰۳/۱۲/۳۰')

    def test_clearing_date_saves_null(self):
        doc = make_doctor(collaboration_start_date=datetime.date(2024, 1, 1))
        resp = self.client.post(
            f'/admin/contacts/doctor/{doc.pk}/change/',
            self._post_data(doc, collaboration_start_date=''),
        )
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertIsNone(doc.collaboration_start_date)

    def test_invalid_date_shows_persian_error(self):
        doc = make_doctor()
        resp = self.client.post(
            f'/admin/contacts/doctor/{doc.pk}/change/',
            self._post_data(doc, collaboration_start_date='not-a-date'),
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors
        content = resp.content.decode()
        self.assertIn('errorlist', content)
        # JalaliFormDateField/parse_jalali_date's actual Persian message for
        # a non-numeric date string.
        self.assertIn('تاریخ باید فقط شامل اعداد باشد', content)

    def test_reopening_edit_page_does_not_shift_date_by_one_day(self):
        doc = make_doctor(collaboration_start_date=datetime.date(2025, 6, 17))
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        # 2025-06-17 == 1404/03/27 (verified against common/tests/test_dates.py)
        self.assertContains(resp, '۱۴۰۴/۰۳/۲۷')


# ---------------------------------------------------------------------------
# Admin form layout
# ---------------------------------------------------------------------------

class DoctorAdminFormLayoutTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='pf_layout_admin', password='pass')
        self.client.force_login(self.superuser)

    def _field_positions(self, content, field_ids):
        return [content.index(f'id="{fid}"') for fid in field_ids]

    def test_add_page_contains_all_new_fields(self):
        resp = self.client.get('/admin/contacts/doctor/add/')
        content = resp.content.decode()
        for fid in (
            'id_national_id', 'id_medical_system_number', 'id_specialty',
            'id_collaboration_start_date', 'id_license_last_renewal_date',
            'id_clinic_phone',
        ):
            self.assertIn(f'id="{fid}"', content)

    def test_change_page_contains_all_new_fields(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        for fid in (
            'id_national_id', 'id_medical_system_number', 'id_specialty',
            'id_collaboration_start_date', 'id_license_last_renewal_date',
            'id_clinic_phone',
        ):
            self.assertIn(f'id="{fid}"', content)

    def test_base_information_field_order(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        positions = self._field_positions(content, [
            'id_full_name', 'id_national_id', 'id_medical_system_number',
            'id_specialty', 'id_collaboration_start_date', 'id_license_last_renewal_date',
        ])
        self.assertEqual(positions, sorted(positions))

    def test_contact_information_field_order(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        positions = self._field_positions(content, [
            'id_phone_number', 'id_clinic_phone', 'id_email', 'id_address',
        ])
        self.assertEqual(positions, sorted(positions))

    def test_specialty_selector_still_in_base_information_section(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        # Doctor.Meta.verbose_name_plural ('اطلاعات تماس دکترها') also contains
        # 'اطلاعات تماس' and appears earlier, in the breadcrumbs — anchor on
        # the actual fieldset <h2> heading markup instead of the bare text.
        base_start = content.index('fieldset-heading">اطلاعات پایه</h2>')
        contact_start = content.index('fieldset-heading">اطلاعات تماس</h2>')
        specialty_pos = content.index('id="id_specialty"')
        self.assertTrue(base_start < specialty_pos < contact_start)

    def test_specialty_add_delete_activate_controls_present(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'admin/js/doctor_specialty.js')

    def test_document_upload_fields_added_in_phase_5(self):
        # This test originally asserted the ABSENCE of any file input, to
        # confirm Phase 4 did not overreach into document uploads (which
        # were explicitly out of scope for that phase). Phase 5 was later
        # scoped specifically to add the medical-certificate/national-card
        # ImageFields, so that assertion is now intentionally superseded —
        # this checks the new, correct state instead: exactly the two
        # requested file fields exist, nothing more.
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertEqual(content.count('type="file"'), 2)
        self.assertIn('id_medical_certificate_image', content)
        self.assertIn('id_national_card_image', content)

    def test_no_surgery_rate_fields(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertNotIn('surgery_type_rate', content)
        self.assertNotIn('DoctorSurgeryRate', content)


# ---------------------------------------------------------------------------
# Detail (admin change form) / list / search
# ---------------------------------------------------------------------------

class DoctorDetailDisplayTest(TestCase):
    """No standalone Doctor 'detail' page exists in this project (verified —
    only Product/Vendor/Employee have one). The admin change form is the
    single per-Doctor view and is what Phase 4 updates to show every field."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='pf_detail_admin', password='pass')
        self.client.force_login(self.superuser)

    def test_all_new_fields_display_with_values(self):
        doc = make_doctor(
            national_id='0012345678', medical_system_number='045678',
            clinic_phone='02188776655',
            collaboration_start_date=datetime.date(2024, 1, 1),
            license_last_renewal_date=datetime.date(2023, 6, 1),
        )
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('0012345678', content)
        self.assertIn('045678', content)
        self.assertIn('02188776655', content)

    def test_empty_values_are_blank_not_error(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_specialty_name_shown_not_numeric_id(self):
        specialty = make_specialty('تخصص نمایشی')
        doc = make_doctor(specialty=specialty)
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'تخصص نمایشی')

    def test_inactive_assigned_specialty_still_shown_with_indicator(self):
        specialty = make_specialty('تخصص غیرفعال نمایشی')
        doc = make_doctor(specialty=specialty)
        specialty.is_active = False
        specialty.save(update_fields=['is_active'])
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, 'تخصص غیرفعال نمایشی (غیرفعال)')


class DoctorListTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='pf_list_admin', password='pass')
        self.client.force_login(self.superuser)

    def test_directory_list_headers_include_new_columns(self):
        resp = self.client.get('/admin/contacts/doctor/')
        content = resp.content.decode()
        self.assertIn('شماره تلفن همراه', content)
        self.assertIn('شماره تلفن مطب / کلینیک', content)
        self.assertIn('شماره نظام پزشکی', content)

    def test_directory_api_feed_includes_new_field_values(self):
        make_doctor(clinic_phone='02100000000', medical_system_number='999', phone_number='09121110004')
        resp = self.client.get(DOCTORS_URL, {'search': ''})
        self.assertEqual(resp.status_code, 200)
        row = next(r for r in resp.data['results'] if r['clinic_phone'] == '02100000000')
        self.assertEqual(row['medical_system_number'], '999')


class DoctorSearchTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='pf_search_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_search_by_clinic_phone(self):
        make_doctor(clinic_phone='02188776655', phone_number='09121110000')
        make_doctor(clinic_phone='02199998888', phone_number='09122220000')
        resp = self.client.get(DOCTORS_URL, {'search': '88776655'})
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_national_id(self):
        make_doctor(national_id='1234567890', phone_number='09121110001')
        make_doctor(national_id='9999999999', phone_number='09122220001')
        resp = self.client.get(DOCTORS_URL, {'search': '1234567890'})
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_medical_system_number(self):
        make_doctor(medical_system_number='555444', phone_number='09121110002')
        make_doctor(medical_system_number='111222', phone_number='09122220002')
        resp = self.client.get(DOCTORS_URL, {'search': '555444'})
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_specialty_name_still_works(self):
        # DRF's SearchFilter AND-matches whitespace-separated search terms
        # (each term OR'd across search_fields), so specialty names must not
        # share tokens between the two doctors here or both would match.
        make_doctor(specialty='قلبی‌عروقی', phone_number='09121110003')
        make_doctor(specialty='ارتوپدی', phone_number='09122220003')
        resp = self.client.get(DOCTORS_URL, {'search': 'قلبی‌عروقی'})
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_mobile_phone_still_works(self):
        make_doctor(phone_number='09123334444')
        make_doctor(phone_number='09125556666')
        resp = self.client.get(DOCTORS_URL, {'search': '3334444'})
        self.assertEqual(resp.data['count'], 1)

    def test_search_results_do_not_duplicate_doctors(self):
        make_doctor(full_name='دکتر یکتا', specialty='تخصص یکتا', phone_number='09129990001')
        resp = self.client.get(DOCTORS_URL, {'search': 'یکتا'})
        ids = [row['id'] for row in resp.data['results']]
        self.assertEqual(len(ids), len(set(ids)))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class DoctorApiProfileFieldsTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='pf_api_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_api_returns_all_five_new_fields(self):
        doc = make_doctor(
            national_id='0012345678', medical_system_number='045678',
            clinic_phone='02188776655',
            collaboration_start_date=datetime.date(2024, 1, 1),
            license_last_renewal_date=datetime.date(2023, 6, 1),
        )
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        for field in (
            'national_id', 'medical_system_number', 'clinic_phone',
            'collaboration_start_date', 'license_last_renewal_date',
        ):
            self.assertIn(field, resp.data)
        self.assertEqual(resp.data['national_id'], '0012345678')
        self.assertEqual(resp.data['collaboration_start_date'], '2024-01-01')

    def test_api_preserves_mobile_phone_field_name(self):
        doc = make_doctor()
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        self.assertIn('phone_number', resp.data)

    def test_api_returns_null_for_empty_dates(self):
        doc = make_doctor()
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        self.assertIsNone(resp.data['collaboration_start_date'])
        self.assertIsNone(resp.data['license_last_renewal_date'])

    def test_api_dates_are_iso_gregorian(self):
        doc = make_doctor(collaboration_start_date=datetime.date(2026, 7, 8))
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        self.assertEqual(resp.data['collaboration_start_date'], '2026-07-08')

    def test_api_preserves_specialty_and_specialty_name(self):
        specialty = make_specialty('تخصص ای‌پی‌آی')
        doc = make_doctor(specialty=specialty)
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        self.assertEqual(resp.data['specialty'], specialty.pk)
        self.assertEqual(resp.data['specialty_name'], 'تخصص ای‌پی‌آی')

    def test_api_rejects_new_assignment_of_inactive_specialty(self):
        current = make_specialty('تخصص فعلی ای‌پی‌آی')
        inactive = make_specialty('تخصص غیرفعال ای‌پی‌آی')
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        doc = make_doctor(specialty=current)
        resp = self.client.patch(f'{DOCTORS_URL}{doc.pk}/', {'specialty': inactive.pk}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_existing_doctor_may_retain_inactive_specialty(self):
        specialty = make_specialty('تخصص حفظ‌شده ای‌پی‌آی')
        doc = make_doctor(specialty=specialty)
        specialty.is_active = False
        specialty.save(update_fields=['is_active'])
        resp = self.client.patch(
            f'{DOCTORS_URL}{doc.pk}/', {'full_name': 'دکتر به‌روزرسانی‌شده'}, format='json',
        )
        self.assertEqual(resp.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.specialty_id, specialty.pk)

    def test_create_with_new_fields_via_api(self):
        specialty = make_specialty('تخصص ایجاد ای‌پی‌آی')
        payload = {
            'full_name': 'دکتر ایجادشده',
            'specialty': specialty.pk,
            'phone_number': '09121230000',
            'national_id': '۰۰۹۹۸۸۷۷۶۶',
            'medical_system_number': '123456',
            'clinic_phone': '02133334444',
            'collaboration_start_date': '2024-02-01',
        }
        resp = self.client.post(DOCTORS_URL, payload, format='json')
        self.assertEqual(resp.status_code, 201)
        doc = Doctor.objects.get(pk=resp.data['id'])
        self.assertEqual(doc.national_id, '0099887766')
        self.assertEqual(doc.collaboration_start_date, datetime.date(2024, 2, 1))


# ---------------------------------------------------------------------------
# Shared helper unit test
# ---------------------------------------------------------------------------

class NormalizeIdentifierHelperTest(TestCase):

    def test_trims_and_converts_digits(self):
        self.assertEqual(normalize_identifier('  ۰۹۱۲  '), '0912')
        self.assertEqual(normalize_identifier('  ٠٩١٢  '), '0912')

    def test_empty_returns_empty_string(self):
        self.assertEqual(normalize_identifier(None), '')
        self.assertEqual(normalize_identifier(''), '')

    def test_preserves_non_digit_characters(self):
        self.assertEqual(normalize_identifier('+98 21-8877'), '+98 21-8877')
