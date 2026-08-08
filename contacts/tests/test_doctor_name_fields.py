"""Regression tests for the Doctor.first_name / last_name NOT NULL bug.

Root cause: a migration that added NOT-NULL first_name/last_name columns had
been applied to the local dev database and then its file went missing from
the codebase, leaving the Doctor model with no knowledge of those columns —
every admin POST omitted them from the INSERT and SQLite raised
`IntegrityError: NOT NULL constraint failed: contacts_doctor.first_name`.

Covers:
 - the previously-failing admin POST now succeeds (no 500 / IntegrityError)
 - first_name/last_name are derived from full_name and never left null
 - an entirely empty full_name is rejected by ordinary form validation,
   never reaching the database
 - the change form preserves an existing name when only the name is
   unchanged; another field can be edited without corrupting it
 - initial "full_name" on the change form matches the stored value
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from contacts.forms import DoctorAdminForm
from contacts.models import Doctor, DoctorSpecialty

ADD_URL = '/admin/contacts/doctor/add/'
User = get_user_model()


def make_specialty(name='جراحی عمومی'):
    obj, _ = DoctorSpecialty.objects.get_or_create(name=name)
    return obj


def make_doctor(**kwargs):
    if isinstance(kwargs.get('specialty'), str):
        kwargs['specialty'] = make_specialty(kwargs['specialty'])
    defaults = {
        'full_name': 'دکتر علی محمدی',
        'specialty': make_specialty(),
        'phone_number': '09121234567',
    }
    defaults.update(kwargs)
    return Doctor.objects.create(**defaults)


def _inline_management_data(prefix='surgery_rates'):
    return {
        f'{prefix}-TOTAL_FORMS': '0',
        f'{prefix}-INITIAL_FORMS': '0',
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }


def _add_post_data(specialty_pk, **overrides):
    data = {
        'full_name': 'دکتر رضا کریمی',
        'national_id': '',
        'medical_system_number': '',
        'specialty': specialty_pk,
        'phone_number': '09121234567',
        'clinic_phone': '',
        'email': '',
        'address': '',
        'collaboration_start_date': '',
        'license_last_renewal_date': '',
        'cooperation_status': 'active',
        'notes': '',
        'is_active': 'on',
        'center_commission_percent': '',
        'rate_per_surgery': '',
    }
    data.update(_inline_management_data())
    data.update(overrides)
    return data


class DoctorAdminAddPostTest(TestCase):
    """Exercises the exact failing path: a real POST to /admin/contacts/doctor/add/."""

    def setUp(self):
        self.admin = User.objects.create_superuser(username='doc_add_admin', password='pass')
        self.client.force_login(self.admin)
        self.specialty = make_specialty()

    def test_add_post_no_longer_raises_integrity_error(self):
        resp = self.client.post(ADD_URL, _add_post_data(self.specialty.pk))
        self.assertNotEqual(resp.status_code, 500)

    def test_add_post_creates_doctor(self):
        resp = self.client.post(ADD_URL, _add_post_data(self.specialty.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Doctor.objects.filter(full_name='دکتر رضا کریمی').exists())

    def test_created_doctor_has_non_null_first_name(self):
        self.client.post(ADD_URL, _add_post_data(self.specialty.pk))
        doc = Doctor.objects.get(full_name='دکتر رضا کریمی')
        self.assertIsNotNone(doc.first_name)
        self.assertNotEqual(doc.first_name, '')
        self.assertEqual(doc.first_name, 'دکتر')
        self.assertEqual(doc.last_name, 'رضا کریمی')

    def test_single_word_name_leaves_last_name_empty_not_null(self):
        resp = self.client.post(ADD_URL, _add_post_data(self.specialty.pk, full_name='محمد'))
        self.assertEqual(resp.status_code, 302)
        doc = Doctor.objects.get(full_name='محمد')
        self.assertEqual(doc.first_name, 'محمد')
        self.assertIsNotNone(doc.last_name)
        self.assertEqual(doc.last_name, '')

    def test_empty_full_name_returns_form_error_not_500(self):
        resp = self.client.post(ADD_URL, _add_post_data(self.specialty.pk, full_name=''))
        self.assertEqual(resp.status_code, 200)  # re-renders the form, no DB hit
        self.assertFalse(Doctor.objects.filter(phone_number='09121234567').exists())

    def test_whitespace_only_full_name_returns_form_error(self):
        resp = self.client.post(ADD_URL, _add_post_data(self.specialty.pk, full_name='   '))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Doctor.objects.exists())


class DoctorAdminFormNameDerivationTest(TestCase):

    def setUp(self):
        self.specialty = make_specialty()

    def test_new_doctor_derives_first_last_name(self):
        form = DoctorAdminForm(data=_add_post_data(self.specialty.pk, full_name='سارا احمدی نژاد'))
        self.assertTrue(form.is_valid(), form.errors)
        doc = form.save()
        self.assertEqual(doc.first_name, 'سارا')
        self.assertEqual(doc.last_name, 'احمدی نژاد')

    def test_collapses_internal_whitespace(self):
        form = DoctorAdminForm(data=_add_post_data(self.specialty.pk, full_name='  سارا   احمدی  '))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['full_name'], 'سارا احمدی')

    def test_change_form_initial_matches_stored_full_name(self):
        doc = make_doctor(full_name='دکتر حسین رستمی', specialty=self.specialty)
        form = DoctorAdminForm(instance=doc)
        self.assertEqual(form.initial.get('full_name') or form['full_name'].value(), 'دکتر حسین رستمی')

    def test_editing_unrelated_field_preserves_existing_name(self):
        doc = make_doctor(full_name='دکتر حسین رستمی', specialty=self.specialty)
        doc.first_name = 'حسین'
        doc.last_name = 'رستمی-دستی'  # simulate a manually-corrected split
        doc.save()

        data = _add_post_data(self.specialty.pk, full_name='دکتر حسین رستمی')
        data['email'] = 'new-email@example.com'
        form = DoctorAdminForm(data=data, instance=Doctor.objects.get(pk=doc.pk))
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.first_name, 'حسین')
        self.assertEqual(saved.last_name, 'رستمی-دستی')

    def test_changing_full_name_rederives_names(self):
        doc = make_doctor(full_name='دکتر حسین رستمی', specialty=self.specialty)
        data = _add_post_data(self.specialty.pk, full_name='دکتر مریم صالحی')
        form = DoctorAdminForm(data=data, instance=Doctor.objects.get(pk=doc.pk))
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.first_name, 'دکتر')
        self.assertEqual(saved.last_name, 'مریم صالحی')

    def test_first_name_last_name_not_rendered_in_form(self):
        form = DoctorAdminForm()
        self.assertNotIn('first_name', form.fields)
        self.assertNotIn('last_name', form.fields)


class DoctorAdminChangePostTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(username='doc_change_admin', password='pass')
        self.client.force_login(self.admin)
        self.specialty = make_specialty()
        self.doc = make_doctor(full_name='دکتر حسین رستمی', specialty=self.specialty)

    def test_change_post_preserves_name_when_only_other_field_edited(self):
        url = f'/admin/contacts/doctor/{self.doc.pk}/change/'
        data = _add_post_data(self.specialty.pk, full_name='دکتر حسین رستمی')
        data['email'] = 'updated@example.com'
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.email, 'updated@example.com')
        self.assertEqual(self.doc.first_name, 'دکتر')
        self.assertEqual(self.doc.last_name, 'حسین رستمی')
