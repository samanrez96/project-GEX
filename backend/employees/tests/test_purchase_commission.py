"""Tests for EmployeePurchaseCommission model, serializer, API, admin, and payroll integration."""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, EmployeePurchaseCommission, JobPosition
from inventory.models import Product, ProductCategory, Purchase, PurchaseItem, Vendor

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_position(name='تکنسین'):
    obj, _ = JobPosition.objects.get_or_create(name=name)
    return obj


_ctr = [0]


def _make_employee(national_id=None, name=None):
    _ctr[0] += 1
    nid = national_id or f'9{_ctr[0]:09d}'
    return Employee.objects.create(
        full_name=name or f'کارمند تست {_ctr[0]}',
        national_id=nid,
        gender='male',
        job_position=_make_position(),
        start_date=datetime.date(2025, 1, 1),
        personal_phone=f'091{_ctr[0]:08d}',
        emergency_contact_phone=f'092{_ctr[0]:08d}',
    )


def _make_vendor(name='تامین‌کننده تست'):
    v, _ = Vendor.objects.get_or_create(name=name)
    return v


def _make_category():
    c, _ = ProductCategory.objects.get_or_create(name='تجهیزات تست', defaults={'parent': None})
    return c


def _make_product(name='محصول تست', code=None):
    _ctr[0] += 1
    code = code or f'P{_ctr[0]:05d}'
    return Product.objects.create(
        name=name,
        internal_code=code,
        product_type='equipment',
        unit='عدد',
    )


def _make_purchase(vendor, reference_number='', purchase_date=None):
    from django.utils import timezone
    return Purchase.objects.create(
        vendor=vendor,
        reference_number=reference_number,
        purchase_date=purchase_date or timezone.now(),
    )


