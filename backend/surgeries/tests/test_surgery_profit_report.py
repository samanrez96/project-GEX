"""Tests for the Surgery Profit Report API (CLI-53).

GET /api/v1/surgeries/reports/profit/
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import Group, User
from rest_framework import status
from rest_framework.test import APITestCase

from finance.models import CenterCommissionIncome, IncomeStatus
from inventory.models import Product, ProductType
from surgeries.models import (
    Patient,
    PaymentStatus,
    SurgeryHistory,
    SurgeryStatus,
    SurgeryType,
    SurgeryUsedItem,
)

URL = '/api/v1/surgeries/reports/profit/'

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

_emp_counter = 0


def _user(username, role=None, is_superuser=False):
    u = User.objects.create_user(username=username, password='pass')
    if is_superuser:
        u.is_superuser = True
        u.save()
    elif role:
        g, _ = Group.objects.get_or_create(name=role)
        u.groups.add(g)
    return u


def _surgery_type(name=None, code=None):
    import random
    uid = random.randint(100000, 999999)
    return SurgeryType.objects.create(
        name=name or f'عمل_{uid}',
        code=code or f'op_{uid}',
        base_rate=Decimal('1000000'),
    )


def _patient(name=None, case_code=None):
    import random
    uid = random.randint(100000, 999999)
    return Patient.objects.create(
        full_name=name or f'بیمار_{uid}',
        case_code=case_code or f'P-{uid}',
        phone_number='09000000000',
    )


def _product(name=None, purchase_price=Decimal('50000')):
    import random
    uid = random.randint(100000, 999999)
    return Product.objects.create(
        name=name or f'محصول_{uid}',
        internal_code=f'PROD-{uid}',
        product_type=ProductType.MEDICINE,
        unit='عدد',
        purchase_price=purchase_price,
    )


def _doctor(name=None):
    from employees.models import Employee, JobPosition
    import random
    uid = random.randint(100000, 999999)
    pos, _ = JobPosition.objects.get_or_create(name=f'پزشک_{uid}')
    return Employee.objects.create(
        full_name=name or f'دکتر_{uid}',
        national_id=str(uid),
        gender='male',
        job_position=pos,
        start_date=datetime.date(2020, 1, 1),
        personal_phone='09000000000',
        emergency_contact_phone='09111111111',
    )


def _surgery(
    patient, surgery_type, doctor=None,
    amount=Decimal('5000000'),
    surgery_date=None,
    surgery_status=SurgeryStatus.COMPLETED,
    payment_status=PaymentStatus.PAID,
    center_commission_amount=None,
    center_commission_percent=None,
):
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        doctor_or_therapist=doctor,
        amount=amount,
        surgery_date=surgery_date or datetime.datetime(2025, 6, 1, 10, 0),
        status=surgery_status,
        payment_status=payment_status,
        center_commission_amount=center_commission_amount,
        center_commission_percent=center_commission_percent,
    )


def _income(surgery, amount, income_status=IncomeStatus.CONFIRMED):
    return CenterCommissionIncome.objects.create(
        surgery=surgery,
        amount=amount,
        status=income_status,
        income_date=surgery.surgery_date,
    )


def _used_item(surgery, product, quantity=Decimal('2')):
    return SurgeryUsedItem.objects.create(
        surgery=surgery,
        product=product,
        quantity=quantity,
    )


def _commission_transaction(surgery, doctor, amount):
    from payroll.models import CommissionRule, CommissionTransaction
    from employees.models import JobPosition
    rule, _ = CommissionRule.objects.get_or_create(
        job_position=doctor.job_position,
        surgery_type=surgery.surgery_type,
        defaults={'commission_percent': Decimal('10')},
    )
    return CommissionTransaction.objects.create(
        surgery=surgery, employee=doctor, commission_rule=rule, amount=amount,
    )


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class SurgeryProfitReportPermissionsTest(APITestCase):

    def test_superuser_can_access(self):
        user = _user('su_user', is_superuser=True)
        self.client.force_authenticate(user)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_admin_role_can_access(self):
        user = _user('admin_user', role='admin')
        self.client.force_authenticate(user)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_finance_role_can_access(self):
        user = _user('fin_user', role='finance_user')
        self.client.force_authenticate(user)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_inventory_only_role_gets_403(self):
        user = _user('inv_user', role='inventory_user')
        self.client.force_authenticate(user)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_gets_401(self):
        r = self.client.get(URL)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class SurgeryProfitReportValidationTest(APITestCase):

    def setUp(self):
        self.user = _user('val_admin', role='admin')
        self.client.force_authenticate(self.user)

    def test_invalid_date_format_returns_400(self):
        r = self.client.get(URL, {'start_date': 'not-a-date'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reversed_date_range_returns_400(self):
        r = self.client.get(URL, {'start_date': '2025-12-31', 'end_date': '2025-01-01'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_group_by_returns_400(self):
        r = self.client.get(URL, {'group_by': 'invalid_mode'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_surgery_type_id_format_returns_400(self):
        r = self.client.get(URL, {'surgery_type_id': 'abc'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_surgery_type_id_returns_400(self):
        r = self.client.get(URL, {'surgery_type_id': '999999'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_status_returns_400(self):
        r = self.client.get(URL, {'status': 'INVALID_STATUS'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_payment_status_returns_400(self):
        r = self.client.get(URL, {'payment_status': 'INVALID'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_min_profit_returns_400(self):
        r = self.client.get(URL, {'min_profit': 'not-a-number'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_patient_id_returns_400(self):
        r = self.client.get(URL, {'patient_id': '999999'})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# group_by=surgery calculations
# ---------------------------------------------------------------------------

class SurgeryProfitReportBySurgeryTest(APITestCase):

    def setUp(self):
        self.user = _user('surg_admin', role='admin')
        self.client.force_authenticate(self.user)

        self.st   = _surgery_type()
        self.pat  = _patient()
        self.doc  = _doctor()
        self.prod = _product(purchase_price=Decimal('100000'))

        # Surgery with income=2_000_000, item cost=200_000, commission=150_000
        self.surg = _surgery(self.pat, self.st, doctor=self.doc, amount=Decimal('5000000'))
        _income(self.surg, Decimal('2000000'))
        _used_item(self.surg, self.prod, quantity=Decimal('2'))   # cost = 2×100_000 = 200_000
        _commission_transaction(self.surg, self.doc, Decimal('150000'))

    def _get(self, **params):
        return self.client.get(URL, {'group_by': 'surgery', **params})

    def test_correct_center_income(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        row = r.data['results'][0]
        self.assertEqual(Decimal(row['center_income']), Decimal('2000000'))

    def test_correct_consumed_items_cost(self):
        r = self._get()
        row = r.data['results'][0]
        self.assertEqual(Decimal(row['consumed_items_cost']), Decimal('200000'))

    def test_correct_employee_commission_cost(self):
        r = self._get()
        row = r.data['results'][0]
        self.assertEqual(Decimal(row['employee_commission_cost']), Decimal('150000'))

    def test_correct_approximate_profit(self):
        r = self._get()
        row = r.data['results'][0]
        # 2_000_000 - 200_000 - 150_000 = 1_650_000
        self.assertEqual(Decimal(row['approximate_profit']), Decimal('1650000'))

    def test_correct_profit_margin_percent(self):
        r = self._get()
        row = r.data['results'][0]
        # 1_650_000 / 2_000_000 × 100 = 82.50
        self.assertEqual(Decimal(row['profit_margin_percent']), Decimal('82.50'))

    def test_surgery_with_no_income_has_zero_center_income(self):
        pat2  = _patient()
        surg2 = _surgery(pat2, self.st, amount=Decimal('3000000'))
        # No CenterCommissionIncome created
        r = self._get()
        rows = {row['surgery_id']: row for row in r.data['results']}
        self.assertEqual(Decimal(rows[surg2.id]['center_income']), Decimal('0'))

    def test_surgery_with_no_used_items_has_zero_cost(self):
        pat2  = _patient()
        surg2 = _surgery(pat2, self.st, amount=Decimal('3000000'))
        _income(surg2, Decimal('1000000'))
        # No SurgeryUsedItem created
        r = self._get()
        rows = {row['surgery_id']: row for row in r.data['results']}
        self.assertEqual(Decimal(rows[surg2.id]['consumed_items_cost']), Decimal('0'))

    def test_surgery_with_no_commission_has_zero_commission_cost(self):
        pat2  = _patient()
        surg2 = _surgery(pat2, self.st, amount=Decimal('3000000'))
        _income(surg2, Decimal('1000000'))
        # No CommissionTransaction created
        r = self._get()
        rows = {row['surgery_id']: row for row in r.data['results']}
        self.assertEqual(Decimal(rows[surg2.id]['employee_commission_cost']), Decimal('0'))

    def test_rows_sorted_by_profit_desc(self):
        pat2  = _patient()
        surg2 = _surgery(pat2, self.st, amount=Decimal('3000000'))
        _income(surg2, Decimal('500000'))   # profit = 500_000

        # surg has profit 1_650_000, surg2 has profit 500_000
        r = self._get()
        profits = [Decimal(row['approximate_profit']) for row in r.data['results']]
        self.assertEqual(profits, sorted(profits, reverse=True))
        self.assertEqual(profits[0], Decimal('1650000'))

    def test_correct_surgery_fields_in_row(self):
        r = self._get()
        row = r.data['results'][0]
        self.assertEqual(row['surgery_id'], self.surg.id)
        self.assertEqual(row['patient_name'], self.pat.full_name)
        self.assertEqual(row['surgery_type_name'], self.st.name)
        self.assertEqual(row['doctor_name'], self.doc.full_name)

    def test_surgery_without_doctor_has_null_doctor_name(self):
        pat2  = _patient()
        surg2 = _surgery(pat2, self.st, doctor=None, amount=Decimal('2000000'))
        _income(surg2, Decimal('1000000'))
        r = self._get()
        rows = {row['surgery_id']: row for row in r.data['results']}
        self.assertIsNone(rows[surg2.id]['doctor_name'])

    def test_empty_result_returns_200_with_zero_metadata(self):
        r = self._get(start_date='2000-01-01', end_date='2000-01-02')
        self.assertEqual(r.status_code, 200)
        meta = r.data['metadata']
        self.assertEqual(meta['total_surgeries'], 0)
        self.assertEqual(Decimal(meta['total_approximate_profit']), Decimal('0'))
        self.assertIsNone(meta['average_profit_per_surgery'])
        self.assertEqual(r.data['results'], [])

    def test_metadata_grand_totals(self):
        r = self._get()
        meta = r.data['metadata']
        self.assertEqual(meta['total_surgeries'], r.data['count'])
        self.assertIsNotNone(meta['average_profit_per_surgery'])

    def test_cancelled_income_not_counted(self):
        pat2  = _patient()
        surg2 = _surgery(pat2, self.st, amount=Decimal('3000000'))
        # CANCELLED income should not count
        _income(surg2, Decimal('999999'), income_status=IncomeStatus.CANCELLED)
        r = self._get()
        rows = {row['surgery_id']: row for row in r.data['results']}
        self.assertEqual(Decimal(rows[surg2.id]['center_income']), Decimal('0'))


# ---------------------------------------------------------------------------
# group_by=surgery_type
# ---------------------------------------------------------------------------

class SurgeryProfitReportBySurgeryTypeTest(APITestCase):

    def setUp(self):
        self.user = _user('st_admin', role='admin')
        self.client.force_authenticate(self.user)

        self.st1 = _surgery_type(name='نوع عمل الف')
        self.st2 = _surgery_type(name='نوع عمل ب')
        pat1, pat2, pat3 = _patient(), _patient(), _patient()
        prod = _product(purchase_price=Decimal('50000'))

        # st1: two surgeries
        s1 = _surgery(pat1, self.st1, amount=Decimal('4000000'))
        _income(s1, Decimal('1000000'))
        _used_item(s1, prod, Decimal('2'))   # cost = 100_000

        s2 = _surgery(pat2, self.st1, amount=Decimal('3000000'))
        _income(s2, Decimal('600000'))
        _used_item(s2, prod, Decimal('1'))   # cost = 50_000

        # st2: one surgery
        s3 = _surgery(pat3, self.st2, amount=Decimal('2000000'))
        _income(s3, Decimal('400000'))

    def _get(self, **params):
        return self.client.get(URL, {'group_by': 'surgery_type', **params})

    def test_groups_by_surgery_type(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        type_ids = {row['surgery_type_id'] for row in r.data['results']}
        self.assertIn(self.st1.id, type_ids)
        self.assertIn(self.st2.id, type_ids)

    def test_correct_surgeries_count_per_type(self):
        r = self._get()
        rows = {row['surgery_type_id']: row for row in r.data['results']}
        self.assertEqual(rows[self.st1.id]['surgeries_count'], 2)
        self.assertEqual(rows[self.st2.id]['surgeries_count'], 1)

    def test_correct_aggregated_income(self):
        r = self._get()
        rows = {row['surgery_type_id']: row for row in r.data['results']}
        # st1: 1_000_000 + 600_000 = 1_600_000
        self.assertEqual(Decimal(rows[self.st1.id]['total_center_income']), Decimal('1600000'))
        self.assertEqual(Decimal(rows[self.st2.id]['total_center_income']), Decimal('400000'))

    def test_correct_aggregated_item_cost(self):
        r = self._get()
        rows = {row['surgery_type_id']: row for row in r.data['results']}
        # st1: 100_000 + 50_000 = 150_000; st2: 0
        self.assertEqual(Decimal(rows[self.st1.id]['total_consumed_items_cost']), Decimal('150000'))
        self.assertEqual(Decimal(rows[self.st2.id]['total_consumed_items_cost']), Decimal('0'))

    def test_correct_total_approximate_profit(self):
        r = self._get()
        rows = {row['surgery_type_id']: row for row in r.data['results']}
        # st1: 1_600_000 - 150_000 - 0 = 1_450_000
        self.assertEqual(Decimal(rows[self.st1.id]['total_approximate_profit']), Decimal('1450000'))

    def test_average_profit_per_surgery(self):
        r = self._get()
        rows = {row['surgery_type_id']: row for row in r.data['results']}
        # st1: 1_450_000 / 2 = 725_000.00
        self.assertEqual(
            Decimal(rows[self.st1.id]['average_profit_per_surgery']),
            Decimal('725000.00'),
        )

    def test_sorted_by_total_profit_desc(self):
        r = self._get()
        profits = [Decimal(row['total_approximate_profit']) for row in r.data['results']]
        self.assertEqual(profits, sorted(profits, reverse=True))

    def test_metadata_total_surgeries_is_sum(self):
        r = self._get()
        meta = r.data['metadata']
        total = sum(row['surgeries_count'] for row in r.data['results'])
        self.assertEqual(meta['total_surgeries'], total)


# ---------------------------------------------------------------------------
# group_by=doctor
# ---------------------------------------------------------------------------

class SurgeryProfitReportByDoctorTest(APITestCase):

    def setUp(self):
        self.user = _user('doc_admin', role='admin')
        self.client.force_authenticate(self.user)

        self.st  = _surgery_type()
        self.doc1 = _doctor(name='دکتر اول')
        self.doc2 = _doctor(name='دکتر دوم')

        pat1, pat2, pat3 = _patient(), _patient(), _patient()

        s1 = _surgery(pat1, self.st, doctor=self.doc1, amount=Decimal('4000000'))
        _income(s1, Decimal('800000'))

        s2 = _surgery(pat2, self.st, doctor=self.doc1, amount=Decimal('3000000'))
        _income(s2, Decimal('600000'))

        s3 = _surgery(pat3, self.st, doctor=self.doc2, amount=Decimal('2000000'))
        _income(s3, Decimal('300000'))

        # Surgery with no doctor — should be excluded from group_by=doctor
        pat4 = _patient()
        _surgery(pat4, self.st, doctor=None, amount=Decimal('1000000'))

    def _get(self, **params):
        return self.client.get(URL, {'group_by': 'doctor', **params})

    def test_groups_by_doctor(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        doc_ids = {row['doctor_id'] for row in r.data['results']}
        self.assertIn(self.doc1.id, doc_ids)
        self.assertIn(self.doc2.id, doc_ids)

    def test_surgeries_without_doctor_excluded(self):
        r = self._get()
        # Total surgeries in result = 2 (doc1) + 1 (doc2) = 3, not 4
        self.assertEqual(r.data['metadata']['total_surgeries'], 3)

    def test_correct_totals_per_doctor(self):
        r = self._get()
        rows = {row['doctor_id']: row for row in r.data['results']}
        self.assertEqual(Decimal(rows[self.doc1.id]['total_center_income']), Decimal('1400000'))
        self.assertEqual(Decimal(rows[self.doc2.id]['total_center_income']), Decimal('300000'))

    def test_average_profit_per_surgery(self):
        r = self._get()
        rows = {row['doctor_id']: row for row in r.data['results']}
        # doc1: (800_000 + 600_000) / 2 = 700_000.00
        self.assertEqual(
            Decimal(rows[self.doc1.id]['average_profit_per_surgery']),
            Decimal('700000.00'),
        )

    def test_sorted_by_total_profit_desc(self):
        r = self._get()
        profits = [Decimal(row['total_approximate_profit']) for row in r.data['results']]
        self.assertEqual(profits, sorted(profits, reverse=True))


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class SurgeryProfitReportFiltersTest(APITestCase):

    def setUp(self):
        self.user = _user('filt_admin', role='admin')
        self.client.force_authenticate(self.user)

        self.st1 = _surgery_type()
        self.st2 = _surgery_type()
        self.doc = _doctor()
        self.pat = _patient()

        # Surgery in Jan 2025
        self.s_jan = _surgery(
            self.pat, self.st1, doctor=self.doc,
            amount=Decimal('4000000'),
            surgery_date=datetime.datetime(2025, 1, 15, 10, 0),
        )
        _income(self.s_jan, Decimal('1000000'))

        # Surgery in Jun 2025
        self.s_jun = _surgery(
            _patient(), self.st2,
            amount=Decimal('3000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0),
        )
        _income(self.s_jun, Decimal('500000'))

    def test_date_range_start_filter(self):
        r = self.client.get(URL, {'start_date': '2025-06-01', 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(self.s_jun.id, ids)
        self.assertNotIn(self.s_jan.id, ids)

    def test_date_range_end_filter(self):
        r = self.client.get(URL, {'end_date': '2025-01-31', 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(self.s_jan.id, ids)
        self.assertNotIn(self.s_jun.id, ids)

    def test_surgery_type_id_filter(self):
        r = self.client.get(URL, {'surgery_type_id': self.st1.id, 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(self.s_jan.id, ids)
        self.assertNotIn(self.s_jun.id, ids)

    def test_patient_id_filter(self):
        r = self.client.get(URL, {'patient_id': self.pat.id, 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertEqual(ids, {self.s_jan.id})

    def test_doctor_id_filter(self):
        r = self.client.get(URL, {'doctor_id': self.doc.id, 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(self.s_jan.id, ids)
        self.assertNotIn(self.s_jun.id, ids)

    def test_status_filter(self):
        # s_jan is COMPLETED; create a PLANNED surgery
        s_planned = _surgery(
            _patient(), self.st1,
            surgery_status=SurgeryStatus.PLANNED,
            amount=Decimal('2000000'),
        )
        r = self.client.get(URL, {'status': 'PLANNED', 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(s_planned.id, ids)
        self.assertNotIn(self.s_jan.id, ids)

    def test_payment_status_filter(self):
        s_pending = _surgery(
            _patient(), self.st1,
            payment_status=PaymentStatus.PENDING,
            amount=Decimal('2000000'),
        )
        r = self.client.get(URL, {'payment_status': 'PENDING', 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(s_pending.id, ids)
        self.assertNotIn(self.s_jan.id, ids)

    def test_min_profit_filter(self):
        # s_jan profit = 1_000_000; s_jun profit = 500_000
        r = self.client.get(URL, {'min_profit': '900000', 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(self.s_jan.id, ids)
        self.assertNotIn(self.s_jun.id, ids)

    def test_max_profit_filter(self):
        r = self.client.get(URL, {'max_profit': '600000', 'group_by': 'surgery'})
        ids = {row['surgery_id'] for row in r.data['results']}
        self.assertIn(self.s_jun.id, ids)
        self.assertNotIn(self.s_jan.id, ids)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class SurgeryProfitReportPaginationTest(APITestCase):

    def setUp(self):
        self.user = _user('page_admin', role='admin')
        self.client.force_authenticate(self.user)
        self.st = _surgery_type()

        for i in range(5):
            s = _surgery(_patient(), self.st, amount=Decimal('1000000'))
            _income(s, Decimal(str(100000 * (i + 1))))

    def test_pagination_first_page(self):
        r = self.client.get(URL, {'group_by': 'surgery', 'page': '1', 'page_size': '2'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['results']), 2)
        self.assertEqual(r.data['count'], 5)
        self.assertIsNotNone(r.data['next'])
        self.assertIsNone(r.data['previous'])

    def test_pagination_middle_page(self):
        r = self.client.get(URL, {'group_by': 'surgery', 'page': '2', 'page_size': '2'})
        self.assertEqual(len(r.data['results']), 2)
        self.assertIsNotNone(r.data['next'])
        self.assertIsNotNone(r.data['previous'])

    def test_pagination_last_page(self):
        r = self.client.get(URL, {'group_by': 'surgery', 'page': '3', 'page_size': '2'})
        self.assertEqual(len(r.data['results']), 1)
        self.assertIsNone(r.data['next'])
        self.assertIsNotNone(r.data['previous'])

    def test_page_size_max_100(self):
        r = self.client.get(URL, {'group_by': 'surgery', 'page_size': '999'})
        # Should cap at 100 and return 200 (not 400)
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Missing cost data
# ---------------------------------------------------------------------------

class SurgeryProfitReportMissingCostTest(APITestCase):

    def setUp(self):
        self.user = _user('mc_admin', role='admin')
        self.client.force_authenticate(self.user)
        self.st = _surgery_type()
        self.pat = _patient()

    def test_product_with_zero_purchase_price_has_zero_cost(self):
        prod_free = _product(purchase_price=Decimal('0'))
        s = _surgery(self.pat, self.st, amount=Decimal('3000000'))
        _income(s, Decimal('1000000'))
        _used_item(s, prod_free, Decimal('5'))
        r = self.client.get(URL, {'group_by': 'surgery'})
        row = next(x for x in r.data['results'] if x['surgery_id'] == s.id)
        self.assertEqual(Decimal(row['consumed_items_cost']), Decimal('0'))

    def test_has_missing_cost_data_flagged_true(self):
        prod_free = _product(purchase_price=Decimal('0'))
        s = _surgery(self.pat, self.st, amount=Decimal('3000000'))
        _used_item(s, prod_free, Decimal('1'))
        r = self.client.get(URL, {'group_by': 'surgery'})
        row = next(x for x in r.data['results'] if x['surgery_id'] == s.id)
        self.assertTrue(row['has_missing_cost_data'])

    def test_has_missing_cost_data_false_when_all_prices_set(self):
        prod = _product(purchase_price=Decimal('100000'))
        s = _surgery(self.pat, self.st, amount=Decimal('3000000'))
        _used_item(s, prod, Decimal('1'))
        r = self.client.get(URL, {'group_by': 'surgery'})
        row = next(x for x in r.data['results'] if x['surgery_id'] == s.id)
        self.assertFalse(row['has_missing_cost_data'])

    def test_missing_cost_items_count_in_metadata(self):
        prod_free = _product(purchase_price=Decimal('0'))
        prod_paid = _product(purchase_price=Decimal('100000'))
        s = _surgery(self.pat, self.st, amount=Decimal('3000000'))
        _used_item(s, prod_free, Decimal('2'))  # 1 item with zero price
        _used_item(s, prod_paid, Decimal('1'))  # 1 item with price
        r = self.client.get(URL, {'group_by': 'surgery'})
        # One item (prod_free row) has purchase_price=0
        self.assertEqual(r.data['metadata']['missing_cost_items_count'], 1)

    def test_surgery_with_no_items_not_flagged(self):
        s = _surgery(self.pat, self.st, amount=Decimal('3000000'))
        _income(s, Decimal('1000000'))
        r = self.client.get(URL, {'group_by': 'surgery'})
        row = next(x for x in r.data['results'] if x['surgery_id'] == s.id)
        self.assertFalse(row['has_missing_cost_data'])


# ---------------------------------------------------------------------------
# Profit margin edge cases
# ---------------------------------------------------------------------------

class SurgeryProfitReportMarginTest(APITestCase):

    def setUp(self):
        self.user = _user('margin_admin', role='admin')
        self.client.force_authenticate(self.user)
        self.st  = _surgery_type()
        self.pat = _patient()

    def test_profit_margin_null_when_center_income_zero(self):
        s = _surgery(self.pat, self.st, amount=Decimal('3000000'))
        # No income record → center_income=0
        r = self.client.get(URL, {'group_by': 'surgery'})
        row = next(x for x in r.data['results'] if x['surgery_id'] == s.id)
        self.assertIsNone(row['profit_margin_percent'])

    def test_loss_surgery_counted_in_metadata(self):
        prod = _product(purchase_price=Decimal('5000000'))
        s = _surgery(self.pat, self.st, amount=Decimal('1000000'))
        _income(s, Decimal('100000'))
        _used_item(s, prod, Decimal('1'))  # cost 5_000_000 > income 100_000 → loss
        r = self.client.get(URL, {'group_by': 'surgery'})
        row = next(x for x in r.data['results'] if x['surgery_id'] == s.id)
        self.assertLess(Decimal(row['approximate_profit']), Decimal('0'))
        self.assertGreater(r.data['metadata']['loss_surgeries_count'], 0)

    def test_profitable_surgery_counted_in_metadata(self):
        s = _surgery(self.pat, self.st, amount=Decimal('5000000'))
        _income(s, Decimal('2000000'))
        r = self.client.get(URL, {'group_by': 'surgery'})
        row = next(x for x in r.data['results'] if x['surgery_id'] == s.id)
        self.assertGreater(Decimal(row['approximate_profit']), Decimal('0'))
        self.assertGreater(r.data['metadata']['profitable_surgeries_count'], 0)
