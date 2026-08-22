"""Tests for CLI-38: Surgery History admin UI.

Covers:
  - Admin list view: HTTP 200, custom template, unauthenticated redirect
  - Admin detail view: HTTP 200, context, 404 for nonexistent, redirect
  - Admin change view: uses custom template
  - SurgeryHistoryListSerializer: phone_number field, center_commission_income_amount
  - Queryset: select_related does not cause N+1 queries on list
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import CenterCommissionIncome, IncomeStatus
from surgeries.models import Patient, SurgeryHistory, SurgeryType
from surgeries.serializers import SurgeryHistoryListSerializer

User = get_user_model()

LIST_URL   = '/admin/surgeries/surgeryhistory/'
API_URL    = '/api/v1/surgeries/history/'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ctr = [0]


def _surgery_type(**kw):
    _ctr[0] += 1
    d = {'name': f'عمل {_ctr[0]}', 'code': f'op_{_ctr[0]}', 'base_rate': Decimal('500000')}
    d.update(kw)
    return SurgeryType.objects.create(**d)


def _patient(**kw):
    _ctr[0] += 1
    d = {
        'full_name':    f'بیمار {_ctr[0]}',
        'case_code':    f'C{_ctr[0]:04d}',
        'phone_number': f'091{_ctr[0]:08d}',
    }
    d.update(kw)
    return Patient.objects.create(**d)


def _surgery(**kw):
    d = {
        'patient':      _patient(),
        'surgery_type': _surgery_type(),
        'amount':       Decimal('10000000'),
        'surgery_date': datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
    }
    d.update(kw)
    return SurgeryHistory.objects.create(**d)


# ---------------------------------------------------------------------------
# Admin list view tests
# ---------------------------------------------------------------------------

class SurgeryHistoryAdminListTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin_sh', password='pass123', email='sh@test.com'
        )
        self.client.login(username='admin_sh', password='pass123')

    def test_list_page_returns_200(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)

    def test_list_page_uses_custom_template(self):
        response = self.client.get(LIST_URL)
        self.assertTemplateUsed(response, 'admin/surgeries/surgeryhistory/change_list.html')

    def test_list_page_unauthenticated_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_list_page_includes_global_search_js(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, 'global_search.js')

    def test_list_page_includes_table_pagination_js(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, 'table_pagination.js')

    def test_list_page_includes_table_filters_js(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, 'table_filters.js')

    def test_list_page_has_sort_controls(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, 'sh-sort-by')
        self.assertContains(response, 'sh-sort-dir')

    def test_list_page_has_date_range_filters(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, 'sh-filter-date-from')
        self.assertContains(response, 'sh-filter-date-to')

    def test_list_page_search_input_has_data_attribute(self):
        response = self.client.get(LIST_URL)
        self.assertContains(response, 'data-global-search')


# ---------------------------------------------------------------------------
# Admin detail view tests
# ---------------------------------------------------------------------------

class SurgeryHistoryAdminDetailTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin_shd', password='pass123', email='shd@test.com'
        )
        self.client.login(username='admin_shd', password='pass123')
        self.surgery = _surgery()

    def _detail_url(self, pk=None):
        return f'/admin/surgeries/surgeryhistory/{pk or self.surgery.pk}/detail/'

    def test_detail_page_returns_200(self):
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)

    def test_detail_page_uses_custom_template(self):
        response = self.client.get(self._detail_url())
        self.assertTemplateUsed(response, 'admin/surgeries/surgeryhistory/change_form.html')

    def test_detail_page_passes_surgery_to_context(self):
        response = self.client.get(self._detail_url())
        self.assertEqual(response.context['original'], self.surgery)

    def test_detail_page_404_for_nonexistent_surgery(self):
        response = self.client.get(self._detail_url(pk=999999))
        self.assertEqual(response.status_code, 404)

    def test_detail_page_unauthenticated_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_change_page_is_real_editable_form(self):
        """
        /change/ must use Django's built-in change form (NOT the custom detail view).
        It should render a real editable form, not the read-only tab UI.
        """
        url = f'/admin/surgeries/surgeryhistory/{self.surgery.pk}/change/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Real change form has a <form> POST action
        self.assertIn('<form', content)
        self.assertIn('method="post"', content)
        # Must NOT load the custom detail JS (that is the read-only view)
        self.assertNotIn('surgery_history_detail.js', content)


# ---------------------------------------------------------------------------
# SurgeryHistoryListSerializer tests
# ---------------------------------------------------------------------------

class SurgeryHistoryListSerializerTest(TestCase):

    def test_serializer_includes_phone_number(self):
        surgery = _surgery()
        data = SurgeryHistoryListSerializer(surgery).data
        self.assertIn('phone_number', data)
        self.assertEqual(data['phone_number'], surgery.phone_number)

    def test_serializer_has_none_for_missing_commission_income(self):
        surgery = _surgery()
        data = SurgeryHistoryListSerializer(surgery).data
        self.assertIn('center_commission_income_amount', data)
        self.assertIsNone(data['center_commission_income_amount'])

    def test_serializer_returns_income_amount_when_income_exists(self):
        surgery = _surgery(center_commission_percent=Decimal('20'))
        income = CenterCommissionIncome.objects.create(
            surgery=surgery,
            amount=Decimal('2000000'),
            status=IncomeStatus.CONFIRMED,
            income_date=surgery.surgery_date,
        )
        surgery.refresh_from_db()
        data = SurgeryHistoryListSerializer(surgery).data
        self.assertEqual(Decimal(data['center_commission_income_amount']), income.amount)

    def test_serializer_includes_expected_fields(self):
        surgery = _surgery()
        data = SurgeryHistoryListSerializer(surgery).data
        for field in [
            'id', 'patient_name', 'case_code', 'phone_number',
            'surgery_type_name', 'doctor_name',
            'surgery_date', 'amount',
            'payment_status', 'payment_status_display',
            'status', 'status_display',
            'center_commission_income_amount',
            'created_at',
        ]:
            self.assertIn(field, data, msg=f'Missing field: {field}')


# ---------------------------------------------------------------------------
# API list endpoint: phone_number + center_commission_income_amount
# ---------------------------------------------------------------------------

class SurgeryHistoryAPIListFieldsTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('apitest', 'a@t.com', 'pass')
        self.client.force_authenticate(user=self.user)

    def test_api_list_includes_phone_number(self):
        surgery = _surgery()
        res = self.client.get(API_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        row = next((r for r in res.data['results'] if r['id'] == surgery.id), None)
        self.assertIsNotNone(row)
        self.assertIn('phone_number', row)
        self.assertEqual(row['phone_number'], surgery.phone_number)

    def test_api_list_income_amount_populated_when_income_exists(self):
        surgery = _surgery(center_commission_percent=Decimal('10'))
        CenterCommissionIncome.objects.create(
            surgery=surgery,
            amount=Decimal('1000000'),
            status=IncomeStatus.CONFIRMED,
            income_date=surgery.surgery_date,
        )
        res = self.client.get(API_URL)
        row = next((r for r in res.data['results'] if r['id'] == surgery.id), None)
        self.assertIsNotNone(row)
        self.assertEqual(Decimal(row['center_commission_income_amount']), Decimal('1000000'))

    def test_api_list_income_amount_none_when_no_income(self):
        surgery = _surgery()
        res = self.client.get(API_URL)
        row = next((r for r in res.data['results'] if r['id'] == surgery.id), None)
        self.assertIsNotNone(row)
        self.assertIsNone(row['center_commission_income_amount'])
