"""Tests for employee commission calculation.

Covers:
- Single employee commission calculation
- Commission variation by position
- Duplicate prevention (idempotency)
- Missing commission rule handled gracefully
- Missing doctor handled gracefully
- Signal auto-creates transaction on SurgeryHistory save
"""

import datetime
from decimal import Decimal

from django.test import TestCase

from employees.models import Employee, JobPosition
from payroll.models import CommissionRule, CommissionTransaction
from payroll.services import calculate_surgery_commission
from surgeries.models import Patient, SurgeryHistory, SurgeryType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _position(name='جراح-تست-کمیسیون', **kwargs):
    return JobPosition.objects.create(name=name, **kwargs)


def _employee(position, name='دکتر تستی', national_id='TEST-NID-1', **kwargs):
    defaults = {
        'full_name':               name,
        'national_id':             national_id,
        'gender':                  'male',
        'job_position':            position,
        'start_date':              datetime.date(2020, 1, 1),
        'personal_phone':          '09120000000',
        'emergency_contact_phone': '09120000001',
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def _surgery_type(name='عمل تست-کمیسیون', code='commission_test', base_rate=5_000_000):
    return SurgeryType.objects.get_or_create(
        code=code,
        defaults={'name': name, 'base_rate': base_rate},
    )[0]


def _patient(case_code='TEST-001', **kwargs):
    defaults = {
        'full_name':    'بیمار تست',
        'phone_number': '09130000000',
    }
    defaults.update(kwargs)
    return Patient.objects.create(case_code=case_code, **defaults)


def _commission_rule(position, surgery_type, percent=Decimal('10.00')):
    return CommissionRule.objects.create(
        job_position=position,
        surgery_type=surgery_type,
        commission_percent=percent,
    )


def _surgery_history(patient, surgery_type, doctor=None, amount=Decimal('10000000'), **kwargs):
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        doctor_or_therapist=doctor,
        amount=amount,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class CommissionCalculationTest(TestCase):

    def setUp(self):
        self.position     = _position()
        self.doctor       = _employee(self.position, name='دکتر احمدی', national_id='1234567890')
        self.surgery_type = _surgery_type()
        self.patient      = _patient()

    # ── Service function tests ───────────────────────────────────────────

    def test_single_employee_commission_calculated(self):
        """Service calculates correct amount and creates one transaction."""
        rule = _commission_rule(self.position, self.surgery_type, percent=Decimal('10.00'))
        # Create surgery without doctor so signal produces no transaction
        surgery = _surgery_history(self.patient, self.surgery_type, doctor=None, amount=Decimal('10000000'))
        # Now assign doctor and call service manually
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(len(created), 1)
        ct = created[0]
        self.assertEqual(ct.employee, self.doctor)
        self.assertEqual(ct.commission_rule, rule)
        self.assertEqual(ct.amount, Decimal('1000000.00'))  # 10% of 10,000,000

    def test_commission_amount_persisted_in_db(self):
        """Calculated commission is stored correctly in the database."""
        _commission_rule(self.position, self.surgery_type, percent=Decimal('15.00'))
        surgery = _surgery_history(self.patient, self.surgery_type, doctor=None, amount=Decimal('2000000'))
        surgery.doctor_or_therapist = self.doctor

        calculate_surgery_commission(surgery)

        self.assertEqual(CommissionTransaction.objects.count(), 1)
        ct = CommissionTransaction.objects.first()
        self.assertEqual(ct.amount, Decimal('300000.00'))  # 15% of 2,000,000

    def test_commission_varies_by_position(self):
        """Different positions with different rules produce different amounts."""
        pos2    = _position('مشاور-تست-کمیسیون')
        doctor2 = _employee(pos2, name='دکتر رضایی', national_id='0987654321')
        _commission_rule(self.position, self.surgery_type, percent=Decimal('10.00'))
        _commission_rule(pos2,          self.surgery_type, percent=Decimal('5.00'))

        # No doctor at creation → no signal transactions
        surgery1 = _surgery_history(self.patient, self.surgery_type, doctor=None, amount=Decimal('10000000'))
        patient2 = _patient(case_code='TEST-002')
        surgery2 = _surgery_history(patient2, self.surgery_type, doctor=None, amount=Decimal('10000000'))

        surgery1.doctor_or_therapist = self.doctor
        surgery2.doctor_or_therapist = doctor2

        ct1 = calculate_surgery_commission(surgery1)[0]
        ct2 = calculate_surgery_commission(surgery2)[0]

        self.assertEqual(ct1.amount, Decimal('1000000.00'))  # 10%
        self.assertEqual(ct2.amount, Decimal('500000.00'))   # 5%

    def test_duplicate_calculation_skipped(self):
        """Calling the service twice produces only one transaction (idempotent)."""
        _commission_rule(self.position, self.surgery_type)
        surgery = _surgery_history(self.patient, self.surgery_type, doctor=None)
        surgery.doctor_or_therapist = self.doctor

        calculate_surgery_commission(surgery)
        calculate_surgery_commission(surgery)  # second call — must be idempotent

        self.assertEqual(CommissionTransaction.objects.count(), 1)

    def test_missing_commission_rule_no_transaction(self):
        """When no active rule exists, service returns [] and creates nothing."""
        surgery = _surgery_history(self.patient, self.surgery_type, doctor=None)
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(created, [])
        self.assertEqual(CommissionTransaction.objects.count(), 0)

    def test_no_doctor_no_transaction(self):
        """When doctor_or_therapist is None, service returns [] and creates nothing."""
        _commission_rule(self.position, self.surgery_type)
        surgery = _surgery_history(self.patient, self.surgery_type, doctor=None)

        # doctor is None — service must skip
        created = calculate_surgery_commission(surgery)

        self.assertEqual(created, [])
        self.assertEqual(CommissionTransaction.objects.count(), 0)

    # ── Signal integration test ──────────────────────────────────────────

    def test_signal_auto_creates_transaction_on_surgery_save(self):
        """post_save signal triggers commission calculation automatically."""
        _commission_rule(self.position, self.surgery_type, percent=Decimal('10.00'))

        # Doctor present at creation time → signal fires and creates transaction
        _surgery_history(
            self.patient, self.surgery_type,
            doctor=self.doctor, amount=Decimal('5000000'),
        )

        self.assertEqual(CommissionTransaction.objects.count(), 1)
        ct = CommissionTransaction.objects.first()
        self.assertEqual(ct.amount, Decimal('500000.00'))  # 10% of 5,000,000
        self.assertEqual(ct.employee, self.doctor)
