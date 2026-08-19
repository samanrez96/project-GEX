"""Pagination tests for SurgeryHistoryViewSet (CLI-57).

Verifies that GET /api/v1/surgeries/history/ returns the StandardPagination
envelope (count, total_pages, page_size, results) so the JS frontend can
render page-number buttons correctly.
"""

import datetime
import math
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from surgeries.models import Patient, SurgeryHistory, SurgeryStatus, SurgeryType

User = get_user_model()
URL  = '/api/v1/surgeries/history/'

_ctr = [0]


def _surgery_type():
    _ctr[0] += 1
    return SurgeryType.objects.create(
        name=f'نوع عمل {_ctr[0]}',
        code=f'op_{_ctr[0]}',
        base_rate=Decimal('500000'),
    )


def _patient(n):
    return Patient.objects.create(
        full_name=f'بیمار {n}',
        case_code=f'C{n:05d}',
        phone_number=f'091{n:08d}',
    )


def _bulk_surgeries(n):
    st = _surgery_type()
    SurgeryHistory.objects.bulk_create([
        SurgeryHistory(
            patient=_patient(i),
            surgery_type=st,
            amount=Decimal('5000000'),
            surgery_date=datetime.datetime(2025, 1, i % 28 + 1, 10, 0,
                                           tzinfo=datetime.timezone.utc),
            status=SurgeryStatus.COMPLETED,
        )
        for i in range(n)
    ])


class SurgeryHistoryPaginationTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='sh_pag', password='x')
        self.client.force_authenticate(self.user)
        _bulk_surgeries(30)

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

    def test_filter_with_pagination(self):
        resp = self.client.get(URL, {'status': 'COMPLETED', 'page_size': '5'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(None)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
