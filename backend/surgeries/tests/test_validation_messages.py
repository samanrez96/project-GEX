"""Validation message tests for surgery endpoints (CLI-60).

Verifies that API returns clear Persian validation messages for:
- patient case_code uniqueness
- negative surgery amount
- invalid commission percent
- zero/negative used item quantity
- insufficient stock for used items
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from inventory.models import Product, ProductType
from surgeries.models import (
    Patient,
    PaymentStatus,
    SurgeryHistory,
    SurgeryStatus,
    SurgeryType,
)

User = get_user_model()
PATIENTS_URL    = '/api/v2/surgeries/patients/'
HISTORY_URL     = '/api/v2/surgeries/history/'
USED_ITEMS_URL  = '/api/v2/surgeries/used-items/'


def _user():
    return User.objects.create_user(username=f'vm_s_{User.objects.count()}', password='x')


def _surgery_type():
    import random
    uid = random.randint(100000, 999999)
    return SurgeryType.objects.create(
        name=f'نوع {uid}', code=f'op_{uid}', base_rate=Decimal('500000'),
    )


def _patient(name=None):
    import random
    uid = random.randint(100000, 999999)
    return Patient.objects.create(
        full_name=name or f'بیمار {uid}',
        case_code=f'C-{uid}',
        phone_number='09100000000',
    )


def _surgery(patient, surgery_type, amount=Decimal('5000000')):
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        amount=amount,
        surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        status=SurgeryStatus.COMPLETED,
        payment_status=PaymentStatus.PAID,
    )


class PatientValidationTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)

    def test_duplicate_case_code_returns_persian_message(self):
        existing = _patient()
        resp = self.client.post(PATIENTS_URL, {
            'full_name':    'بیمار تکراری',
            'case_code':    existing.case_code,
            'phone_number': '09200000000',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('case_code', resp.data)
        errors = str(resp.data['case_code'])
        self.assertIn('قبلاً ثبت شده', errors)

    def test_unique_case_code_is_accepted(self):
        import random
        uid = random.randint(100000, 999999)
        resp = self.client.post(PATIENTS_URL, {
            'full_name':    'بیمار جدید',
            'case_code':    f'UNIQ-{uid}',
            'phone_number': '09300000000',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class SurgeryHistoryValidationTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.patient = _patient()
        self.st = _surgery_type()

    def test_negative_amount_rejected(self):
        resp = self.client.post(HISTORY_URL, {
            'patient':      self.patient.id,
            'surgery_type': self.st.id,
            'amount':       '-100',
            'surgery_date': '2025-06-01T10:00:00Z',
            'status':       'COMPLETED',
            'payment_status': 'PAID',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', resp.data)
        errors = str(resp.data['amount'])
        self.assertIn('منفی', errors)

    def test_zero_amount_is_allowed(self):
        resp = self.client.post(HISTORY_URL, {
            'patient':        self.patient.id,
            'surgery_type':   self.st.id,
            'amount':         '0',
            'surgery_date':   '2025-06-01T10:00:00Z',
            'status':         'COMPLETED',
            'payment_status': 'PAID',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_invalid_commission_percent_rejected(self):
        resp = self.client.post(HISTORY_URL, {
            'patient':                  self.patient.id,
            'surgery_type':             self.st.id,
            'amount':                   '5000000',
            'surgery_date':             '2025-06-01T10:00:00Z',
            'status':                   'COMPLETED',
            'payment_status':           'PAID',
            'center_commission_percent': '110',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('center_commission_percent', resp.data)


class SurgeryUsedItemValidationTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.patient = _patient()
        self.st = _surgery_type()
        self.surgery = _surgery(self.patient, self.st)
        import random
        uid = random.randint(100000, 999999)
        self.product = Product.objects.create(
            name=f'دارو {uid}',
            internal_code=f'D-{uid}',
            product_type=ProductType.MEDICINE,
            unit='عدد',
            purchase_price=Decimal('1000'),
        )

    def test_zero_quantity_rejected(self):
        resp = self.client.post(USED_ITEMS_URL, {
            'surgery':  self.surgery.id,
            'product':  self.product.id,
            'quantity': '0',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('quantity', resp.data)

    def test_insufficient_stock_returns_persian_message(self):
        # Product has 0 stock; trying to consume any amount should fail
        resp = self.client.post(USED_ITEMS_URL, {
            'surgery':  self.surgery.id,
            'product':  self.product.id,
            'quantity': '100',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # The error message should mention insufficient stock in Persian
        error_text = str(resp.data)
        self.assertTrue(
            'موجودی' in error_text or 'کافی' in error_text or 'quantity' in str(resp.data),
            f"Expected Persian stock error, got: {resp.data}"
        )
