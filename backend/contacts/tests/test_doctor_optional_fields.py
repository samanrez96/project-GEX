"""Targeted tests: Doctor add/edit must be creatable with minimal data.

national_id, medical_system_number, specialty, phone_number, clinic_phone,
email, address, dates, documents, notes, and commission/rate fields are all
optional. Only full_name remains required (the identity field).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from contacts.models import Doctor, DoctorSpecialty

ADD_URL = '/admin/contacts/doctor/add/'
API_URL = '/api/v2/contacts/doctors/'
User = get_user_model()


class DoctorMinimalAdminFormTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='doc_min_admin', password='pass123')
        self.client.login(username='doc_min_admin', password='pass123')

    def _minimal_post_data(self, **overrides):
        data = {
            'full_name': 'دکتر حداقلی',
            'specialty': '',
            'phone_number': '',
            'national_id': '',
            'medical_system_number': '',
            'clinic_phone': '',
            'email': '',
            'address': '',
            'collaboration_start_date': '',
            'license_last_renewal_date': '',
            'rate_per_surgery': '',
            'center_commission_percent': '',
            'cooperation_status': 'active',
            'notes': '',
            'surgery_rates-TOTAL_FORMS': '0',
            'surgery_rates-INITIAL_FORMS': '0',
            'surgery_rates-MIN_NUM_FORMS': '0',
            'surgery_rates-MAX_NUM_FORMS': '1000',
        }
        data.update(overrides)
        return data

    def test_doctor_saved_with_only_full_name(self):
        response = self.client.post(ADD_URL, self._minimal_post_data())
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        doctor = Doctor.objects.get(full_name='دکتر حداقلی')
        self.assertIsNone(doctor.specialty_id)
        self.assertEqual(doctor.phone_number, '')
        self.assertEqual(doctor.national_id, '')

    def test_full_name_still_required(self):
        response = self.client.post(ADD_URL, self._minimal_post_data(full_name=''))
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        self.assertContains(response, 'این مقدار لازم است.')

    def test_doctor_with_specialty_still_works(self):
        specialty = DoctorSpecialty.objects.create(name='تخصص کامل')
        response = self.client.post(ADD_URL, self._minimal_post_data(
            full_name='دکتر کامل', specialty=str(specialty.pk), phone_number='09120000000',
        ))
        self.assertEqual(response.status_code, 302)
        doctor = Doctor.objects.get(full_name='دکتر کامل')
        self.assertEqual(doctor.specialty_id, specialty.pk)


class DoctorMinimalApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='doc_min_api', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_create_doctor_via_api_with_only_full_name(self):
        resp = self.client.post(API_URL, {'full_name': 'دکتر ای‌پی‌آی حداقلی'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(resp.data.get('specialty'))

    def test_full_name_required_via_api(self):
        resp = self.client.post(API_URL, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('full_name', resp.data)