def _make_purchase_item(purchase, product, quantity=1, unit_price=Decimal('100000')):
    return PurchaseItem.objects.create(
        purchase=purchase,
        product=product,
        quantity=Decimal(str(quantity)),
        unit_price=unit_price,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class EmployeePurchaseCommissionModelTest(TestCase):

    def test_create_commission_without_purchase(self):
        emp = _make_employee()
        comm = EmployeePurchaseCommission.objects.create(
            employee=emp,
            amount=Decimal('500000'),
            commission_date=datetime.date(2025, 4, 1),
            description='صرفه‌جویی خرید دارو',
        )
        self.assertEqual(comm.employee, emp)
        self.assertEqual(comm.amount, Decimal('500000'))
        self.assertIsNone(comm.purchase)

    def test_create_commission_with_purchase(self):
        emp = _make_employee()
        vendor = _make_vendor()
        purchase = _make_purchase(vendor, reference_number='INV-001')
        comm = EmployeePurchaseCommission.objects.create(
            employee=emp,
            purchase=purchase,
            amount=Decimal('1000000'),
            commission_date=datetime.date(2025, 5, 1),
        )
        self.assertEqual(comm.purchase, purchase)
        self.assertEqual(comm.purchase.vendor, vendor)

    def test_str_representation(self):
        emp = _make_employee()
        comm = EmployeePurchaseCommission.objects.create(
            employee=emp,
            amount=Decimal('1000000'),
            commission_date=datetime.date(2025, 5, 1),
        )
        self.assertIn(emp.full_name, str(comm))
        self.assertIn('تومان', str(comm))

    def test_total_commission_sum(self):
        emp = _make_employee()
        EmployeePurchaseCommission.objects.create(
            employee=emp, amount=Decimal('200000'), commission_date=datetime.date(2025, 1, 1),
        )
        EmployeePurchaseCommission.objects.create(
            employee=emp, amount=Decimal('300000'), commission_date=datetime.date(2025, 2, 1),
        )
        from django.db.models import Sum
        total = EmployeePurchaseCommission.objects.filter(employee=emp).aggregate(
            total=Sum('amount')
        )['total']
        self.assertEqual(total, Decimal('500000'))


# ---------------------------------------------------------------------------
# Serializer tests — purchase fields, items_summary, formatting
# ---------------------------------------------------------------------------

class EmployeePurchaseCommissionSerializerTest(TestCase):

    def setUp(self):
        self.emp = _make_employee()
        self.vendor = _make_vendor('فروشنده آزمایشی')
        self.purchase = _make_purchase(self.vendor, reference_number='REF-2025-001')
        self.product1 = _make_product('سرم نرمال سالین')
        self.product2 = _make_product('گاز استریل')
        self.product3 = _make_product('دستکش جراحی')
        _make_purchase_item(self.purchase, self.product1, quantity=10, unit_price=Decimal('50000'))
        _make_purchase_item(self.purchase, self.product2, quantity=5, unit_price=Decimal('20000'))

    def _get_data(self, comm):
        from employees.serializers import EmployeePurchaseCommissionSerializer
        from employees.views import EmployeePurchaseCommissionViewSet
        # Use the viewset queryset to get prefetch benefit
        qs = EmployeePurchaseCommissionViewSet().get_queryset().filter(pk=comm.pk)
        obj = qs.get()
        return EmployeePurchaseCommissionSerializer(obj).data

    def test_purchase_ref_shows_reference_number(self):
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        self.assertEqual(data['purchase_ref'], 'REF-2025-001')

    def test_purchase_ref_fallback_to_pk_when_no_reference_number(self):
        purchase_no_ref = _make_purchase(self.vendor, reference_number='')
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=purchase_no_ref,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        self.assertEqual(data['purchase_ref'], f'#{purchase_no_ref.pk}')

    def test_purchase_pk_is_integer_id(self):
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        self.assertEqual(data['purchase_pk'], self.purchase.pk)

    def test_purchase_date_is_iso_string(self):
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        self.assertIsNotNone(data['purchase_date'])
        # Should be YYYY-MM-DD
        import re
        self.assertRegex(data['purchase_date'], r'^\d{4}-\d{2}-\d{2}$')

    def test_vendor_name_in_serializer(self):
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        self.assertEqual(data['vendor_name'], 'فروشنده آزمایشی')

    def test_items_summary_single_product(self):
        purchase_single = _make_purchase(self.vendor, reference_number='SINGLE-001')
        _make_purchase_item(purchase_single, self.product1, quantity=3)
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=purchase_single,
            amount=Decimal('50000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        self.assertEqual(data['items_summary'], 'سرم نرمال سالین')

    def test_items_summary_multiple_products(self):
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        # Should contain first product name + "قلم دیگر" suffix
        self.assertIn('سرم نرمال سالین', data['items_summary'])
        self.assertIn('قلم دیگر', data['items_summary'])
        # The count (1) should appear as Persian digit ۱
        self.assertIn('۱', data['items_summary'])

    def test_purchase_amount_sum_of_items(self):
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        # 10 × 50000 + 5 × 20000 = 500000 + 100000 = 600000
        self.assertEqual(Decimal(data['purchase_amount']), Decimal('600000'))

    def test_null_purchase_fields_when_no_purchase(self):
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            amount=Decimal('200000'),
            commission_date=datetime.date(2025, 6, 1),
            description='کمیسیون بدون فاکتور',
        )
        data = self._get_data(comm)
        self.assertIsNone(data['purchase_pk'])
        self.assertIsNone(data['purchase_ref'])
        self.assertIsNone(data['purchase_date'])
        self.assertIsNone(data['purchase_amount'])
        self.assertIsNone(data['items_summary'])
        self.assertIsNone(data['vendor_name'])

    def test_amount_has_no_decimal_point_when_whole(self):
        """purchase_amount must be a whole number string with no .00"""
        comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('100000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        data = self._get_data(comm)
        # purchase_amount should not contain a decimal point
        self.assertNotIn('.', data['purchase_amount'])


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class EmployeePurchaseCommissionAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('comm_api', 'c@t.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.emp = _make_employee()

    def test_create_commission_via_api(self):
        resp = self.client.post('/api/v2/employees/purchase-commissions/', {
            'employee': self.emp.pk,
            'amount': '750000',
            'commission_date': '2025-06-01',
            'description': 'تست',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EmployeePurchaseCommission.objects.count(), 1)

    def test_list_commissions_for_employee(self):
        EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            amount=Decimal('300000'),
            commission_date=datetime.date(2025, 5, 1),
        )
        resp = self.client.get(f'/api/v2/employees/purchase-commissions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(Decimal(results[0]['amount']), Decimal('300000'))

    def test_response_includes_new_purchase_fields(self):
        vendor = _make_vendor()
        purchase = _make_purchase(vendor, reference_number='API-TEST-001')
        product = _make_product('قلم آزمایش')
        _make_purchase_item(purchase, product, quantity=2, unit_price=Decimal('150000'))
        EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=purchase,
            amount=Decimal('50000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        resp = self.client.get(f'/api/v2/employees/purchase-commissions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        row = results[0]
        self.assertEqual(row['purchase_ref'], 'API-TEST-001')
        self.assertEqual(row['purchase_pk'], purchase.pk)
        self.assertIsNotNone(row['purchase_date'])
        self.assertEqual(row['items_summary'], 'قلم آزمایش')
        self.assertEqual(row['vendor_name'], vendor.name)
        # purchase_amount = 2 × 150000 = 300000
        self.assertEqual(Decimal(row['purchase_amount']), Decimal('300000'))

    def test_employee_without_commission_returns_empty_list(self):
        emp2 = _make_employee(national_id='1111111111')
        resp = self.client.get(f'/api/v2/employees/purchase-commissions/?employee={emp2.pk}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 0)

    def test_invalid_amount_rejected(self):
        resp = self.client.post('/api/v2/employees/purchase-commissions/', {
            'employee': self.emp.pk,
            'amount': '-100',
            'commission_date': '2025-06-01',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_surgery_commissions_do_not_appear_in_purchase_history(self):
        """CommissionTransaction (surgery-based) must not appear in purchase commissions."""
        from payroll.models import CommissionRule, CommissionTransaction
        from surgeries.models import Patient, SurgeryHistory, SurgeryType

        pos = self.emp.job_position
        stype = SurgeryType.objects.create(name='عمل کنترل', code='ctrl', base_rate=Decimal('100000'))
        rule = CommissionRule.objects.create(
            job_position=pos, surgery_type=stype,
            commission_percent=Decimal('10'),
        )
        patient = Patient.objects.create(
            full_name='بیمار کنترل', case_code='CTRL001', phone_number='09129999999',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype,
            amount=Decimal('1000000'),
            surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        CommissionTransaction.objects.create(
            surgery=surgery, employee=self.emp,
            commission_rule=rule, amount=Decimal('100000'),
        )
        # Purchase commissions endpoint must return zero records for this employee
        resp = self.client.get(f'/api/v2/employees/purchase-commissions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 0,
                         'Surgery commissions must not appear in purchase commission history')


# ---------------------------------------------------------------------------
# Admin tests
# ---------------------------------------------------------------------------

class PurchaseCommissionAdminTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('comm_adm', 'x@y.com', 'pass')
        self.client.force_login(self.superuser)
        self.emp = _make_employee()

    def test_admin_list_loads(self):
        resp = self.client.get('/admin/employees/employeepurchasecommission/')
        self.assertEqual(resp.status_code, 200)

    def test_admin_add_loads(self):
        resp = self.client.get('/admin/employees/employeepurchasecommission/add/')
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Payroll report has_commission badge — both commission types
# ---------------------------------------------------------------------------

class PayrollReportHasCommissionTest(APITestCase):
    """Payroll report has_commission reflects EITHER purchase or surgery commission."""

    def setUp(self):
        self.user = User.objects.create_superuser('pr_comm', 'p@r.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.emp_with = _make_employee()
        self.emp_without = _make_employee()

        from payroll.models import MonthlyWage
        # Both employees need a wage record to appear in the payroll report
        MonthlyWage.objects.create(
            employee=self.emp_with,
            amount=Decimal('4000000'),
            start_date=datetime.date(2025, 1, 1),
            is_active=True,
        )
        MonthlyWage.objects.create(
            employee=self.emp_without,
            amount=Decimal('5000000'),
            start_date=datetime.date(2025, 1, 1),
            is_active=True,
        )
        # Only emp_with has a purchase-based commission
        EmployeePurchaseCommission.objects.create(
            employee=self.emp_with,
            amount=Decimal('500000'),
            commission_date=datetime.date(2025, 6, 1),
            description='کمیسیون خرید',
        )

    def test_employee_with_purchase_commission_shows_darad(self):
        """Employee with EmployeePurchaseCommission → has_commission = True (دارد)."""
        resp = self.client.get('/api/v2/payroll/report/')
        self.assertEqual(resp.status_code, 200)
        emps = {r['employee_id']: r for r in resp.data.get('employees', [])}
        row = emps.get(self.emp_with.pk)
        self.assertIsNotNone(row, 'Employee with purchase commission must appear in report')
        self.assertTrue(row['has_commission'])

    def test_employee_without_any_commission_shows_nadarad(self):
        """Employee without any commission → has_commission = False (ندارد)."""
        resp = self.client.get('/api/v2/payroll/report/')
        self.assertEqual(resp.status_code, 200)
        emps = {r['employee_id']: r for r in resp.data.get('employees', [])}
        row = emps.get(self.emp_without.pk)
        self.assertIsNotNone(row, 'Employee with monthly wage must appear in report')
        self.assertFalse(row['has_commission'])

    def test_surgery_commission_alone_gives_darad(self):
        """An employee with only surgery CommissionTransaction → has_commission = True."""
        from payroll.models import CommissionRule, CommissionTransaction
        from surgeries.models import Patient, SurgeryHistory, SurgeryType

        emp_surgery_only = _make_employee()
        from payroll.models import MonthlyWage
        MonthlyWage.objects.create(
            employee=emp_surgery_only,
            amount=Decimal('3000000'),
            start_date=datetime.date(2025, 1, 1),
            is_active=True,
        )
        pos = emp_surgery_only.job_position
        stype = SurgeryType.objects.create(name='عمل سرجری', code='srg2', base_rate=Decimal('100000'))
        rule = CommissionRule.objects.create(
            job_position=pos, surgery_type=stype,
            commission_percent=Decimal('5'),
        )
        patient = Patient.objects.create(
            full_name='بیمار سرجری', case_code='SRG002', phone_number='09120000001',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype,
            amount=Decimal('2000000'),
            surgery_date=datetime.datetime(2025, 6, 15, 10, 0, tzinfo=datetime.timezone.utc),
        )
        CommissionTransaction.objects.create(
            surgery=surgery, employee=emp_surgery_only,
            commission_rule=rule, amount=Decimal('100000'),
        )
        resp = self.client.get('/api/v2/payroll/report/')
        self.assertEqual(resp.status_code, 200)
        emps = {r['employee_id']: r for r in resp.data.get('employees', [])}
        row = emps.get(emp_surgery_only.pk)
        self.assertIsNotNone(row)
        self.assertTrue(row['has_commission'],
                        'Surgery commission alone must set has_commission=True')

    def test_darad_filtered_by_date_range(self):
        """has_commission only reflects commissions within the filter period."""
        emp_old = _make_employee()
        from payroll.models import MonthlyWage
        MonthlyWage.objects.create(
            employee=emp_old,
            amount=Decimal('4000000'),
            start_date=datetime.date(2024, 1, 1),
            is_active=True,
        )
        # Purchase commission in 2024, but we filter for 1404 (2025)
        EmployeePurchaseCommission.objects.create(
            employee=emp_old,
            amount=Decimal('200000'),
            commission_date=datetime.date(2024, 3, 1),
        )
        resp = self.client.get('/api/v2/payroll/report/?year=1404&month=3')
        self.assertEqual(resp.status_code, 200)
        emps = {r['employee_id']: r for r in resp.data.get('employees', [])}
        row = emps.get(emp_old.pk)
        if row:
            self.assertFalse(row['has_commission'],
                             '2024 commission must not show as دارد in 1404 filter')


# ---------------------------------------------------------------------------
# Payroll report combined commission fields — purchase + surgery
# ---------------------------------------------------------------------------

class PayrollReportCombinedCommissionTest(APITestCase):
    """purchase_commission + surgery_commission fields in payroll report rows."""

    def setUp(self):
        self.user = User.objects.create_superuser('comb_comm', 'cb@t.com', 'pass')
        self.client.force_authenticate(user=self.user)
        from payroll.models import CommissionRule, CommissionTransaction, MonthlyWage
        from surgeries.models import Patient, SurgeryHistory, SurgeryType

        self.emp = _make_employee()
        MonthlyWage.objects.create(
            employee=self.emp,
            amount=Decimal('3000000'),
            start_date=datetime.date(2025, 1, 1),
            is_active=True,
        )
        # Purchase commission
        EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            amount=Decimal('400000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        # Surgery commission
        pos   = self.emp.job_position
        stype = SurgeryType.objects.create(name='عمل ترکیبی', code='comb1', base_rate=Decimal('100000'))
        rule  = CommissionRule.objects.create(
            job_position=pos, surgery_type=stype, commission_percent=Decimal('10'),
        )
        patient = Patient.objects.create(
            full_name='بیمار ترکیب', case_code='COMB001', phone_number='09121111111',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype,
            amount=Decimal('2000000'),
            surgery_date=datetime.datetime(2025, 6, 10, 10, 0, tzinfo=datetime.timezone.utc),
        )
        CommissionTransaction.objects.create(
            surgery=surgery, employee=self.emp,
            commission_rule=rule, amount=Decimal('200000'),
        )

    def _get_row(self):
        resp = self.client.get('/api/v2/payroll/report/')
        self.assertEqual(resp.status_code, 200)
        emps = {r['employee_id']: r for r in resp.data.get('employees', [])}
        return emps.get(self.emp.pk)

    def test_purchase_commission_field_present(self):
        row = self._get_row()
        self.assertIsNotNone(row)
        self.assertIn('purchase_commission', row)
        self.assertEqual(Decimal(str(row['purchase_commission'])), Decimal('400000'))

    def test_surgery_commission_field_present(self):
        row = self._get_row()
        self.assertIsNotNone(row)
        self.assertIn('surgery_commission', row)
        self.assertEqual(Decimal(str(row['surgery_commission'])), Decimal('200000'))

    def test_total_commission_equals_sum(self):
        """total_commission = purchase_commission + surgery_commission"""
        row = self._get_row()
        self.assertIsNotNone(row)
        expected = Decimal('400000') + Decimal('200000')
        self.assertEqual(Decimal(str(row['total_commission'])), expected)

    def test_total_payment_includes_both(self):
        """total_payment = fixed_salary + total_commission"""
        row = self._get_row()
        self.assertIsNotNone(row)
        expected = Decimal('3000000') + Decimal('400000') + Decimal('200000')
        self.assertEqual(Decimal(str(row['total_payment'])), expected)

    def test_employee_with_only_purchase_commission(self):
        """Employee with only purchase commission: surgery_commission = 0."""
        emp2 = _make_employee()
        from payroll.models import MonthlyWage
        MonthlyWage.objects.create(
            employee=emp2, amount=Decimal('2000000'),
            start_date=datetime.date(2025, 1, 1), is_active=True,
        )
        EmployeePurchaseCommission.objects.create(
            employee=emp2, amount=Decimal('150000'),
            commission_date=datetime.date(2025, 6, 1),
        )
        resp = self.client.get('/api/v2/payroll/report/')
        emps = {r['employee_id']: r for r in resp.data.get('employees', [])}
        row = emps.get(emp2.pk)
        self.assertIsNotNone(row)
        self.assertEqual(Decimal(str(row['surgery_commission'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['purchase_commission'])), Decimal('150000'))

    def test_employee_with_only_surgery_commission(self):
        """Employee with only surgery commission: purchase_commission = 0."""
        from payroll.models import CommissionRule, CommissionTransaction, MonthlyWage
        from surgeries.models import Patient, SurgeryHistory, SurgeryType
        emp3 = _make_employee()
        MonthlyWage.objects.create(
            employee=emp3, amount=Decimal('2000000'),
            start_date=datetime.date(2025, 1, 1), is_active=True,
        )
        pos   = emp3.job_position
        stype = SurgeryType.objects.create(name='عمل تکی', code='solo1', base_rate=Decimal('100000'))
        rule  = CommissionRule.objects.create(
            job_position=pos, surgery_type=stype, commission_percent=Decimal('8'),
        )
        patient = Patient.objects.create(
            full_name='بیمار تکی', case_code='SOLO001', phone_number='09122222222',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype,
            amount=Decimal('1000000'),
            surgery_date=datetime.datetime(2025, 6, 5, 10, 0, tzinfo=datetime.timezone.utc),
        )
        CommissionTransaction.objects.create(
            surgery=surgery, employee=emp3,
            commission_rule=rule, amount=Decimal('80000'),
        )
        resp = self.client.get('/api/v2/payroll/report/')
        emps = {r['employee_id']: r for r in resp.data.get('employees', [])}
        row = emps.get(emp3.pk)
        self.assertIsNotNone(row)
        self.assertEqual(Decimal(str(row['purchase_commission'])), Decimal('0'))
        self.assertEqual(Decimal(str(row['surgery_commission'])), Decimal('80000'))


# ---------------------------------------------------------------------------
# CommissionTransaction serializer — surgery_date and surgery_amount fields
# ---------------------------------------------------------------------------

class CommissionTransactionSerializerFieldsTest(APITestCase):
    """CommissionTransaction serializer now exposes surgery_date and surgery_amount."""

    def setUp(self):
        self.user = User.objects.create_superuser('ct_ser', 'cts@t.com', 'pass')
        self.client.force_authenticate(user=self.user)
        from payroll.models import CommissionRule, CommissionTransaction
        from surgeries.models import Patient, SurgeryHistory, SurgeryType

        self.emp = _make_employee()
        pos   = self.emp.job_position
        stype = SurgeryType.objects.create(name='عمل سریالایزر', code='ser1', base_rate=Decimal('100000'))
        rule  = CommissionRule.objects.create(
            job_position=pos, surgery_type=stype, commission_percent=Decimal('10'),
        )
        patient = Patient.objects.create(
            full_name='بیمار سریالایزر', case_code='SER001', phone_number='09123333333',
        )
        self.surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype,
            amount=Decimal('5000000'),
            surgery_date=datetime.datetime(2025, 7, 1, 9, 0, tzinfo=datetime.timezone.utc),
        )
        CommissionTransaction.objects.create(
            surgery=self.surgery, employee=self.emp,
            commission_rule=rule, amount=Decimal('500000'),
        )

    def test_surgery_date_in_response(self):
        resp = self.client.get(f'/api/v2/payroll/commission-transactions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, 200)
        results = resp.data.get('results', resp.data)
        row = results[0] if results else None
        self.assertIsNotNone(row)
        self.assertIn('surgery_date', row)
        import re
        self.assertRegex(row['surgery_date'], r'^\d{4}-\d{2}-\d{2}$',
                         'surgery_date must be ISO date string YYYY-MM-DD')

    def test_surgery_amount_in_response(self):
        resp = self.client.get(f'/api/v2/payroll/commission-transactions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, 200)
        results = resp.data.get('results', resp.data)
        row = results[0] if results else None
        self.assertIsNotNone(row)
        self.assertIn('surgery_amount', row)
        self.assertEqual(Decimal(str(row['surgery_amount'])), Decimal('5000000'))

    def test_surgery_amount_has_no_decimal_point(self):
        resp = self.client.get(f'/api/v2/payroll/commission-transactions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, 200)
        results = resp.data.get('results', resp.data)
        row = results[0] if results else None
        self.assertIsNotNone(row)
        self.assertNotIn('.', str(row['surgery_amount']),
                         'surgery_amount must have no decimal point when amount is whole')


# ---------------------------------------------------------------------------
# Payroll page → employee detail link
# ---------------------------------------------------------------------------

class PayrollEmployeeDetailLinkTest(APITestCase):
    """Payroll report exposes employee_id so the JS can build /detail/ links."""

    def setUp(self):
        self.user = User.objects.create_superuser('link_usr', 'lnk@t.com', 'pass')
        self.client.force_authenticate(user=self.user)
        from payroll.models import MonthlyWage
        self.emp = _make_employee(name='نمونه لینک')
        MonthlyWage.objects.create(
            employee=self.emp,
            amount=Decimal('5000000'),
            start_date=datetime.date(2025, 1, 1),
            is_active=True,
        )

    def test_payroll_report_includes_employee_id(self):
        """Each row in /api/v2/payroll/report/ must include employee_id for link building."""
        resp = self.client.get('/api/v2/payroll/report/')
        self.assertEqual(resp.status_code, 200)
        rows = resp.data.get('employees', [])
        self.assertTrue(len(rows) >= 1)
        ids = {r['employee_id'] for r in rows}
        self.assertIn(self.emp.pk, ids,
                      'employee_id must be present so JS can build /detail/ links')

    def test_employee_detail_url_returns_200(self):
        """The /admin/employees/employee/<id>/detail/ URL must be accessible."""
        self.client.force_login(self.user)
        resp = self.client.get(f'/admin/employees/employee/{self.emp.pk}/detail/')
        self.assertEqual(resp.status_code, 200,
                         'Employee detail page must return 200 — this is the link target from payroll page')

    def test_payroll_report_includes_employee_name(self):
        """employee_name must be present so it can be used as the link label."""
        resp = self.client.get('/api/v2/payroll/report/')
        self.assertEqual(resp.status_code, 200)
        rows = resp.data.get('employees', [])
        row = next((r for r in rows if r['employee_id'] == self.emp.pk), None)
        self.assertIsNotNone(row)
        self.assertEqual(row['employee_name'], 'نمونه لینک')


# ---------------------------------------------------------------------------
# Purchase commission row fields + Toman format
# ---------------------------------------------------------------------------

class PurchaseCommissionRowFieldsTest(APITestCase):
    """Verify commission row fields are complete and correctly formatted."""

    def setUp(self):
        self.user = User.objects.create_superuser('row_fld', 'rf@t.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.emp = _make_employee()
        self.vendor = _make_vendor('فروشنده ردیف')
        self.purchase = _make_purchase(self.vendor, reference_number='ROW-TEST-001')
        product = _make_product('محصول ردیف')
        _make_purchase_item(self.purchase, product, quantity=5, unit_price=Decimal('200000'))
        self.comm = EmployeePurchaseCommission.objects.create(
            employee=self.emp,
            purchase=self.purchase,
            amount=Decimal('150000'),
            commission_date=datetime.date(2025, 8, 1),
            description='بررسی فیلدهای ردیف',
        )

    def test_all_expected_fields_present(self):
        resp = self.client.get(f'/api/v2/employees/purchase-commissions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, 200)
        results = resp.data.get('results', resp.data)
        row = results[0]
        for field in ('purchase_pk', 'purchase_ref', 'purchase_date', 'purchase_amount',
                      'items_summary', 'vendor_name', 'commission_date', 'amount',
                      'description', 'employee_name'):
            self.assertIn(field, row, f'Field {field!r} missing from purchase commission row')

    def test_commission_amount_no_decimal(self):
        """The commission amount field must not contain .00 when whole."""
        resp = self.client.get(f'/api/v2/employees/purchase-commissions/?employee={self.emp.pk}')
        results = resp.data.get('results', resp.data)
        row = results[0]
        # amount is Decimal field; serializer returns string representation
        # The purchase_amount computed field must have no decimal point
        self.assertNotIn('.', str(row['purchase_amount']))

    def test_purchase_and_surgery_commissions_are_separate(self):
        """Purchase commissions must not include surgery-based CommissionTransaction rows."""
        from payroll.models import CommissionRule, CommissionTransaction
        from surgeries.models import Patient, SurgeryHistory, SurgeryType
        pos   = self.emp.job_position
        stype = SurgeryType.objects.create(name='عمل جداسازی', code='sep1', base_rate=Decimal('100000'))
        rule  = CommissionRule.objects.create(
            job_position=pos, surgery_type=stype, commission_percent=Decimal('10'),
        )
        patient = Patient.objects.create(
            full_name='بیمار جدا', case_code='SEP001', phone_number='09130000001',
        )
        surgery = SurgeryHistory.objects.create(
            patient=patient, surgery_type=stype,
            amount=Decimal('2000000'),
            surgery_date=datetime.datetime(2025, 8, 1, 10, 0, tzinfo=datetime.timezone.utc),
        )
        CommissionTransaction.objects.create(
            surgery=surgery, employee=self.emp,
            commission_rule=rule, amount=Decimal('200000'),
        )
        # purchase commission endpoint: only 1 row (the EmployeePurchaseCommission)
        resp = self.client.get(f'/api/v2/employees/purchase-commissions/?employee={self.emp.pk}')
        self.assertEqual(resp.status_code, 200)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 1,
                         'Surgery CommissionTransaction must not appear in purchase commission list')

        # surgery commission endpoint: only 1 row (the CommissionTransaction)
        resp2 = self.client.get(f'/api/v2/payroll/commission-transactions/?employee={self.emp.pk}')
        self.assertEqual(resp2.status_code, 200)
        results2 = resp2.data.get('results', resp2.data)
        self.assertEqual(len(results2), 1,
                         'EmployeePurchaseCommission must not appear in surgery commission list')
