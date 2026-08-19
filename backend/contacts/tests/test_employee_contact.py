import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, GenderChoice, JobPosition

EMPLOYEES_URL = '/api/v2/contacts/employees/'
User = get_user_model()


def get_position(name='پرستار'):
    pos, _ = JobPosition.objects.get_or_create(name=name, defaults={'is_active': True})
    return pos


def make_employee(**kwargs):
    if 'job_position' not in kwargs:
        kwargs['job_position'] = get_position()
    defaults = {
        'full_name': 'مریم احمدی',
        'national_id': '0099887766',
        'gender': GenderChoice.FEMALE,
        'start_date': datetime.date(2022, 3, 1),
        'personal_phone': '09121234568',
        'emergency_contact_phone': '09129876544',
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


class EmployeeContactAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='emp_ct_user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_list_employees(self):
        make_employee()
        resp = self.client.get(EMPLOYEES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_read_only_no_post(self):
        resp = self.client.post(EMPLOYEES_URL, {'full_name': 'تست'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_search_by_name(self):
        pos = get_position()
        make_employee(full_name='احمد رضایی', national_id='1111111111', job_position=pos)
        make_employee(full_name='سارا نوری', national_id='2222222222', job_position=pos)
        resp = self.client.get(EMPLOYEES_URL, {'search': 'احمد'})
        self.assertEqual(resp.data.get('count', len(resp.data)), 1)

    def test_retrieve_includes_emergency(self):
        emp = make_employee()
        resp = self.client.get(f'{EMPLOYEES_URL}{emp.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('emergency_contact_phone', resp.data)

    def test_unauthenticated_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(EMPLOYEES_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
