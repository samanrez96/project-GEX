"""Commission calculation unit tests (CLI-62).

Covers gaps not present in the existing test_commission_transaction.py:

* Missing-rule scenarios — the task explicitly requires testing each distinct
  way a rule can be absent:
    - rule exists for a DIFFERENT position (employee's position has no rule)
    - rule exists for a DIFFERENT surgery type
    - rule exists but is INACTIVE
  These complement the existing 'no rule at all' test in test_commission_transaction.py.

* Calculation precision — Decimal rounding to 2 decimal places.

* Zero-amount surgery — commission = 0.00, transaction still created.

* CommissionTransaction fields — notes, commission_rule FK, surgery FK, employee FK.

NOT duplicated from test_commission_transaction.py:
  - basic 10%/15% calculation ✅  - idempotency ✅  - no doctor → no transaction ✅
NOT duplicated from test_commission_rule.py:
  - get_active_rule() ordering ✅  - inactive rule selection ✅
"""

import datetime
from decimal import Decimal

from django.test import TestCase

from employees.models import Employee, GenderChoice, JobPosition
from payroll.models import CommissionRule, CommissionTransaction
from payroll.services import calculate_surgery_commission
from surgeries.models import Patient, SurgeryHistory, SurgeryType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid = 0


def _uid_str():
    global _uid
    _uid += 1
    return str(_uid).zfill(6)


def _position(name=None):
    uid = _uid_str()
    return JobPosition.objects.create(name=name or f'پوزیشن-CC-{uid}')


def _employee(position, name=None):
    uid = _uid_str()
    return Employee.objects.create(
        full_name=name or f'دکتر {uid}',
        national_id=f'CC{uid}',
        gender=GenderChoice.MALE,
        job_position=position,
        start_date=datetime.date(2020, 1, 1),
        personal_phone='09120000000',
        emergency_contact_phone='09120000001',
    )


def _surgery_type(name=None, code=None):
    uid = _uid_str()
    return SurgeryType.objects.create(
        name=name or f'نوع-CC-{uid}',
        code=code or f'cc_{uid}',
        base_rate=Decimal('5000000'),
    )


def _patient():
    uid = _uid_str()
    return Patient.objects.create(
        full_name=f'بیمار {uid}',
        case_code=f'CC-{uid}',
        phone_number='09130000000',
    )


def _rule(position, surgery_type, percent='10.00', is_active=True):
    return CommissionRule.objects.create(
        job_position=position,
        surgery_type=surgery_type,
        commission_percent=Decimal(percent),
        is_active=is_active,
    )


def _surgery(patient, surgery_type, doctor=None, amount=Decimal('10000000')):
    """Create SurgeryHistory without triggering the commission signal.

    Because doctor_or_therapist is None at creation time, the signal does
    not fire.  Tests then set doctor and call calculate_surgery_commission()
    manually to isolate the service logic from signal timing.
    """
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        doctor_or_therapist=None,  # avoid signal
        amount=amount,
    )


# ---------------------------------------------------------------------------
# Missing rule behavior
# ---------------------------------------------------------------------------

