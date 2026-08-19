"""Regression tests for Patient.internal_code (کد داخلی بیمار).

Covers:
  - the field is a real, optional model column, separate from case_code
  - blank/whitespace-only input normalizes to NULL (never an empty string)
  - multiple Patients may each leave it unset without colliding
  - duplicate non-blank codes are rejected with a clear Persian message,
    both via the admin form and the DRF API — never a raw IntegrityError
  - it persists correctly through the admin add/change forms
  - it appears in PatientListSerializer/PatientSerializer output
  - the Patient admin changelist search and the DRF API search both match it
  - existing Patient functionality (case_code, admin pages) is unaffected
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from surgeries.models import Patient

User = get_user_model()

PATIENTS_URL = '/api/v2/surgeries/patients/'

_ctr = [0]


def _make_patient(**kwargs):
    _ctr[0] += 1
    defaults = dict(
        full_name=f'بیمار داخلی {_ctr[0]}',
        case_code=f'PIC-{_ctr[0]:05d}',
        phone_number='09120000000',
        national_id=f'{_ctr[0]:010d}',
    )
    defaults.update(kwargs)
    return Patient.objects.create(**defaults)


class PatientInternalCodeModelTest(TestCase):

    def test_field_is_optional(self):
        patient = _make_patient(internal_code=None)
        self.assertIsNone(patient.internal_code)

    def test_field_persists_a_value(self):
        patient = _make_patient(internal_code='INT-001')
        patient.refresh_from_db()
        self.assertEqual(patient.internal_code, 'INT-001')

    def test_case_code_untouched_and_still_required_unique(self):
        _make_patient(case_code='KEEP-001')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Patient.objects.create(
                    full_name='دیگری', case_code='KEEP-001', phone_number='09121112222',
                )

    def test_clean_trims_whitespace(self):
        patient = Patient(
            full_name='بیمار', case_code='TRIM-001', phone_number='0912',
            internal_code='  ABC-1  ',
        )
        patient.clean()
        self.assertEqual(patient.internal_code, 'ABC-1')

    def test_clean_normalizes_blank_to_none(self):
        patient = Patient(
            full_name='بیمار', case_code='TRIM-002', phone_number='0912',
            internal_code='   ',
        )
        patient.clean()
        self.assertIsNone(patient.internal_code)

    def test_multiple_patients_can_each_leave_it_unset(self):
        _make_patient(internal_code=None)
        _make_patient(internal_code=None)
        _make_patient(internal_code='')
        # None of these must raise — NULL/blank never collide with each other.
        self.assertEqual(Patient.objects.filter(internal_code__isnull=True).count(), 2)

    def test_duplicate_internal_code_rejected_by_full_clean(self):
        _make_patient(internal_code='DUP-1')
        dupe = Patient(
            full_name='دیگری', case_code='DUP-CASE', phone_number='0912', internal_code='DUP-1',
        )
        with self.assertRaises(ValidationError) as ctx:
            dupe.full_clean()
        self.assertIn('کد داخلی بیمار باید یکتا باشد.', str(ctx.exception))


class PatientAdminInternalCodeTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('pic_admin', 'p@t.com', 'pass123')
        self.client.force_login(self.superuser)

    def test_add_form_persists_internal_code(self):
        resp = self.client.post('/admin/surgeries/patient/add/', {
            'full_name':      'بیمار کد داخلی',
            'case_code':      'ADMIN-IC-1',
            'internal_code':  'IC-100',
            'phone_number':   '09120001111',
            'national_id':    '6666666666',
            'age':            '30',
            'gender':         'MALE',
            'description':    '',
        })
        self.assertIn(resp.status_code, (200, 302))
        patient = Patient.objects.get(case_code='ADMIN-IC-1')
        self.assertEqual(patient.internal_code, 'IC-100')

    def test_add_form_without_internal_code_succeeds(self):
        resp = self.client.post('/admin/surgeries/patient/add/', {
            'full_name':      'بیمار بدون کد داخلی',
            'case_code':      'ADMIN-IC-2',
            'internal_code':  '',
            'phone_number':   '09120001112',
            'national_id':    '6666666667',
            'age':            '30',
            'gender':         'MALE',
            'description':    '',
        })
        self.assertIn(resp.status_code, (200, 302))
        patient = Patient.objects.get(case_code='ADMIN-IC-2')
        self.assertIsNone(patient.internal_code)

    def test_edit_form_persists_internal_code_change(self):
        patient = _make_patient(internal_code=None)
        resp = self.client.post(f'/admin/surgeries/patient/{patient.pk}/change/', {
            'full_name':      patient.full_name,
            'case_code':      patient.case_code,
            'internal_code':  'IC-EDITED',
            'phone_number':   patient.phone_number,
            'national_id':    patient.national_id,
            'age':            '30',
            'gender':         'MALE',
            'description':    '',
        })
        self.assertIn(resp.status_code, (200, 302))
        patient.refresh_from_db()
        self.assertEqual(patient.internal_code, 'IC-EDITED')

    def test_duplicate_internal_code_shows_friendly_error_not_500(self):
        _make_patient(internal_code='IC-DUP')
        resp = self.client.post('/admin/surgeries/patient/add/', {
            'full_name':      'بیمار تکراری',
            'case_code':      'ADMIN-IC-DUP',
            'internal_code':  'IC-DUP',
            'phone_number':   '09120009999',
            'national_id':    '6666699999',
            'age':            '30',
            'gender':         'MALE',
            'description':    '',
        })
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a crash
        self.assertContains(resp, 'کد داخلی بیمار باید یکتا باشد.')
        self.assertFalse(Patient.objects.filter(case_code='ADMIN-IC-DUP').exists())

    def test_two_patients_with_blank_internal_code_via_admin_both_succeed(self):
        resp1 = self.client.post('/admin/surgeries/patient/add/', {
            'full_name': 'بیمار یک', 'case_code': 'BLANK-IC-1', 'internal_code': '',
            'phone_number': '09120000001', 'national_id': '1111111111',
            'age': '30', 'gender': 'MALE', 'description': '',
        })
        resp2 = self.client.post('/admin/surgeries/patient/add/', {
            'full_name': 'بیمار دو', 'case_code': 'BLANK-IC-2', 'internal_code': '',
            'phone_number': '09120000002', 'national_id': '2222222222',
            'age': '30', 'gender': 'MALE', 'description': '',
        })
        self.assertIn(resp1.status_code, (200, 302))
        self.assertIn(resp2.status_code, (200, 302))
        self.assertTrue(Patient.objects.filter(case_code='BLANK-IC-1').exists())
        self.assertTrue(Patient.objects.filter(case_code='BLANK-IC-2').exists())

    def test_changelist_shows_internal_code_column(self):
        _make_patient(internal_code='LIST-IC-1', case_code='LIST-CASE-1')
        resp = self.client.get('/admin/surgeries/patient/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'LIST-IC-1')

    def test_changelist_search_matches_internal_code(self):
        _make_patient(internal_code='SEARCHABLE-IC', case_code='SEARCH-CASE-1')
        resp = self.client.get('/admin/surgeries/patient/', {'q': 'SEARCHABLE-IC'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'SEARCH-CASE-1')

    def test_add_form_renders_new_field(self):
        resp = self.client.get('/admin/surgeries/patient/add/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id_internal_code')
        self.assertContains(resp, 'کد داخلی بیمار')

    def test_change_form_renders_new_field(self):
        patient = _make_patient(internal_code='IC-SHOW')
        resp = self.client.get(f'/admin/surgeries/patient/{patient.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id_internal_code')
        self.assertContains(resp, 'IC-SHOW')


class PatientInternalCodeApiTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='pic_api_user', password='x')
        self.client.force_authenticate(self.user)

    def test_list_serializer_includes_internal_code(self):
        _make_patient(internal_code='API-LIST-IC')
        resp = self.client.get(PATIENTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertTrue(any(r.get('internal_code') == 'API-LIST-IC' for r in results))

    def test_create_via_api_persists_internal_code(self):
        resp = self.client.post(PATIENTS_URL, {
            'full_name': 'بیمار API', 'case_code': 'API-CREATE-1',
            'internal_code': 'API-IC-1', 'phone_number': '09120000003',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        patient = Patient.objects.get(case_code='API-CREATE-1')
        self.assertEqual(patient.internal_code, 'API-IC-1')

    def test_create_via_api_without_internal_code_succeeds(self):
        resp = self.client.post(PATIENTS_URL, {
            'full_name': 'بیمار API بدون کد', 'case_code': 'API-CREATE-2',
            'phone_number': '09120000004',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        patient = Patient.objects.get(case_code='API-CREATE-2')
        self.assertIsNone(patient.internal_code)

    def test_duplicate_internal_code_via_api_returns_400_with_persian_message(self):
        _make_patient(internal_code='API-DUP')
        resp = self.client.post(PATIENTS_URL, {
            'full_name': 'بیمار تکراری API', 'case_code': 'API-DUP-CASE',
            'internal_code': 'API-DUP', 'phone_number': '09120000005',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('کد داخلی بیمار باید یکتا باشد.', str(resp.data))
        self.assertFalse(Patient.objects.filter(case_code='API-DUP-CASE').exists())

    def test_update_via_api_persists_internal_code_change(self):
        patient = _make_patient(internal_code=None)
        resp = self.client.patch(f'{PATIENTS_URL}{patient.pk}/', {
            'internal_code': 'API-EDITED',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        patient.refresh_from_db()
        self.assertEqual(patient.internal_code, 'API-EDITED')

    def test_search_by_internal_code(self):
        _make_patient(internal_code='FINDME-IC', case_code='FINDME-CASE')
        resp = self.client.get(PATIENTS_URL, {'search': 'FINDME-IC'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertTrue(any(r.get('case_code') == 'FINDME-CASE' for r in results))

    def test_search_by_case_code_still_works(self):
        _make_patient(case_code='STILL-SEARCHABLE')
        resp = self.client.get(PATIENTS_URL, {'search': 'STILL-SEARCHABLE'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertTrue(any(r.get('case_code') == 'STILL-SEARCHABLE' for r in results))

    def test_search_by_national_id_now_works(self):
        _make_patient(national_id='9988776655', case_code='NID-SEARCH-CASE')
        resp = self.client.get(PATIENTS_URL, {'search': '9988776655'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertTrue(any(r.get('case_code') == 'NID-SEARCH-CASE' for r in results))
