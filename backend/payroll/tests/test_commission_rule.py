import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, GenderChoice, JobPosition
from payroll.models import CommissionRule, PayrollTypeConfig
from surgeries.models import SurgeryType

User = get_user_model()

RULES_URL      = '/api/v2/payroll/commission-rules/'
MATRIX_URL     = '/api/v2/payroll/commission-rules/matrix/'
BY_POSITION_URL = '/api/v2/payroll/commission-rules/by_position/'

_counter = [0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(name=None):
    _counter[0] += 1
    n = name or f'پوزیشن {_counter[0]}'
    pos, _ = JobPosition.objects.get_or_create(name=n, defaults={'is_active': True})
    return pos


def make_surgery_type(code=None, name=None):
    _counter[0] += 1
    c = code or f'st_{_counter[0]}'
    n = name or f'نوع عمل {_counter[0]}'
    st, _ = SurgeryType.objects.get_or_create(
        code=c, defaults={'name': n, 'base_rate': Decimal('1000000')},
    )
    return st


def make_employee(job_position=None, **kwargs):
    _counter[0] += 1
    if job_position is None:
        job_position = make_position()
    defaults = {
        'full_name':               f'کارمند {_counter[0]}',
        'national_id':             str(_counter[0]).zfill(10),
        'gender':                  GenderChoice.MALE,
        'start_date':              datetime.date(2022, 1, 1),
        'personal_phone':          f'091{str(_counter[0]).zfill(8)}',
        'emergency_contact_phone': '09120000000',
        'job_position':            job_position,
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_rule(job_position, surgery_type, percent='15.00', **kwargs):
    return CommissionRule.objects.create(
        job_position=job_position,
        surgery_type=surgery_type,
        commission_percent=Decimal(percent),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class CommissionRuleModelTest(TestCase):

    def setUp(self):
        self.position    = make_position('دکتر تست')
        self.stype       = make_surgery_type('nose_test', 'عمل تست')

    def test_create_success_and_str(self):
        rule = make_rule(self.position, self.stype, '15.00')
        self.assertIn('15', str(rule))
        self.assertIn('%', str(rule))

    def test_commission_percent_immutability_raises_on_change(self):
        rule = make_rule(self.position, self.stype, '15.00')
        rule.commission_percent = Decimal('20.00')
        with self.assertRaises(ValueError):
            rule.save()

    def test_commission_percent_immutability_allows_notes_update(self):
        rule = make_rule(self.position, self.stype, '15.00')
        rule.notes = 'یادداشت'
        rule.save()  # should not raise
        rule.refresh_from_db()
        self.assertEqual(rule.notes, 'یادداشت')

    def test_clean_percent_zero_raises(self):
        rule = CommissionRule(
            job_position=self.position,
            surgery_type=self.stype,
            commission_percent=Decimal('0'),
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.full_clean()
        self.assertIn('commission_percent', ctx.exception.message_dict)

    def test_clean_percent_100_valid(self):
        rule = CommissionRule(
            job_position=self.position,
            surgery_type=self.stype,
            commission_percent=Decimal('100'),
        )
        rule.full_clean()  # should not raise

    def test_clean_percent_over_100_raises(self):
        rule = CommissionRule(
            job_position=self.position,
            surgery_type=self.stype,
            commission_percent=Decimal('101'),
        )
        with self.assertRaises(ValidationError) as ctx:
            rule.full_clean()
        self.assertIn('commission_percent', ctx.exception.message_dict)

    def test_clean_duplicate_active_rule_raises(self):
        make_rule(self.position, self.stype, '15.00')
        duplicate = CommissionRule(
            job_position=self.position,
            surgery_type=self.stype,
            commission_percent=Decimal('20.00'),
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_clean_allows_second_rule_when_first_inactive(self):
        first = make_rule(self.position, self.stype, '15.00')
        first.is_active = False
        first.save()
        second = CommissionRule(
            job_position=self.position,
            surgery_type=self.stype,
            commission_percent=Decimal('20.00'),
        )
        second.full_clean()  # should not raise

    def test_clean_allows_same_surgery_type_different_positions(self):
        pos2 = make_position('پوزیشن دیگر')
        make_rule(self.position, self.stype, '15.00')
        rule2 = CommissionRule(
            job_position=pos2,
            surgery_type=self.stype,
            commission_percent=Decimal('20.00'),
        )
        rule2.full_clean()  # should not raise

    def test_get_active_rule_returns_correct_rule(self):
        rule = make_rule(self.position, self.stype, '15.00')
        found = CommissionRule.get_active_rule(self.position.pk, self.stype.pk)
        self.assertEqual(found, rule)

    def test_get_active_rule_returns_none_when_no_active_rule(self):
        rule = make_rule(self.position, self.stype, '15.00')
        rule.is_active = False
        rule.save()
        found = CommissionRule.get_active_rule(self.position.pk, self.stype.pk)
        self.assertIsNone(found)

    def test_get_active_rule_returns_latest_when_multiple(self):
        older = CommissionRule.objects.create(
            job_position=self.position,
            surgery_type=self.stype,
            commission_percent=Decimal('10.00'),
            start_date=datetime.date(2024, 1, 1),
            is_active=True,
        )
        newer = CommissionRule.objects.create(
            job_position=self.position,
            surgery_type=self.stype,
            commission_percent=Decimal('20.00'),
            start_date=datetime.date(2025, 1, 1),
            is_active=True,
        )
        found = CommissionRule.get_active_rule(self.position.pk, self.stype.pk)
        self.assertEqual(found, newer)

    # ── Signal tests ─────────────────────────────────────────────────

    def test_signal_sets_has_commission_true_on_create(self):
        emp = make_employee(job_position=self.position)
        cfg = PayrollTypeConfig.objects.get(employee=emp)
        self.assertFalse(cfg.has_commission)

        make_rule(self.position, self.stype)

        cfg.refresh_from_db()
        self.assertTrue(cfg.has_commission)

    def test_signal_sets_has_commission_false_when_last_rule_deactivated(self):
        emp  = make_employee(job_position=self.position)
        rule = make_rule(self.position, self.stype)
        cfg  = PayrollTypeConfig.objects.get(employee=emp)
        self.assertTrue(cfg.has_commission)

        rule.is_active = False
        rule.save()

        cfg.refresh_from_db()
        self.assertFalse(cfg.has_commission)

    def test_signal_updates_all_employees_with_position(self):
        emp1 = make_employee(job_position=self.position)
        emp2 = make_employee(job_position=self.position)
        pos2 = make_position('مستقل')
        emp3 = make_employee(job_position=pos2)

        make_rule(self.position, self.stype)

        cfg1 = PayrollTypeConfig.objects.get(employee=emp1)
        cfg2 = PayrollTypeConfig.objects.get(employee=emp2)
        cfg3 = PayrollTypeConfig.objects.get(employee=emp3)

        self.assertTrue(cfg1.has_commission)
        self.assertTrue(cfg2.has_commission)
        self.assertFalse(cfg3.has_commission)  # unrelated position unaffected

    # ── SurgeryType integration ───────────────────────────────────────

    def test_surgery_type_get_active_commission_rule_count_real(self):
        self.assertEqual(self.stype.get_active_commission_rule_count(), 0)
        make_rule(self.position, self.stype)
        self.assertEqual(self.stype.get_active_commission_rule_count(), 1)

    def test_surgery_type_clean_blocks_deactivation_with_active_rules(self):
        make_rule(self.position, self.stype)
        self.stype.is_active = False
        with self.assertRaises(ValidationError) as ctx:
            self.stype.full_clean()
        self.assertIn('is_active', ctx.exception.message_dict)

    def test_surgery_type_clean_allows_deactivation_with_no_active_rules(self):
        # no rules → deactivation allowed
        self.stype.is_active = False
        self.stype.full_clean()  # should not raise


# ---------------------------------------------------------------------------
# Seed migration tests
# ---------------------------------------------------------------------------

class CommissionRuleSeededTest(TestCase):

    SEEDED_PAIRS = [
        ('متخصص بیهوشی', 'nose'),
        ('متخصص بیهوشی', 'stomach'),
        ('متخصص بیهوشی', 'lift'),
        ('متخصص بیهوشی', 'beauty'),
        ('پرستار',        'nose'),
        ('پرستار',        'stomach'),
        ('تکنسین',        'nose'),
        ('تکنسین',        'stomach'),
    ]

    def test_all_eight_rules_seeded(self):
        for position_name, surgery_code in self.SEEDED_PAIRS:
            self.assertTrue(
                CommissionRule.objects.filter(
                    job_position__name=position_name,
                    surgery_type__code=surgery_code,
                ).exists(),
                msg=f'Missing seeded rule: {position_name} × {surgery_code}',
            )

    def test_seeded_rules_are_active(self):
        for position_name, surgery_code in self.SEEDED_PAIRS:
            qs = CommissionRule.objects.filter(
                job_position__name=position_name,
                surgery_type__code=surgery_code,
                is_active=True,
            )
            self.assertTrue(qs.exists(), msg=f'Seeded rule inactive: {position_name} × {surgery_code}')

    def test_seed_get_or_create_is_idempotent(self):
        count_before = CommissionRule.objects.count()
        for position_name, surgery_code in self.SEEDED_PAIRS:
            try:
                position     = JobPosition.objects.get(name=position_name)
                surgery_type = SurgeryType.objects.get(code=surgery_code)
            except (JobPosition.DoesNotExist, SurgeryType.DoesNotExist):
                continue
            CommissionRule.objects.get_or_create(
                job_position=position,
                surgery_type=surgery_type,
                defaults={'commission_percent': 10, 'start_date': datetime.date.today()},
            )
        self.assertEqual(CommissionRule.objects.count(), count_before)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class CommissionRuleAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('ruletest', 'r@test.com', 'pass')
        self.client.force_authenticate(user=self.user)
        self.position = make_position('دکتر API')
        self.stype    = make_surgery_type('api_test', 'API عمل')

    def _make(self, **kwargs):
        return make_rule(self.position, self.stype, **kwargs)

    def test_list_returns_http_200(self):
        res = self.client.get(RULES_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_list_contains_seeded_rules(self):
        res = self.client.get(RULES_URL)
        self.assertGreaterEqual(res.data['count'], 8)

    def test_list_filter_is_active_true(self):
        rule = self._make()
        rule.is_active = False
        rule.save()
        res = self.client.get(RULES_URL, {'is_active': 'true'})
        ids = [item['id'] for item in res.data['results']]
        self.assertNotIn(rule.pk, ids)

    def test_list_filter_job_position(self):
        res = self.client.get(RULES_URL, {'job_position': self.position.pk})
        for item in res.data['results']:
            self.assertEqual(item['job_position_name'], self.position.name)

    def test_list_uses_list_serializer_no_surgery_type_code(self):
        res = self.client.get(RULES_URL)
        result = res.data['results'][0]
        self.assertNotIn('surgery_type_code', result)
        self.assertIn('job_position_name', result)

    def test_detail_has_full_fields(self):
        rule = self._make()
        res = self.client.get(f'{RULES_URL}{rule.pk}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('surgery_type_code', res.data)
        self.assertIn('job_position_name', res.data)

    def test_post_creates_rule(self):
        res = self.client.post(RULES_URL, {
            'job_position': self.position.pk,
            'surgery_type': self.stype.pk,
            'commission_percent': '15.00',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_post_duplicate_active_rule_returns_400(self):
        self._make()
        pos2  = make_position()
        stype2 = make_surgery_type()
        # Create another rule for the same pair
        res = self.client.post(RULES_URL, {
            'job_position': self.position.pk,
            'surgery_type': self.stype.pk,
            'commission_percent': '20.00',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_percent_zero_returns_400(self):
        pos2   = make_position()
        stype2 = make_surgery_type()
        res = self.client.post(RULES_URL, {
            'job_position': pos2.pk,
            'surgery_type': stype2.pk,
            'commission_percent': '0',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('commission_percent', res.data)

    def test_patch_percent_returns_400(self):
        rule = self._make()
        res = self.client.patch(
            f'{RULES_URL}{rule.pk}/',
            {'commission_percent': '99.00'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_notes_returns_200(self):
        rule = self._make()
        res = self.client.patch(
            f'{RULES_URL}{rule.pk}/',
            {'notes': 'یادداشت'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['notes'], 'یادداشت')

    def test_delete_returns_405(self):
        rule = self._make()
        res = self.client.delete(f'{RULES_URL}{rule.pk}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_matrix_returns_correct_structure(self):
        res = self.client.get(MATRIX_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('positions', res.data)
        self.assertIn('surgery_types', res.data)
        self.assertIn('matrix', res.data)

    def test_matrix_contains_seeded_data(self):
        res = self.client.get(MATRIX_URL)
        positions = res.data['positions']
        self.assertIn('متخصص بیهوشی', positions)
        self.assertIn('پرستار', positions)

    def test_matrix_percent_is_float(self):
        res = self.client.get(MATRIX_URL)
        matrix = res.data['matrix']
        for pos, surgeries in matrix.items():
            for stype_name, pct in surgeries.items():
                self.assertIsInstance(pct, float)

    def test_by_position_returns_rules(self):
        self._make()
        res = self.client.get(BY_POSITION_URL, {'job_position': self.position.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data), 1)
        for item in res.data:
            self.assertEqual(item['job_position'], self.position.pk)

    def test_by_position_without_param_returns_400(self):
        res = self.client.get(BY_POSITION_URL)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(RULES_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
