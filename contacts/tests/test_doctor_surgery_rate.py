"""Phase 6 tests: authoritative Surgery Type workflow + DoctorSurgeryRate
(per-Surgery-Type Doctor rate), managed inside the Doctor add/edit form.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from contacts.models import Doctor, DoctorSpecialty, DoctorSurgeryRate
from surgeries.models import Patient, SurgeryHistory, SurgeryType

User = get_user_model()


def make_specialty(name='جراحی عمومی'):
    obj, _ = DoctorSpecialty.objects.get_or_create(name=name)
    return obj


def make_doctor(**kwargs):
    if isinstance(kwargs.get('specialty'), str):
        kwargs['specialty'] = make_specialty(kwargs['specialty'])
    defaults = {
        'full_name': 'دکتر نرخ‌دار',
        'specialty': make_specialty(),
        'phone_number': '09121234567',
    }
    defaults.update(kwargs)
    return Doctor.objects.create(**defaults)


def make_surgery_type(name='نوع تست', code='rate-test', base_rate=Decimal('1000000'), is_active=True):
    obj, _ = SurgeryType.objects.get_or_create(
        code=code, defaults={'name': name, 'base_rate': base_rate, 'is_active': is_active},
    )
    return obj


# ---------------------------------------------------------------------------
# SurgeryType — authoritative model, labels, admin behavior
# ---------------------------------------------------------------------------

class SurgeryTypeLabelsTest(TestCase):

    def test_verbose_name(self):
        self.assertEqual(SurgeryType._meta.verbose_name, 'نوع عمل جراحی')

    def test_verbose_name_plural(self):
        self.assertEqual(SurgeryType._meta.verbose_name_plural, 'انواع عمل جراحی')

    def test_surgery_history_already_uses_fk_not_free_text(self):
        field = SurgeryHistory._meta.get_field('surgery_type')
        self.assertTrue(field.is_relation)
        self.assertEqual(field.related_model, SurgeryType)


class SurgeryTypeAdminTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='st_admin', password='pass')
        self.client.force_login(self.superuser)

    def test_changelist_returns_200_with_correct_title(self):
        resp = self.client.get('/admin/surgeries/surgerytype/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'انواع عمل جراحی')

    def test_add_page_returns_200(self):
        resp = self.client.get('/admin/surgeries/surgerytype/add/')
        self.assertEqual(resp.status_code, 200)

    def test_change_page_returns_200(self):
        st = make_surgery_type()
        resp = self.client.get(f'/admin/surgeries/surgerytype/{st.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_search_by_name(self):
        make_surgery_type(name='آپاندکتومی', code='appendectomy')
        make_surgery_type(name='بای‌پس', code='bypass')
        resp = self.client.get('/admin/surgeries/surgerytype/', {'q': 'آپاندکتومی'})
        self.assertContains(resp, 'آپاندکتومی')
        self.assertNotContains(resp, 'بای‌پس')

    def test_filter_by_active_status(self):
        # Note: 'غیرفعال' ("inactive") contains 'فعال' ("active") as a
        # literal substring, so the two type names must not collide that
        # way — use distinct roots instead.
        make_surgery_type(name='نوع روشن', code='active-test', is_active=True)
        make_surgery_type(name='نوع خاموش', code='inactive-test', is_active=False)
        resp = self.client.get('/admin/surgeries/surgerytype/', {'is_active__exact': '0'})
        self.assertContains(resp, 'نوع خاموش')
        self.assertNotContains(resp, 'نوع روشن')

    def test_ordering_by_name(self):
        self.assertEqual(SurgeryType._meta.ordering, ['name'])

    def test_referenced_surgery_type_cannot_be_deleted_unsafely(self):
        st = make_surgery_type(name='نوع محافظت‌شده', code='protected-test')
        doc = make_doctor(phone_number='09121110000')
        DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('500000'))
        with self.assertRaises(ProtectedError):
            st.delete()

    def test_unreferenced_surgery_type_can_be_deleted(self):
        st = make_surgery_type(name='قابل حذف', code='deletable-test')
        st.delete()  # must not raise
        self.assertFalse(SurgeryType.objects.filter(code='deletable-test').exists())


class InactiveSurgeryTypeVisibilityTest(TestCase):

    def test_inactive_type_remains_visible_in_surgery_history(self):
        st = make_surgery_type(name='نوع تاریخی', code='historical-test')
        patient = Patient.objects.create(
            full_name='بیمار تست نرخ', case_code='PAT-RATE-1', phone_number='09120000001', national_id='4444444444',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=st, amount=Decimal('1000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        st.is_active = False
        st.save(update_fields=['is_active'])
        surgery.refresh_from_db()
        self.assertEqual(surgery.surgery_type_id, st.pk)

    def test_inactive_type_remains_visible_in_existing_doctor_rate(self):
        st = make_surgery_type(name='نوع نرخ قدیمی', code='old-rate-test')
        doc = make_doctor(phone_number='09121110001')
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('700000'))
        st.is_active = False
        st.save(update_fields=['is_active'])
        rate.refresh_from_db()
        self.assertEqual(rate.surgery_type_id, st.pk)


# ---------------------------------------------------------------------------
# DoctorSurgeryRate model
# ---------------------------------------------------------------------------

class DoctorSurgeryRateModelTest(TestCase):

    def test_create_rate(self):
        doc = make_doctor()
        st = make_surgery_type()
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('850000'))
        self.assertEqual(rate.doctor_id, doc.pk)
        self.assertEqual(rate.surgery_type_id, st.pk)

    def test_str(self):
        doc = make_doctor(full_name='دکتر نمایشی')
        st = make_surgery_type(name='نوع نمایشی', code='display-test')
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('1'))
        self.assertIn('دکتر نمایشی', str(rate))

    def test_negative_rate_rejected(self):
        doc = make_doctor()
        st = make_surgery_type()
        rate = DoctorSurgeryRate(doctor=doc, surgery_type=st, rate=Decimal('-100'))
        with self.assertRaises(ValidationError):
            rate.clean()

    def test_unique_together_doctor_surgery_type(self):
        doc = make_doctor()
        st = make_surgery_type()
        DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('100'))
        with self.assertRaises(Exception):
            DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('200'))

    def test_different_doctors_can_have_rate_for_same_surgery_type(self):
        st = make_surgery_type()
        doc1 = make_doctor(phone_number='09121110002')
        doc2 = make_doctor(phone_number='09121110003')
        DoctorSurgeryRate.objects.create(doctor=doc1, surgery_type=st, rate=Decimal('100'))
        DoctorSurgeryRate.objects.create(doctor=doc2, surgery_type=st, rate=Decimal('200'))  # must not raise

    def test_deleting_doctor_cascades_rates(self):
        doc = make_doctor(phone_number='09121110004')
        st = make_surgery_type()
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('100'))
        doc.delete()
        self.assertFalse(DoctorSurgeryRate.objects.filter(pk=rate.pk).exists())

    def test_surgery_type_delete_protected_when_rate_exists(self):
        doc = make_doctor(phone_number='09121110005')
        st = make_surgery_type(name='نوع حفاظت‌شده ۲', code='protected-test-2')
        DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('100'))
        with self.assertRaises(ProtectedError):
            st.delete()

    def test_doctor_pk_and_surgery_history_unchanged_when_rate_added(self):
        doc = make_doctor(phone_number='09121110006')
        pk_before = doc.pk
        patient = Patient.objects.create(
            full_name='بیمار حفظ‌شده', case_code='PAT-RATE-2', phone_number='09120000002', national_id='5555555555',
        )
        st = make_surgery_type(name='نوع حفظ‌شده', code='preserve-test')
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=st, clinical_doctor=doc, amount=Decimal('1000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('900000'))
        doc.refresh_from_db()
        surgery.refresh_from_db()
        self.assertEqual(doc.pk, pk_before)
        self.assertEqual(surgery.clinical_doctor_id, doc.pk)
        self.assertEqual(surgery.surgery_type_id, st.pk)


# ---------------------------------------------------------------------------
# Rate management inside the Doctor admin form
# ---------------------------------------------------------------------------

class DoctorSurgeryRateInlineFormTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='dsr_admin', password='pass')
        self.client.force_login(self.superuser)

    def _base_post_data(self, doc, extra_management=None):
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
            'surgery_rates-TOTAL_FORMS': '1',
            'surgery_rates-INITIAL_FORMS': '0',
            'surgery_rates-MIN_NUM_FORMS': '0',
            'surgery_rates-MAX_NUM_FORMS': '1000',
            'surgery_rates-0-surgery_type': '',
            'surgery_rates-0-rate': '',
            'surgery_rates-0-id': '',
            'surgery_rates-0-doctor': str(doc.pk),
        }
        if extra_management:
            data.update(extra_management)
        return data

    def test_no_standalone_surgery_rate_panel(self):
        with self.assertRaises(NoReverseMatch):
            reverse('admin:contacts_doctorsurgeryrate_changelist')

    def test_change_form_contains_rate_inline_section(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('نرخ', content)
        self.assertIn('surgery_rates-TOTAL_FORMS', content)

    def test_add_rate_via_doctor_form(self):
        doc = make_doctor(phone_number='09121110007')
        st = make_surgery_type(name='نوع افزودن نرخ', code='add-rate-test')
        data = self._base_post_data(doc)
        data['surgery_rates-0-surgery_type'] = str(st.pk)
        data['surgery_rates-0-rate'] = '650000'
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        rate = DoctorSurgeryRate.objects.get(doctor=doc, surgery_type=st)
        self.assertEqual(rate.rate, Decimal('650000.00'))

    def test_edit_existing_rate_via_doctor_form(self):
        doc = make_doctor(phone_number='09121110008')
        st = make_surgery_type(name='نوع ویرایش نرخ', code='edit-rate-test')
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('100000'))
        data = self._base_post_data(doc)
        data['surgery_rates-INITIAL_FORMS'] = '1'
        data['surgery_rates-0-id'] = str(rate.pk)
        data['surgery_rates-0-surgery_type'] = str(st.pk)
        data['surgery_rates-0-rate'] = '999000'
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        rate.refresh_from_db()
        self.assertEqual(rate.rate, Decimal('999000.00'))

    def test_delete_rate_via_doctor_form(self):
        doc = make_doctor(phone_number='09121110009')
        st = make_surgery_type(name='نوع حذف نرخ', code='delete-rate-test')
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('100000'))
        data = self._base_post_data(doc)
        data['surgery_rates-INITIAL_FORMS'] = '1'
        data['surgery_rates-0-id'] = str(rate.pk)
        data['surgery_rates-0-surgery_type'] = str(st.pk)
        data['surgery_rates-0-rate'] = '100000'
        data['surgery_rates-0-DELETE'] = 'on'
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(DoctorSurgeryRate.objects.filter(pk=rate.pk).exists())

    def test_inactive_surgery_type_not_offered_for_new_rate(self):
        active = make_surgery_type(name='نوع فعال گزینه', code='active-choice-test')
        inactive = make_surgery_type(name='نوع غیرفعال گزینه', code='inactive-choice-test', is_active=False)
        doc = make_doctor(phone_number='09121110010')
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        # Scope to the inline's own surgery_type select — the Specialty
        # select on the same page also renders <option value="N"> and its
        # pks can coincidentally collide with a SurgeryType pk.
        start = content.index('id="id_surgery_rates-0-surgery_type"')
        end = content.index('</select>', start)
        rate_select_html = content[start:end]
        self.assertIn(f'value="{active.pk}"', rate_select_html)
        self.assertNotIn(f'value="{inactive.pk}"', rate_select_html)

    def test_existing_inactive_rate_still_shown_and_labeled(self):
        inactive = make_surgery_type(name='نوع نرخ غیرفعال فعلی', code='current-inactive-rate-test')
        doc = make_doctor(phone_number='09121110011')
        DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=inactive, rate=Decimal('100000'))
        inactive.is_active = False
        inactive.save(update_fields=['is_active'])
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertContains(resp, f'{inactive.name} (غیرفعال)')

    def test_cannot_assign_different_inactive_surgery_type(self):
        current = make_surgery_type(name='نوع فعلی نرخ', code='current-rate-test')
        inactive = make_surgery_type(name='نوع غیرفعال هدف نرخ', code='target-inactive-rate-test', is_active=False)
        doc = make_doctor(phone_number='09121110012')
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=current, rate=Decimal('100000'))
        data = self._base_post_data(doc)
        data['surgery_rates-INITIAL_FORMS'] = '1'
        data['surgery_rates-0-id'] = str(rate.pk)
        data['surgery_rates-0-surgery_type'] = str(inactive.pk)
        data['surgery_rates-0-rate'] = '100000'
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors
        self.assertContains(resp, 'برای انتساب جدید قابل انتخاب نیست')
        rate.refresh_from_db()
        self.assertEqual(rate.surgery_type_id, current.pk)

    def test_duplicate_surgery_type_for_same_doctor_rejected(self):
        doc = make_doctor(phone_number='09121110013')
        st = make_surgery_type(name='نوع تکراری', code='dup-rate-test')
        DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('100000'))
        data = self._base_post_data(doc)
        data['surgery_rates-0-surgery_type'] = str(st.pk)
        data['surgery_rates-0-rate'] = '200000'
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors
        self.assertEqual(DoctorSurgeryRate.objects.filter(doctor=doc, surgery_type=st).count(), 1)

    def test_saving_unrelated_field_preserves_existing_rates(self):
        doc = make_doctor(phone_number='09121110014')
        st = make_surgery_type(name='نوع حفظ‌شده فرم', code='preserve-form-rate-test')
        rate = DoctorSurgeryRate.objects.create(doctor=doc, surgery_type=st, rate=Decimal('321000'))
        data = self._base_post_data(doc)
        data['surgery_rates-INITIAL_FORMS'] = '1'
        data['surgery_rates-0-id'] = str(rate.pk)
        data['surgery_rates-0-surgery_type'] = str(st.pk)
        data['surgery_rates-0-rate'] = '321000'
        data['notes'] = 'یادداشت جدید'
        resp = self.client.post(f'/admin/contacts/doctor/{doc.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        rate.refresh_from_db()
        self.assertEqual(doc.notes, 'یادداشت جدید')
        self.assertEqual(rate.rate, Decimal('321000.00'))


# ---------------------------------------------------------------------------
# Cross-phase regression spot-checks
# ---------------------------------------------------------------------------

class Phase6RegressionSpotCheckTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='p6_regress_admin', password='pass')
        self.client.force_login(self.superuser)

    def test_specialty_selector_still_present(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('id="id_specialty"', content)
        self.assertIn('admin/js/doctor_specialty.js', content)

    def test_document_fields_still_present(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('id_medical_certificate_image', content)
        self.assertIn('id_national_card_image', content)

    def test_jalali_date_fields_still_present(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        content = resp.content.decode()
        self.assertIn('id_collaboration_start_date', content)
        self.assertIn('id_license_last_renewal_date', content)

    def test_no_specialty_sidebar_entry(self):
        resp = self.client.get('/admin/contacts/doctor/')
        self.assertNotIn('تخصص‌ها', resp.content.decode())

    def test_doctor_change_url_still_works(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctor/{doc.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_old_doctorcontact_redirect_still_works(self):
        doc = make_doctor()
        resp = self.client.get(f'/admin/contacts/doctorcontact/{doc.pk}/change/')
        self.assertIn(resp.status_code, (301, 302))
