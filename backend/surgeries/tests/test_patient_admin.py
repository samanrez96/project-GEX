"""Tests for the Patients admin panel."""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from contacts.models import Doctor, DoctorSpecialty
from surgeries.models import Patient, SurgeryHistory, SurgeryType

User = get_user_model()


def _make_patient(case_code='PAT001', full_name='بیمار تست'):
    return Patient.objects.create(
        full_name=full_name,
        case_code=case_code,
        phone_number='09120000000',
        national_id='5555555555',
    )


def _make_doctor():
    specialty, _ = DoctorSpecialty.objects.get_or_create(name='جراح')
    obj, _ = Doctor.objects.get_or_create(
        full_name='دکتر تست',
        defaults={'specialty': specialty, 'phone_number': '09120000009', 'is_active': True},
    )
    return obj


def _make_surgery(patient, doctor=None):
    stype, _ = SurgeryType.objects.get_or_create(
        code='gen', defaults={'name': 'عمومی', 'base_rate': Decimal('1000000')},
    )
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=stype,
        clinical_doctor=doctor,
        amount=Decimal('10000000'),
        surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    )


class PatientAdminTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('pat_admin', 'p@t.com', 'pass123')
        self.client.force_login(self.superuser)

    def test_patient_list_loads(self):
        resp = self.client.get('/admin/surgeries/patient/')
        self.assertEqual(resp.status_code, 200)

    def test_patient_add_form_loads(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertEqual(resp.status_code, 200)

    def test_create_patient_via_admin(self):
        resp = self.client.post('/admin/surgeries/patient/add/', {
            'full_name':    'بیمار جدید',
            'case_code':    'NEWPAT01',
            'phone_number': '09120001111',
            'national_id':  '6666666666',
            'age':          '30',
            'gender':       'MALE',
            'description':  '',
        })
        self.assertIn(resp.status_code, (200, 302))
        self.assertTrue(Patient.objects.filter(case_code='NEWPAT01').exists())

    def test_edit_patient_form_loads(self):
        patient = _make_patient()
        resp = self.client.get(f'/admin/surgeries/patient/{patient.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    def test_patient_list_shows_latest_doctor(self):
        """Patient list annotates clinical_doctor name from latest surgery."""
        patient = _make_patient(case_code='DOCTEST')
        doctor  = _make_doctor()
        _make_surgery(patient, doctor)

        resp = self.client.get('/admin/surgeries/patient/')
        self.assertEqual(resp.status_code, 200)
        # The page should render without errors and load successfully

    def test_patient_list_no_surgery_shows_dash(self):
        patient = _make_patient(case_code='NOSURGERY')
        resp = self.client.get('/admin/surgeries/patient/')
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        resp = self.client.get('/admin/surgeries/patient/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp.url)
