"""Filter and sort tests for SurgeryHistoryViewSet (CLI-58)."""

import datetime
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, JobPosition
from surgeries.models import (
    Patient,
    PaymentStatus,
    SurgeryHistory,
    SurgeryStatus,
    SurgeryType,
)

User = get_user_model()
URL  = '/api/v2/surgeries/history/'

_ctr = [0]


def _user():
    return User.objects.create_user(username=f'sf_{User.objects.count()}', password='x')


def _surgery_type(name=None):
    _ctr[0] += 1
    return SurgeryType.objects.create(
        name=name or f'نوع {_ctr[0]}',
        code=f'op_{_ctr[0]}',
        base_rate=Decimal('500000'),
    )


def _patient(n=None):
    _ctr[0] += 1
    n = n or _ctr[0]
    return Patient.objects.create(
        full_name=f'بیمار {n}',
        case_code=f'P{n:05d}',
        phone_number=f'091{n:08d}',
    )


def _position():
    return JobPosition.objects.create(name=f'Pos_{random.randint(10000, 99999)}')


def _doctor():
    return Employee.objects.create(
        full_name=f'دکتر {random.randint(1, 99)}',
        national_id=str(random.randint(1_000_000_000, 9_999_999_999)),
        gender='male',
        job_position=_position(),
        start_date=datetime.date(2020, 1, 1),
        personal_phone='09100000000',
        emergency_contact_phone='09200000000',
    )


def _surgery(patient, surgery_type, amount=Decimal('5000000'),
             surgery_date=None, status=SurgeryStatus.COMPLETED,
             payment_status=PaymentStatus.PAID, doctor=None):
    return SurgeryHistory.objects.create(
        patient=patient,
        surgery_type=surgery_type,
        amount=amount,
        surgery_date=surgery_date or datetime.datetime(2025, 6, 1, 10, 0,
                                                        tzinfo=datetime.timezone.utc),
        status=status,
        payment_status=payment_status,
        doctor_or_therapist=doctor,
    )


