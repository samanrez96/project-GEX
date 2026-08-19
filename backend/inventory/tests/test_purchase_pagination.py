"""Pagination tests for PurchaseViewSet (CLI-57).

Verifies that GET /api/v1/inventory/purchases/ returns the StandardPagination
envelope (count, total_pages, page_size, results) so the JS frontend can
render page-number buttons correctly.
"""

import math

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import Purchase, PurchaseStatus, Vendor

User = get_user_model()
URL  = '/api/v1/inventory/purchases/'


def _vendor(name='TestVendor'):
    return Vendor.objects.create(name=name)


def _bulk_purchases(vendor, n):
    Purchase.objects.bulk_create([
        Purchase(vendor=vendor, status=PurchaseStatus.PENDING)
        for _ in range(n)
    ])


class PurchasePaginationTest(APITestCase):

    def setUp(self):
        self.user   = User.objects.create_user(username='pu_pag', password='x')
        self.client.force_authenticate(self.user)
        self.vendor = _vendor()
        _bulk_purchases(self.vendor, 30)

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
        v2 = _vendor('UniqueVendorXYZ')
        Purchase.objects.create(vendor=v2, status=PurchaseStatus.CONFIRMED)
        resp = self.client.get(URL, {'search': 'UniqueVendorXYZ', 'page_size': '10'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['total_pages'], 1)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(None)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
