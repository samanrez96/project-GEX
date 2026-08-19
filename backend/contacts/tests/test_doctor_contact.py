from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from contacts.models import CooperationStatus, Doctor, DoctorSpecialty

DOCTORS_URL = '/api/v2/contacts/doctors/'
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


class DoctorModelTest(TestCase):

    def test_create(self):
        doc = make_doctor()
        self.assertIsNotNone(doc.pk)
        self.assertTrue(doc.is_active)
        self.assertEqual(doc.cooperation_status, CooperationStatus.ACTIVE)

    def test_str(self):
        doc = make_doctor()
        self.assertIn('دکتر علی محمدی', str(doc))
        self.assertIn('جراحی عمومی', str(doc))

    def test_defaults(self):
        doc = make_doctor()
        self.assertEqual(doc.notes, '')
        self.assertEqual(doc.email, '')
        self.assertIsNone(doc.center_commission_percent)

    def test_commission_over_100_raises(self):
        doc = make_doctor(center_commission_percent=Decimal('101'))
        with self.assertRaises(ValidationError):
            doc.clean()

    def test_commission_negative_raises(self):
        doc = make_doctor(center_commission_percent=Decimal('-1'))
        with self.assertRaises(ValidationError):
            doc.clean()

    def test_valid_commission(self):
        doc = make_doctor(center_commission_percent=Decimal('15.50'))
        doc.clean()

    def test_timestamps_set(self):
        doc = make_doctor()
        self.assertIsNotNone(doc.created_at)
        self.assertIsNotNone(doc.updated_at)


class DoctorAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='ct_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_list_empty(self):
        resp = self.client.get(DOCTORS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create(self):
        specialty = make_specialty('قلب و عروق')
        payload = {'full_name': 'دکتر سارا احمدی', 'specialty': specialty.pk, 'phone_number': '09351112233'}
        resp = self.client.post(DOCTORS_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_list_count(self):
        make_doctor()
        make_doctor(full_name='دکتر رضا', specialty='اورولوژی', phone_number='09120000001')
        resp = self.client.get(DOCTORS_URL)
        self.assertEqual(resp.data.get('count', len(resp.data)), 2)

    def test_search_by_name(self):
        make_doctor(full_name='دکتر علی کریمی', specialty='ارتوپدی', phone_number='09121111111')
        make_doctor(full_name='دکتر رضا نوری', specialty='اورولوژی', phone_number='09122222222')
        resp = self.client.get(DOCTORS_URL, {'search': 'علی'})
        self.assertEqual(resp.data.get('count', len(resp.data)), 1)

    def test_search_by_specialty(self):
        make_doctor(full_name='دکتر ۱', specialty='ارتوپدی', phone_number='09121111111')
        make_doctor(full_name='دکتر ۲', specialty='اورولوژی', phone_number='09122222222')
        resp = self.client.get(DOCTORS_URL, {'search': 'ارتوپدی'})
        self.assertEqual(resp.data.get('count', len(resp.data)), 1)

    def test_filter_cooperation_status(self):
        make_doctor(phone_number='09121111111', cooperation_status=CooperationStatus.ACTIVE)
        make_doctor(phone_number='09122222222', cooperation_status=CooperationStatus.INACTIVE)
        resp = self.client.get(DOCTORS_URL, {'cooperation_status': 'inactive'})
        self.assertEqual(resp.data.get('count', len(resp.data)), 1)

    def test_retrieve(self):
        doc = make_doctor()
        resp = self.client.get(f'{DOCTORS_URL}{doc.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('address', resp.data)

    def test_update(self):
        doc = make_doctor()
        specialty = make_specialty('ارتوپدی')
        resp = self.client.patch(f'{DOCTORS_URL}{doc.pk}/', {'specialty': specialty.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_delete(self):
        doc = make_doctor()
        resp = self.client.delete(f'{DOCTORS_URL}{doc.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_unauthenticated_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(DOCTORS_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