class MissingRuleBehaviorTest(TestCase):
    """Explicit tests for every 'no applicable rule' scenario.

    The task requires these to be tested separately and explicitly.
    The existing test_missing_commission_rule_no_transaction covers 'no rule
    at all'.  The three cases below cover distinct ways a rule can be absent.
    """

    def setUp(self):
        self.position     = _position()
        self.doctor       = _employee(self.position)
        self.surgery_type = _surgery_type()
        self.patient      = _patient()

    # ── Case 1: rule for a different position ────────────────────────

    def test_rule_for_different_position_creates_no_transaction(self):
        """A rule for position B does NOT apply when the doctor has position A."""
        other_position = _position()
        _rule(other_position, self.surgery_type, percent='10.00')

        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('5000000'))
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(created, [], "Expected no transaction when rule is for a different position")
        self.assertEqual(CommissionTransaction.objects.count(), 0)

    # ── Case 2: rule for a different surgery type ────────────────────

    def test_rule_for_different_surgery_type_creates_no_transaction(self):
        """A rule for surgery type B does NOT apply when surgery uses type A."""
        other_surgery_type = _surgery_type()
        _rule(self.position, other_surgery_type, percent='10.00')

        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('5000000'))
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(created, [], "Expected no transaction when rule is for a different surgery type")
        self.assertEqual(CommissionTransaction.objects.count(), 0)

    # ── Case 3: rule exists but is inactive ─────────────────────────

    def test_inactive_rule_creates_no_transaction(self):
        """An is_active=False rule must be ignored — no transaction created."""
        _rule(self.position, self.surgery_type, percent='15.00', is_active=False)

        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('5000000'))
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(created, [], "Expected no transaction when rule is inactive")
        self.assertEqual(CommissionTransaction.objects.count(), 0)

    def test_deactivated_rule_creates_no_transaction(self):
        """Rule created as active then deactivated must not be used."""
        rule = _rule(self.position, self.surgery_type, percent='20.00', is_active=True)
        rule.is_active = False
        rule.save()

        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('5000000'))
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(created, [])
        self.assertEqual(CommissionTransaction.objects.count(), 0)

    # ── Case 4: rule for wrong position AND wrong surgery type ───────

    def test_completely_mismatched_rule_creates_no_transaction(self):
        """A rule mismatched on both position and surgery type is not used."""
        other_position = _position()
        other_surgery_type = _surgery_type()
        _rule(other_position, other_surgery_type, percent='10.00')

        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('5000000'))
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(created, [])

    # ── Correct rule is used when present ────────────────────────────

    def test_correct_rule_used_when_both_match(self):
        """Control: when position AND surgery type both match, transaction is created."""
        _rule(self.position, self.surgery_type, percent='10.00')

        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('10000000'))
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].amount, Decimal('1000000.00'))


# ---------------------------------------------------------------------------
# Commission amount calculation precision
# ---------------------------------------------------------------------------

class CommissionAmountPrecisionTest(TestCase):
    """Verify the calculation formula: amount = surgery.amount × percent / 100
    and that the result is rounded to exactly 2 decimal places.
    """

    def setUp(self):
        self.position     = _position()
        self.doctor       = _employee(self.position)
        self.surgery_type = _surgery_type()
        self.patient      = _patient()

    def _calc(self, surgery_amount, percent):
        rule = _rule(self.position, self.surgery_type, percent=str(percent))
        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal(str(surgery_amount)))
        surgery.doctor_or_therapist = self.doctor
        results = calculate_surgery_commission(surgery)
        rule.is_active = False
        rule.save()
        return results[0].amount if results else None

    def test_zero_surgery_amount_gives_zero_commission(self):
        """Surgery amount = 0 → commission = 0.00.  Transaction IS created."""
        rule = _rule(self.position, self.surgery_type, percent='10.00')
        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('0'))
        surgery.doctor_or_therapist = self.doctor

        created = calculate_surgery_commission(surgery)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].amount, Decimal('0.00'))

    def test_commission_rounded_to_two_decimal_places(self):
        """1.5% of 10,001,000 = 150,015.00 — verify exact Decimal rounding."""
        amount = Decimal('10001000')
        percent = Decimal('1.50')
        expected = (amount * percent / Decimal('100')).quantize(Decimal('0.01'))

        result = self._calc(10001000, '1.50')

        self.assertEqual(result, expected)

    def test_commission_formula_ten_percent(self):
        result = self._calc('5000000', '10.00')
        self.assertEqual(result, Decimal('500000.00'))

    def test_commission_formula_half_percent(self):
        """0.5% commission on a round number."""
        result = self._calc('20000000', '0.50')
        self.assertEqual(result, Decimal('100000.00'))

    def test_commission_100_percent_equals_surgery_amount(self):
        result = self._calc('3000000', '100.00')
        self.assertEqual(result, Decimal('3000000.00'))

    def test_commission_minimum_percent(self):
        """Minimum valid percent (> 0) should produce a positive result."""
        rule = _rule(self.position, self.surgery_type, percent='0.01')
        surgery = _surgery(self.patient, self.surgery_type, amount=Decimal('1000000'))
        surgery.doctor_or_therapist = self.doctor
        created = calculate_surgery_commission(surgery)
        self.assertEqual(len(created), 1)
        # 0.01% of 1,000,000 = 100.00
        self.assertEqual(created[0].amount, Decimal('100.00'))


