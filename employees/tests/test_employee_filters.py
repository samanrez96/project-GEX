"""Filter and sort tests for EmployeeViewSet (CLI-58)."""

import datetime
import random

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, JobPosition

User = get_user_model()
URL  = '/api/v1/employees/'


def _user():
    return User.objects.create_user(username=f'ef_{User.objects.count()}', password='x')


def _position(name=None):
    return JobPosition.objects.create(name=name or f'Pos_{random.randint(10000, 99999)}')


def _employee(name, position, is_active=True, start_date=None):
    return Employee.objects.create(
        full_name=name,
        national_id=str(random.randint(1_000_000_000, 9_999_999_999)),
        gender='female',
        job_position=position,
        start_date=start_date or datetime.date(2023, 1, 1),
        personal_phone='09100000000',
        emergency_contact_phone='09200000000',
        is_active=is_active,
    )


class EmployeeFilterTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.pos1 = _position()
        self.pos2 = _position()

    # ── Filter by job_position ────────────────────────────────────

    def test_filter_by_position(self):
        e1 = _employee('علی رضایی',   self.pos1)
        e2 = _employee('مریم احمدی',  self.pos2)
        resp = self.client.get(URL, {'job_position': self.pos1.id})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(e1.id, ids)
        self.assertNotIn(e2.id, ids)

    # ── Filter by is_active ───────────────────────────────────────

    def test_filter_active_true(self):
        e_active   = _employee('فعال', self.pos1, is_active=True)
        e_inactive = _employee('غیرفعال', self.pos1, is_active=False)
        resp = self.client.get(URL, {'is_active': 'true'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(e_active.id, ids)
        self.assertNotIn(e_inactive.id, ids)

    def test_filter_active_false(self):
        e_active   = _employee('فعال2', self.pos1, is_active=True)
        e_inactive = _employee('غیرفعال2', self.pos1, is_active=False)
        resp = self.client.get(URL, {'is_active': 'false'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(e_inactive.id, ids)
        self.assertNotIn(e_active.id, ids)

    # ── Filter by start_date range ────────────────────────────────

    def test_filter_start_date_from(self):
        e_old  = _employee('قدیمی',  self.pos1, start_date=datetime.date(2019, 1, 1))
        e_new  = _employee('جدید',   self.pos1, start_date=datetime.date(2023, 6, 1))
        resp = self.client.get(URL, {'start_date_from': '2022-01-01'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(e_new.id, ids)
        self.assertNotIn(e_old.id, ids)

    def test_filter_start_date_to(self):
        e_old = _employee('قدیمی2', self.pos1, start_date=datetime.date(2018, 3, 1))
        e_new = _employee('جدید2',  self.pos1, start_date=datetime.date(2024, 1, 1))
        resp = self.client.get(URL, {'start_date_to': '2020-01-01'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(e_old.id, ids)
        self.assertNotIn(e_new.id, ids)

    def test_filter_start_date_range(self):
        e1 = _employee('ابتدای دوره', self.pos1, start_date=datetime.date(2021, 1, 1))
        e2 = _employee('خارج از دوره', self.pos1, start_date=datetime.date(2015, 5, 1))
        resp = self.client.get(URL, {
            'start_date_from': '2020-01-01',
            'start_date_to':   '2022-12-31',
        })
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(e1.id, ids)
        self.assertNotIn(e2.id, ids)

    # ── Sorting ───────────────────────────────────────────────────

    def test_sort_by_full_name(self):
        _employee('الف', self.pos1)
        _employee('ب',   self.pos1)
        resp = self.client.get(URL, {'ordering': 'full_name'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_sort_by_start_date_desc(self):
        _employee('قدیمی3', self.pos1, start_date=datetime.date(2019, 1, 1))
        _employee('جدید3',  self.pos1, start_date=datetime.date(2024, 1, 1))
        resp = self.client.get(URL, {'ordering': '-start_date'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_sort_by_position_name(self):
        resp = self.client.get(URL, {'ordering': 'job_position__name'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_invalid_ordering_is_ignored_safely(self):
        resp = self.client.get(URL, {'ordering': 'password_hash'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    # ── Combined ──────────────────────────────────────────────────

    def test_position_filter_and_sort_together(self):
        _employee('زینب',  self.pos1, start_date=datetime.date(2023, 3, 1))
        _employee('یاسمن', self.pos1, start_date=datetime.date(2022, 3, 1))
        _employee('رضا',   self.pos2)
        resp = self.client.get(URL, {
            'job_position': self.pos1.id, 'ordering': 'full_name',
        })
        self.assertEqual(resp.status_code, 200)
        for r in resp.data['results']:
            self.assertEqual(r['job_position'], self.pos1.id)
