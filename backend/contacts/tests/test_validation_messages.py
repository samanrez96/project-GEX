"""Validation message tests for contacts endpoints (CLI-60)."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from contacts.models import DoctorSpecialty

User = get_user_model()
URL  = '/api/v1/contacts/doctors/'


def _user():
    return User.objects.create_user(username=f'vm_ct_{User.objects.count()}', password='x')


class DoctorValidationTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.specialty = DoctorSpecialty.objects.create(name='جراحی')

    def test_commission_percent_above_100_rejected(self):
        resp = self.client.post(URL, {
            'full_name':                 'دکتر تستی',
            'specialty':                 self.specialty.pk,
            'phone_number':              '09100000000',
            'center_commission_percent': '150',
            'cooperation_status':        'active',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('center_commission_percent', resp.data)
        errors = str(resp.data['center_commission_percent'])
        self.assertIn('۱۰۰', errors)

    def test_commission_percent_negative_rejected(self):
        resp = self.client.post(URL, {
            'full_name':                 'دکتر تستی',
            'phone_number':              '09100000000',
            'center_commission_percent': '-5',
            'cooperation_status':        'active',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('center_commission_percent', resp.data)

    def test_valid_commission_percent_accepted(self):
        resp = self.client.post(URL, {
            'full_name':                 'دکتر معتبر',
            'specialty':                 self.specialty.pk,
            'phone_number':              '09100000001',
            'center_commission_percent': '30',
            'cooperation_status':        'active',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
