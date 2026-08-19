import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from surgeries.models import SurgeryType

User = get_user_model()

TYPES_URL = '/api/v1/surgeries/types/'

SEED_CODES = {'nose', 'stomach', 'lift', 'beauty', 'other'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_type_counter = [0]


def make_surgery_type(**kwargs):
    _type_counter[0] += 1
    defaults = {
        'name':      f'نوع عمل {_type_counter[0]}',
        'code':      f'type_{_type_counter[0]}',
        'base_rate': Decimal('1000000'),
    }
    defaults.update(kwargs)
    return SurgeryType.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class SurgeryTypeModelTest(TestCase):

    def test_create_success_and_str(self):
        st = make_surgery_type(name='عمل بینی تست', code='nose_test')
        self.assertEqual(str(st), 'عمل بینی تست (nose_test)')

    def test_default_is_active_true(self):
        st = make_surgery_type()
        self.assertTrue(st.is_active)

    def test_code_saved_lowercase(self):
        st = SurgeryType(name='تست', code='UPPER', base_rate=Decimal('0'))
        st.save()
        st.refresh_from_db()
        self.assertEqual(st.code, 'upper')

    def test_code_valid_lowercase_letters(self):
        st = SurgeryType(name='تست پایین', code='valid', base_rate=Decimal('0'))
        st.full_clean()  # should not raise

    def test_code_valid_underscore_and_digit(self):
        st = SurgeryType(name='تست زیرخط', code='nose_job_2', base_rate=Decimal('0'))
        st.full_clean()  # should not raise

    def test_code_invalid_uppercase_raises(self):
        st = SurgeryType(name='تست بزرگ', code='Nose', base_rate=Decimal('0'))
        with self.assertRaises(ValidationError) as ctx:
            st.full_clean()
        self.assertIn('code', ctx.exception.message_dict)

    def test_code_invalid_hyphen_raises(self):
        st = SurgeryType(name='تست خط', code='nose-job', base_rate=Decimal('0'))
        with self.assertRaises(ValidationError) as ctx:
            st.full_clean()
        self.assertIn('code', ctx.exception.message_dict)

    def test_base_rate_zero_valid(self):
        st = SurgeryType(name='سایر تست', code='other_test', base_rate=Decimal('0'))
        st.full_clean()  # should not raise

    def test_base_rate_negative_raises(self):
        st = SurgeryType(name='منفی', code='neg_test', base_rate=Decimal('-1'))
        with self.assertRaises(ValidationError) as ctx:
            st.full_clean()
        self.assertIn('base_rate', ctx.exception.message_dict)

    def test_name_unique_raises_integrity_error(self):
        make_surgery_type(name='عمل یکتا', code='unique_code')
        with self.assertRaises(IntegrityError):
            make_surgery_type(name='عمل یکتا', code='another_code')

    def test_code_unique_raises_integrity_error(self):
        make_surgery_type(name='نام اول', code='dup_code')
        with self.assertRaises(IntegrityError):
            make_surgery_type(name='نام دوم', code='dup_code')

    def test_get_active_commission_rule_count_stub_returns_zero(self):
        st = make_surgery_type()
        self.assertEqual(st.get_active_commission_rule_count(), 0)


# ---------------------------------------------------------------------------
# Seed migration tests
# ---------------------------------------------------------------------------

class SurgeryTypeSeededTest(TestCase):

    def test_all_five_seeded_types_exist(self):
        seeded = SurgeryType.objects.filter(code__in=SEED_CODES)
        self.assertEqual(seeded.count(), 5)

    def test_seeded_codes_are_correct(self):
        present = set(SurgeryType.objects.filter(code__in=SEED_CODES).values_list('code', flat=True))
        self.assertEqual(present, SEED_CODES)

    def test_seed_get_or_create_is_idempotent(self):
        count_before = SurgeryType.objects.count()
        # Simulate running seed logic again
        SEED = [
            ('عمل بینی',  'nose',    5_000_000),
            ('عمل معده', 'stomach', 8_000_000),
            ('لیفت',      'lift',    6_000_000),
            ('زیبایی',   'beauty',  4_000_000),
            ('سایر',      'other',   0),
        ]
        for name, code, base_rate in SEED:
            SurgeryType.objects.get_or_create(
                code=code,
                defaults={'name': name, 'base_rate': base_rate},
            )
        self.assertEqual(SurgeryType.objects.count(), count_before)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class SurgeryTypeAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('typetest', 't@test.com', 'pass')
        self.client.force_authenticate(user=self.user)

    def _make(self, **kwargs):
        return make_surgery_type(**kwargs)

    def test_list_returns_http_200(self):
        res = self.client.get(TYPES_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_list_contains_seeded_types(self):
        res = self.client.get(TYPES_URL)
        codes = {item['code'] for item in res.data['results']}
        self.assertTrue(SEED_CODES.issubset(codes))

    def test_list_filters_is_active_true(self):
        inactive = self._make(is_active=False)
        res = self.client.get(TYPES_URL, {'is_active': 'true'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in res.data['results']]
        self.assertNotIn(inactive.pk, ids)

    def test_list_filters_is_active_false(self):
        inactive = self._make(is_active=False)
        res = self.client.get(TYPES_URL, {'is_active': 'false'})
        ids = [item['id'] for item in res.data['results']]
        self.assertIn(inactive.pk, ids)

    def test_list_uses_list_serializer_no_commission_count(self):
        res = self.client.get(TYPES_URL)
        self.assertNotIn('active_commission_rule_count', res.data['results'][0])

    def test_detail_uses_full_serializer_has_commission_count(self):
        st = SurgeryType.objects.get(code='nose')
        expected = st.get_active_commission_rule_count()
        res = self.client.get(f'{TYPES_URL}{st.pk}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('active_commission_rule_count', res.data)
        self.assertEqual(res.data['active_commission_rule_count'], expected)

    def test_post_creates_surgery_type(self):
        res = self.client.post(TYPES_URL, {
            'name':      'عمل جدید',
            'code':      'new_op',
            'base_rate': '3000000',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['code'], 'new_op')

    def test_post_uppercase_code_normalized_to_lowercase(self):
        res = self.client.post(TYPES_URL, {
            'name':      'نرمال‌سازی',
            'code':      'UPPER_CODE',
            'base_rate': '1000000',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['code'], 'upper_code')

    def test_post_invalid_code_format_returns_400(self):
        res = self.client.post(TYPES_URL, {
            'name':      'خط تیره',
            'code':      'nose-job',
            'base_rate': '1000000',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', res.data)

    def test_post_duplicate_code_returns_400(self):
        res = self.client.post(TYPES_URL, {
            'name':      'بینی تکراری',
            'code':      'nose',
            'base_rate': '1000000',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_base_rate_negative_returns_400(self):
        res = self.client.post(TYPES_URL, {
            'name':      'منفی',
            'code':      'neg_op',
            'base_rate': '-1',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('base_rate', res.data)

    def test_patch_updates_base_rate(self):
        st = self._make()
        res = self.client.patch(
            f'{TYPES_URL}{st.pk}/',
            {'base_rate': '9999999'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(res.data['base_rate'])), Decimal('9999999'))

    def test_delete_no_commission_rules_returns_204(self):
        st = self._make()
        res = self.client.delete(f'{TYPES_URL}{st.pk}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SurgeryType.objects.filter(pk=st.pk).exists())

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(TYPES_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
