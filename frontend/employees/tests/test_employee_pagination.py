"""Pagination tests for EmployeeViewSet (CLI-57).

Verifies that GET /api/v1/employees/ returns the StandardPagination
envelope (count, total_pages, page_size, results) so the JS frontend can
render page-number buttons correctly.
"""

import datetime
import math
import random

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, JobPosition

User = get_user_model()
URL  = '/api/v1/employees/'


def _position():
    return JobPosition.objects.create(name=f'Pos_{random.randint(10000, 99999)}')


def _bulk_employees(position, n):
    Employee.objects.bulk_create([
        Employee(
            full_name=f'کارمند {i}',
            national_id=str(random.randint(1_000_000_000, 9_999_999_999)),
            gender='female',
            job_position=position,
            start_date=datetime.date(2022, 1, 1),
            personal_phone='09100000000',
            emergency_contact_phone='09200000000',
        )
        for i in range(n)
    ])


class EmployeePaginationTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='em_pag', password='x')
        self.client.force_authenticate(self.user)
        self.pos  = _position()
        _bulk_employees(self.pos, 30)

    def test_response_includes_pagination_envelope(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for field in ('count', 'total_pages', 'page_size', 'results', 'next', 'previous'):
            self.assertIn(field, resp.data, msg=f'Missing field: {field}')

    def test_default_page_size_is_25(self):
        resp = self.client.get(URL)
        self.assertLessEqual(len(resp.data['results']), 25)
        self.assertEqual(resp.data['page_size'], 25)

    def test_page_size_query_param(self):
        resp = self.client.get(URL, {'page_size': '5'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(resp.data['results']), 5)
        self.assertEqual(resp.data['page_size'], 5)

    def test_max_page_size_enforced(self):
        resp = self.client.get(URL, {'page_size': '999'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertLessEqual(resp.data['page_size'], 100)

    def test_total_pages_matches_count(self):
        resp = self.client.get(URL, {'page_size': '10'})
        expected = math.ceil(resp.data['count'] / 10)
        self.assertEqual(resp.data['total_pages'], expected)

    def test_second_page_works(self):
        resp = self.client.get(URL, {'page': '2', 'page_size': '10'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    def test_search_with_pagination(self):
        pos2 = _position()
        Employee.objects.create(
            full_name='UniqueSearchName',
            national_id='1234567890',
            gender='male',
            job_position=pos2,
            start_date=datetime.date(2022, 1, 1),
            personal_phone='09100000001',
            emergency_contact_phone='09200000001',
        )
        resp = self.client.get(URL, {'search': 'UniqueSearchName', 'page_size': '10'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['total_pages'], 1)

    def test_filter_with_pagination(self):
        resp = self.client.get(URL, {'is_active': 'true', 'page_size': '5'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(None)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