# ---------------------------------------------------------------------------
# CommissionTransaction field verification
# ---------------------------------------------------------------------------

class CommissionTransactionFieldsTest(TestCase):
    """Verify that every field on CommissionTransaction is stored correctly."""

    def setUp(self):
        self.position     = _position()
        self.doctor       = _employee(self.position)
        self.surgery_type = _surgery_type()
        self.patient      = _patient()
        self.rule         = _rule(self.position, self.surgery_type, percent='10.00')
        self.surgery      = _surgery(
            self.patient, self.surgery_type, amount=Decimal('10000000')
        )
        self.surgery.doctor_or_therapist = self.doctor
        created = calculate_surgery_commission(self.surgery)
        self.ct  = created[0]

    def test_surgery_fk_stored(self):
        self.ct.refresh_from_db()
        self.assertEqual(self.ct.surgery_id, self.surgery.pk)

    def test_employee_fk_stored(self):
        self.ct.refresh_from_db()
        self.assertEqual(self.ct.employee_id, self.doctor.pk)

    def test_commission_rule_fk_stored(self):
        self.ct.refresh_from_db()
        self.assertEqual(self.ct.commission_rule_id, self.rule.pk)

    def test_amount_stored_as_decimal(self):
        self.ct.refresh_from_db()
        self.assertIsInstance(self.ct.amount, Decimal)
        self.assertEqual(self.ct.amount, Decimal('1000000.00'))

    def test_notes_field_not_empty(self):
        """The service must set a non-empty notes string on creation."""
        self.ct.refresh_from_db()
        self.assertIsNotNone(self.ct.notes)
        self.assertGreater(len(self.ct.notes), 0, "notes field must not be empty")

    def test_notes_contains_surgery_pk(self):
        self.ct.refresh_from_db()
        self.assertIn(str(self.surgery.pk), self.ct.notes)

    def test_notes_contains_percent(self):
        self.ct.refresh_from_db()
        self.assertIn('10', self.ct.notes)  # percent is in notes

    def test_unique_constraint_on_surgery_employee_rule(self):
        """Creating a second transaction for the same (surgery, employee, rule)
        must raise IntegrityError (enforced by unique_together)."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            CommissionTransaction.objects.create(
                surgery=self.surgery,
                employee=self.doctor,
                commission_rule=self.rule,
                amount=Decimal('999.00'),
            )


# ---------------------------------------------------------------------------
# Service idempotency edge cases
# ---------------------------------------------------------------------------

class CommissionIdempotencyTest(TestCase):
    """Edge cases for the 'skip duplicate silently' behavior."""

    def setUp(self):
        self.position     = _position()
        self.doctor       = _employee(self.position)
        self.surgery_type = _surgery_type()
        self.patient      = _patient()
        self.rule         = _rule(self.position, self.surgery_type, percent='10.00')

    def test_second_call_returns_empty_list(self):
        """Second call returns [] (not the existing transaction)."""
        surgery = _surgery(self.patient, self.surgery_type)
        surgery.doctor_or_therapist = self.doctor

        calculate_surgery_commission(surgery)
        second = calculate_surgery_commission(surgery)

        self.assertEqual(second, [])

    def test_second_call_does_not_increase_count(self):
        surgery = _surgery(self.patient, self.surgery_type)
        surgery.doctor_or_therapist = self.doctor

        calculate_surgery_commission(surgery)
        calculate_surgery_commission(surgery)

        self.assertEqual(CommissionTransaction.objects.count(), 1)

    def test_signal_then_service_call_no_duplicate(self):
        """Signal fires on surgery creation (doctor present) then service
        called again manually — count must still be 1."""
        # Create surgery WITH doctor so signal fires
        surgery = SurgeryHistory.objects.create(
            patient=self.patient,
            surgery_type=self.surgery_type,
            doctor_or_therapist=self.doctor,
            amount=Decimal('5000000'),
        )
        # Signal already created one transaction
        self.assertEqual(CommissionTransaction.objects.count(), 1)

        # Manual service call → idempotent, still 1
        calculate_surgery_commission(surgery)
        self.assertEqual(CommissionTransaction.objects.count(), 1)