class SurgeryHistoryFilterTest(APITestCase):

    def setUp(self):
        self.user = _user()
        self.client.force_authenticate(self.user)
        self.st1 = _surgery_type('بینی')
        self.st2 = _surgery_type('چشم')
        self.doc = _doctor()

    # ── Filter by surgery_type ────────────────────────────────────

    def test_filter_by_surgery_type(self):
        s1 = _surgery(_patient(), self.st1)
        s2 = _surgery(_patient(), self.st2)
        resp = self.client.get(URL, {'surgery_type': self.st1.id})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s1.id, ids)
        self.assertNotIn(s2.id, ids)

    # ── Filter by doctor/therapist ────────────────────────────────

    def test_filter_by_doctor(self):
        s_with    = _surgery(_patient(), self.st1, doctor=self.doc)
        s_without = _surgery(_patient(), self.st1)
        resp = self.client.get(URL, {'doctor_or_therapist': self.doc.id})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_with.id, ids)
        self.assertNotIn(s_without.id, ids)

    # ── Filter by status ──────────────────────────────────────────

    def test_filter_by_status_completed(self):
        s_done    = _surgery(_patient(), self.st1, status=SurgeryStatus.COMPLETED)
        s_planned = _surgery(_patient(), self.st1, status=SurgeryStatus.PLANNED)
        resp = self.client.get(URL, {'status': 'COMPLETED'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_done.id, ids)
        self.assertNotIn(s_planned.id, ids)

    def test_filter_by_payment_status(self):
        s_paid    = _surgery(_patient(), self.st1, payment_status=PaymentStatus.PAID)
        s_pending = _surgery(_patient(), self.st1, payment_status=PaymentStatus.PENDING)
        resp = self.client.get(URL, {'payment_status': 'PAID'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_paid.id, ids)
        self.assertNotIn(s_pending.id, ids)

    # ── Filter by surgery date range ──────────────────────────────

    def test_filter_surgery_date_from(self):
        s_old = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2023, 1, 1, 10, 0,
                                                         tzinfo=datetime.timezone.utc))
        s_new = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2025, 6, 1, 10, 0,
                                                         tzinfo=datetime.timezone.utc))
        resp = self.client.get(URL, {'surgery_date_from': '2024-01-01'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_new.id, ids)
        self.assertNotIn(s_old.id, ids)

    def test_filter_surgery_date_to(self):
        s_old = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2022, 3, 1, 10, 0,
                                                         tzinfo=datetime.timezone.utc))
        s_new = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2025, 6, 1, 10, 0,
                                                         tzinfo=datetime.timezone.utc))
        resp = self.client.get(URL, {'surgery_date_to': '2023-01-01'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_old.id, ids)
        self.assertNotIn(s_new.id, ids)

    def test_filter_surgery_date_range(self):
        s_in  = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2024, 6, 15, 10, 0,
                                                         tzinfo=datetime.timezone.utc))
        s_out = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2020, 1, 1, 10, 0,
                                                         tzinfo=datetime.timezone.utc))
        resp = self.client.get(URL, {
            'surgery_date_from': '2024-01-01',
            'surgery_date_to':   '2024-12-31',
        })
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_in.id, ids)
        self.assertNotIn(s_out.id, ids)

    # ── Filter by amount range ────────────────────────────────────

    def test_filter_min_amount(self):
        s_small = _surgery(_patient(), self.st1, amount=Decimal('100000'))
        s_large = _surgery(_patient(), self.st1, amount=Decimal('5000000'))
        resp = self.client.get(URL, {'min_amount': '1000000'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_large.id, ids)
        self.assertNotIn(s_small.id, ids)

    def test_filter_max_amount(self):
        s_small = _surgery(_patient(), self.st1, amount=Decimal('50000'))
        s_large = _surgery(_patient(), self.st1, amount=Decimal('8000000'))
        resp = self.client.get(URL, {'max_amount': '100000'})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_small.id, ids)
        self.assertNotIn(s_large.id, ids)

    # ── Sorting ───────────────────────────────────────────────────

    def test_sort_by_surgery_date(self):
        _surgery(_patient(), self.st1,
                 surgery_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc))
        _surgery(_patient(), self.st1,
                 surgery_date=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
        resp = self.client.get(URL, {'ordering': 'surgery_date'})
        self.assertEqual(resp.status_code, 200)
        dates = [r['surgery_date'] for r in resp.data['results']]
        self.assertEqual(dates, sorted(dates))

    def test_sort_by_amount_desc(self):
        _surgery(_patient(), self.st1, amount=Decimal('100000'))
        _surgery(_patient(), self.st1, amount=Decimal('900000'))
        resp = self.client.get(URL, {'ordering': '-amount'})
        self.assertEqual(resp.status_code, 200)
        amounts = [Decimal(r['amount']) for r in resp.data['results']]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    def test_sort_by_status(self):
        resp = self.client.get(URL, {'ordering': 'status'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_invalid_ordering_is_ignored_safely(self):
        resp = self.client.get(URL, {'ordering': 'secret_field'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    # ── Combined filters ──────────────────────────────────────────

    def test_date_and_status_filter_together(self):
        s1 = _surgery(_patient(), self.st1,
                      surgery_date=datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc),
                      status=SurgeryStatus.COMPLETED)
        s2 = _surgery(_patient(), self.st1,
                      surgery_date=datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc),
                      status=SurgeryStatus.CANCELLED)
        resp = self.client.get(URL, {
            'surgery_date_from': '2025-01-01',
            'status': 'COMPLETED',
        })
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s1.id, ids)
        self.assertNotIn(s2.id, ids)

    # ── Jalali (Persian/Arabic-Indic digit) date input ─────────────

    def test_filter_surgery_date_from_persian_digits(self):
        from common.dates import to_jalali_date
        s_old = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2023, 1, 1, 10, 0, tzinfo=datetime.timezone.utc))
        s_new = _surgery(_patient(), self.st1,
                         surgery_date=datetime.datetime(2025, 6, 1, 10, 0, tzinfo=datetime.timezone.utc))
        jalali_from = to_jalali_date(datetime.date(2024, 1, 1))
        resp = self.client.get(URL, {'surgery_date_from': jalali_from})
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s_new.id, ids)
        self.assertNotIn(s_old.id, ids)

    def test_filter_surgery_date_range_persian_digits_both_boundaries_inclusive(self):
        from common.dates import to_jalali_date
        s_start = _surgery(_patient(), self.st1,
                           surgery_date=datetime.datetime(2024, 6, 1, 10, 0, tzinfo=datetime.timezone.utc))
        s_end   = _surgery(_patient(), self.st1,
                           surgery_date=datetime.datetime(2024, 6, 30, 10, 0, tzinfo=datetime.timezone.utc))
        s_out   = _surgery(_patient(), self.st1,
                           surgery_date=datetime.datetime(2024, 7, 1, 10, 0, tzinfo=datetime.timezone.utc))
        resp = self.client.get(URL, {
            'surgery_date_from': to_jalali_date(datetime.date(2024, 6, 1)),
            'surgery_date_to':   to_jalali_date(datetime.date(2024, 6, 30)),
        })
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        # Both boundary dates themselves must be included (inclusive range).
        self.assertIn(s_start.id, ids)
        self.assertIn(s_end.id, ids)
        self.assertNotIn(s_out.id, ids)

    # ── Reversed / invalid date range ───────────────────────────────

    def test_reversed_date_range_returns_persian_validation_error(self):
        resp = self.client.get(URL, {
            'surgery_date_from': '2025-06-10',
            'surgery_date_to':   '2025-06-01',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Compare by error code (ASCII-safe) rather than the literal Persian
        # string, which is fragile to Unicode normalization differences
        # (e.g. Arabic vs Persian yeh, ZWNJ placement) across edits.
        error_detail = resp.data['__all__'][0]
        self.assertEqual(error_detail.code, 'invalid_range')
        # The message must still be a non-empty Persian string, not a raw
        # English/technical error.
        self.assertTrue(len(str(error_detail)) > 0)
        self.assertNotIn('Traceback', str(error_detail))

    def test_invalid_date_format_returns_400_not_500(self):
        resp = self.client.get(URL, {'surgery_date_from': 'not-a-date'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_out_of_range_jalali_date_returns_400_not_500(self):
        resp = self.client.get(URL, {'surgery_date_from': '1405/13/40'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Stable ordering / pagination interaction ────────────────────

    def test_ordering_by_surgery_date_is_stable_for_same_date_rows(self):
        # Several surgeries sharing the exact same surgery_date must sort
        # consistently (by id) rather than in an arbitrary DB-dependent order.
        same_date = datetime.datetime(2025, 4, 1, 9, 0, tzinfo=datetime.timezone.utc)
        surgeries = [_surgery(_patient(), self.st1, surgery_date=same_date) for _ in range(5)]
        resp1 = self.client.get(URL, {'ordering': '-surgery_date', 'page_size': 50})
        resp2 = self.client.get(URL, {'ordering': '-surgery_date', 'page_size': 50})
        ids1 = [r['id'] for r in resp1.data['results'] if r['id'] in [s.id for s in surgeries]]
        ids2 = [r['id'] for r in resp2.data['results'] if r['id'] in [s.id for s in surgeries]]
        self.assertEqual(ids1, ids2)
        self.assertEqual(ids1, sorted((s.id for s in surgeries), reverse=True))

    def test_pagination_preserves_date_filter(self):
        for i in range(6):
            _surgery(_patient(), self.st1,
                     surgery_date=datetime.datetime(2025, 5, 1 + i, tzinfo=datetime.timezone.utc))
        _surgery(_patient(), self.st1,
                 surgery_date=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc))
        params = {
            'surgery_date_from': '2025-05-01',
            'surgery_date_to':   '2025-05-31',
            'page_size':         2,
        }
        page1 = self.client.get(URL, dict(params, page=1))
        page2 = self.client.get(URL, dict(params, page=2))
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(page1.data['count'], 6)
        self.assertEqual(page2.data['count'], 6)
        ids_page1 = {r['id'] for r in page1.data['results']}
        ids_page2 = {r['id'] for r in page2.data['results']}
        self.assertFalse(ids_page1 & ids_page2)   # no overlap between pages

    def test_clearing_date_filter_restores_all_results(self):
        _surgery(_patient(), self.st1,
                 surgery_date=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc))
        _surgery(_patient(), self.st1,
                 surgery_date=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc))
        filtered = self.client.get(URL, {'surgery_date_from': '2024-01-01'})
        unfiltered = self.client.get(URL, {})
        self.assertLess(filtered.data['count'], unfiltered.data['count'])
        self.assertEqual(unfiltered.data['count'], 2)

    # ── Read safety ──────────────────────────────────────────────────

    def test_get_request_does_not_modify_records(self):
        _surgery(_patient(), self.st1)
        before = list(SurgeryHistory.objects.values_list('id', 'surgery_date', 'status'))
        self.client.get(URL, {'surgery_date_from': '2020-01-01', 'ordering': '-surgery_date'})
        after = list(SurgeryHistory.objects.values_list('id', 'surgery_date', 'status'))
        self.assertEqual(before, after)

    # ── Text search unaffected ────────────────────────────────────────

    def test_text_search_still_works_alongside_date_filter(self):
        target = Patient.objects.create(
            full_name='نام خاص جستجو', case_code='SEARCHME01', phone_number='09121112233',
        )
        s1 = _surgery(target, self.st1,
                      surgery_date=datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc))
        s2 = _surgery(_patient(), self.st1,
                      surgery_date=datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc))
        resp = self.client.get(URL, {
            'search': 'خاص جستجو',
            'surgery_date_from': '2025-01-01',
        })
        self.assertEqual(resp.status_code, 200)
        ids = [r['id'] for r in resp.data['results']]
        self.assertIn(s1.id, ids)
        self.assertNotIn(s2.id, ids)
