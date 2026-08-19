"""Targeted tests for Task 2 of 3 — Surgery list row-number column and
the SurgeryHistory detail page's general-information tab.

Covers: list row column (uses SurgeryHistory.pk, positioned before نام
بیمار, stable under filtering/sorting/pagination), removal of the old
Patient-derived case_code row, renamed general-information tab, exact
detail field order (via the static JS source, since rows render client
-side), clickable Patient link, Patient age fallback, previous Surgeries
list, Jalali Surgery date, and Doctor/Employee full-name labels.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from contacts.models import Doctor, DoctorSpecialty
from employees.models import Employee, GenderChoice, JobPosition
from surgeries.models import AnesthesiaType, Patient, SurgeryHistory, SurgeryType

User = get_user_model()

LIST_URL = '/admin/surgeries/surgeryhistory/'
API_URL = '/api/v2/surgeries/history/'

_ctr = [0]


def _next():
    _ctr[0] += 1
    return _ctr[0]


def make_position(name):
    pos, _ = JobPosition.objects.get_or_create(name=name, defaults={'is_active': True})
    return pos


def make_employee(position_name='کمک جراح', **kw):
    n = _next()
    defaults = {
        'full_name': f'کارمند {n}',
        'national_id': f'EMP{n:06d}',
        'gender': GenderChoice.MALE,
        'job_position': make_position(position_name),
        'start_date': datetime.date(2022, 1, 1),
        'personal_phone': f'0912{n:07d}',
        'emergency_contact_phone': f'0913{n:07d}',
    }
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def make_doctor(**kw):
    n = _next()
    specialty, _ = DoctorSpecialty.objects.get_or_create(name='تخصص تست دیتیل')
    defaults = {
        'full_name': f'دکتر {n}',
        'specialty': specialty,
        'phone_number': f'0914{n:07d}',
    }
    defaults.update(kw)
    return Doctor.objects.create(**defaults)


def make_surgery_type(**kw):
    n = _next()
    defaults = {'name': f'نوع عمل {n}', 'code': f'type_{n}', 'base_rate': Decimal('100000')}
    defaults.update(kw)
    return SurgeryType.objects.create(**defaults)


def make_patient(**kw):
    n = _next()
    defaults = {'full_name': f'بیمار {n}', 'case_code': f'CASE{n:05d}', 'phone_number': f'0915{n:07d}'}
    defaults.update(kw)
    return Patient.objects.create(**defaults)


def make_surgery(**kw):
    defaults = {
        'patient': make_patient(),
        'surgery_type': make_surgery_type(),
        'amount': Decimal('5000000'),
        'surgery_date': datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc),
    }
    defaults.update(kw)
    return SurgeryHistory.objects.create(**defaults)


def detail_page_url(pk):
    return f'/admin/surgeries/surgeryhistory/{pk}/detail/'


# ---------------------------------------------------------------------------
# 1. Surgery list row-number column
# ---------------------------------------------------------------------------

class SurgeryListRowNumberColumnTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_row', password='pass123', email='row@row.com')
        self.client.login(username='admin_row', password='pass123')

    def test_header_rendered_by_shared_columns_mapping_not_static_html(self):
        """Header cells are populated at runtime from the single COLUMNS
        array (see SurgeryListRowNumberJSTest) — the server-rendered page
        only provides the empty <tr> host, so header/row/skeleton/colspan
        can never drift out of sync with each other again."""
        response = self.client.get(LIST_URL)
        content = response.content.decode()
        self.assertIn('id="sh-thead-row"', content)

    def test_no_new_database_field_for_row_number(self):
        field_names = {f.name for f in SurgeryHistory._meta.get_fields()}
        self.assertNotIn('row_number', field_names)
        self.assertNotIn('sequence_number', field_names)


class SurgeryListRowNumberJSTest(TestCase):
    """The row/header/skeleton are all rendered client-side from one shared
    COLUMNS mapping; verify its order, count, use of the record's actual id
    (not a page-relative index), and that ملاحظات has been fully removed."""

    EXPECTED_HEADERS = [
        'ردیف', 'نام بیمار', 'کد ملی بیمار', 'شماره موبایل بیمار',
        'نام جراح/درمانگر', 'نوع عمل', 'تاریخ عمل', 'مبلغ عمل (تومان)',
        'سهم دانشگاه (۴۵٪)', 'کمیسیون مرکز جراحی (۵۵٪)',
        'وضعیت پرداخت', 'وضعیت عمل',
    ]

    def setUp(self):
        self.js_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'js' / 'surgery_history_list.js'
        self.js_source = self.js_path.read_text(encoding='utf-8')
        self.columns_block = self.js_source[
            self.js_source.find('var COLUMNS ='):self.js_source.find('function renderTableHeader')
        ]

    def test_row_number_uses_record_id_not_loop_index(self):
        self.assertIn('toPersian(r.id)', self.js_source)
        # Must not use forEach's own index for the row number.
        self.assertNotRegex(self.js_source, r'results\.forEach\(function \(r, i(dx)?\)')

    def test_column_order_and_count_matches_spec(self):
        headers = re.findall(r"header:\s*'([^']*)'", self.columns_block)
        self.assertEqual(headers, self.EXPECTED_HEADERS)

    def test_notes_column_fully_removed(self):
        self.assertNotIn('ملاحظات', self.js_source)
        self.assertNotIn('sh-td--notes', self.js_source)
        self.assertNotIn('r.description', self.js_source)

    def test_error_colspan_uses_shared_column_count(self):
        self.assertIn('colspan="\' + COLUMNS.length + \'"', self.js_source)

    def test_skeleton_row_built_from_same_columns_array(self):
        skeleton_fn_start = self.js_source.find('function showLoading')
        skeleton_fn_end = self.js_source.find('function hideLoading')
        skeleton_body = self.js_source[skeleton_fn_start:skeleton_fn_end]
        self.assertIn('col.skeleton', skeleton_body)
        self.assertIn('COLUMNS.map(function (col)', skeleton_body)
        # Old approach hardcoded twelve literal skeleton <td> cells inline;
        # the new approach has exactly one template string built via .map().
        self.assertEqual(skeleton_body.count('<div class="sh-skeleton'), 1)

    def test_header_and_row_and_skeleton_column_counts_match(self):
        header_count = len(re.findall(r"header:\s*'", self.columns_block))
        cell_fn_count = len(re.findall(r'cell:\s*function', self.columns_block))
        skeleton_count = len(re.findall(r"skeleton:\s*'", self.columns_block))
        self.assertEqual(header_count, 12)
        self.assertEqual(cell_fn_count, 12)
        self.assertEqual(skeleton_count, 12)

    def test_template_no_longer_hardcodes_header_cells(self):
        template_path = (
            Path(settings.BASE_DIR) / 'templates' / 'admin' / 'surgeries' / 'surgeryhistory' / 'change_list.html'
        )
        template_source = template_path.read_text(encoding='utf-8')
        self.assertNotIn('<th>ملاحظات</th>', template_source)
        self.assertNotIn('<th>نام بیمار</th>', template_source)


# ---------------------------------------------------------------------------
# 2. Row number stability under filtering/sorting/pagination
# ---------------------------------------------------------------------------

class SurgeryListRowNumberStabilityAPITest(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_stable', password='pass123', email='s@s.com')
        self.client.force_authenticate(user=self.superuser)

    def test_id_is_stable_across_ordering_and_filtering(self):
        s1 = make_surgery(surgery_date=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
        s2 = make_surgery(surgery_date=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc))

        resp_asc = self.client.get(API_URL, {'ordering': 'surgery_date'})
        resp_desc = self.client.get(API_URL, {'ordering': '-surgery_date'})
        resp_filtered = self.client.get(API_URL, {'status': s1.status})

        ids_by_pk = {r['id'] for r in resp_asc.data['results']} | {r['id'] for r in resp_desc.data['results']}
        self.assertIn(s1.pk, ids_by_pk)
        self.assertIn(s2.pk, ids_by_pk)

        # Same record keeps the same id regardless of ordering direction.
        asc_map = {r['id']: r for r in resp_asc.data['results']}
        desc_map = {r['id']: r for r in resp_desc.data['results']}
        self.assertEqual(asc_map[s1.pk]['id'], desc_map[s1.pk]['id'])
        self.assertEqual(asc_map[s1.pk]['id'], s1.pk)

        filtered_ids = {r['id'] for r in resp_filtered.data['results']}
        self.assertIn(s1.pk, filtered_ids)

    def test_sequential_creation_order(self):
        s1 = make_surgery()
        s2 = make_surgery()
        s3 = make_surgery()
        self.assertEqual(s2.pk, s1.pk + 1)
        self.assertEqual(s3.pk, s2.pk + 1)


# ---------------------------------------------------------------------------
# 3. Renamed detail tab
# ---------------------------------------------------------------------------

class DetailTabRenameTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_tab', password='pass123', email='tab@tab.com')
        self.client.login(username='admin_tab', password='pass123')
        self.surgery = make_surgery()

    def test_detail_page_shows_renamed_tab(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        self.assertContains(response, '>اطلاعات عمومی عمل<')
        self.assertNotContains(response, '>اطلاعات عمل<')

    def test_admin_form_uses_same_title(self):
        response = self.client.get(f'/admin/surgeries/surgeryhistory/{self.surgery.pk}/change/')
        self.assertContains(response, 'اطلاعات عمومی عمل')


# ---------------------------------------------------------------------------
# 4. Detail field order (JS source) + removal of old Patient row
# ---------------------------------------------------------------------------

class DetailFieldOrderTest(TestCase):
    def setUp(self):
        self.js_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'js' / 'surgery_history_detail.js'
        self.js_source = self.js_path.read_text(encoding='utf-8')

    def test_old_patient_case_code_row_removed(self):
        info_tab_start = self.js_source.find('function renderInfoTab')
        info_tab_end = self.js_source.find('function renderItemsTab')
        info_tab_body = self.js_source[info_tab_start:info_tab_end]
        self.assertNotIn('data.case_code', info_tab_body)

    def test_field_order_matches_spec(self):
        expected_labels_in_order = [
            'ردیف', 'بیمار', 'سن بیمار', 'نوع عمل', 'تاریخ عمل',
            'نام جراح/درمانگر', 'کمک اول جراح', 'کمک دوم جراح',
            'اسکراب', 'سیرکولر', 'متخصص بیهوشی', 'تکنسین بیهوشی',
            'نوع بیهوشی', 'ساعت شروع عمل', 'ساعت اتمام عمل',
            'اعمال جراحی انجام‌شده', 'مسئول اتاق عمل', 'خدمات',
        ]
        info_tab_start = self.js_source.find('function renderInfoTab')
        info_tab_end = self.js_source.find('function renderItemsTab')
        info_tab_body = self.js_source[info_tab_start:info_tab_end]

        positions = [info_tab_body.find(f"['{label}'") for label in expected_labels_in_order]
        for label, pos in zip(expected_labels_in_order, positions):
            self.assertNotEqual(pos, -1, f'{label} not found in renderInfoTab')
        self.assertEqual(positions, sorted(positions), 'Detail fields are not in the required order')

    def test_labels_use_correct_terminology(self):
        self.assertIn('نام جراح/درمانگر', self.js_source)
        self.assertNotIn('دکتر/درمانگر', self.js_source)
        self.assertIn('تاریخ عمل', self.js_source)
        info_tab_start = self.js_source.find('function renderInfoTab')
        info_tab_end = self.js_source.find('function renderItemsTab')
        self.assertNotIn("['تاریخ پرداخت'", self.js_source[info_tab_start:info_tab_end])


# ---------------------------------------------------------------------------
# 5. Patient link (backend-provided, named URL reversing)
# ---------------------------------------------------------------------------

class PatientLinkAPITest(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_plink', password='pass123', email='pl@pl.com')
        self.client.force_authenticate(user=self.superuser)

    def test_patient_admin_url_uses_named_reverse(self):
        surgery = make_surgery()
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        expected = reverse('admin:surgeries_patient_change', args=[surgery.patient_id])
        self.assertEqual(response.data['patient_admin_url'], expected)

    def test_patient_admin_url_page_is_reachable(self):
        surgery = make_surgery()
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        url = response.data['patient_admin_url']
        self.client.logout()
        self.client.force_authenticate(user=self.superuser)
        page = self.client.get(url)
        self.assertIn(page.status_code, (200, 301, 302))


# ---------------------------------------------------------------------------
# 6. Patient age fallback
# ---------------------------------------------------------------------------

class PatientAgeAPITest(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_age', password='pass123', email='age@age.com')
        self.client.force_authenticate(user=self.superuser)

    def test_patient_age_is_null_when_no_birth_data(self):
        surgery = make_surgery()
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        self.assertIsNone(response.data['patient_age'])

    def test_patient_model_has_no_age_field_added(self):
        field_names = {f.name for f in Patient._meta.get_fields()}
        self.assertNotIn('age', field_names)
        self.assertNotIn('gender', field_names)


# ---------------------------------------------------------------------------
# 7. Previous Surgeries
# ---------------------------------------------------------------------------

class PreviousSurgeriesAPITest(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_prev', password='pass123', email='pr@pr.com')
        self.client.force_authenticate(user=self.superuser)

    def test_no_other_surgeries_returns_empty_list(self):
        surgery = make_surgery()
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        self.assertEqual(response.data['previous_surgeries'], [])

    def test_other_surgeries_for_same_patient_listed_newest_first_excluding_current(self):
        patient = make_patient()
        older = make_surgery(patient=patient, surgery_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc))
        current = make_surgery(patient=patient, surgery_date=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))
        newer = make_surgery(patient=patient, surgery_date=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc))

        response = self.client.get(f'{API_URL}{current.pk}/')
        ids = [item['id'] for item in response.data['previous_surgeries']]

        self.assertNotIn(current.pk, ids)
        self.assertEqual(ids, [newer.pk, older.pk])

    def test_previous_surgery_uses_pk_and_named_detail_url(self):
        patient = make_patient()
        older = make_surgery(patient=patient, surgery_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc))
        current = make_surgery(patient=patient, surgery_date=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc))

        response = self.client.get(f'{API_URL}{current.pk}/')
        item = response.data['previous_surgeries'][0]
        self.assertEqual(item['id'], older.pk)
        self.assertEqual(item['detail_url'], reverse('admin:surgeries_surgeryhistory_detail', args=[older.pk]))

    def test_different_patients_surgeries_not_mixed_in(self):
        surgery = make_surgery()
        make_surgery()  # unrelated patient's surgery
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        self.assertEqual(response.data['previous_surgeries'], [])

    def test_no_duplicate_history_field_stored_on_models(self):
        patient_fields = {f.name for f in Patient._meta.get_fields()}
        self.assertNotIn('surgery_history_text', patient_fields)
        self.assertNotIn('previous_surgeries', patient_fields)


# ---------------------------------------------------------------------------
# 8. Doctor/Employee full-name labels via API (no raw FK ids in display fields)
# ---------------------------------------------------------------------------

class RoleNameFieldsAPITest(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_role', password='pass123', email='rl@rl.com')
        self.client.force_authenticate(user=self.superuser)

    def test_all_role_names_populated(self):
        assistant = make_employee('کمک جراح')
        second_assistant = make_employee('کمک جراح')
        scrub = make_employee('اسکراب')
        circulator = make_employee('سیرکولر')
        anesthesiologist = make_employee('متخصص بیهوشی')
        anesthesia_tech = make_employee('تکنسین بیهوشی')
        or_manager = make_employee('خدمات')
        service = make_employee('خدمات')
        anesthesia_type = AnesthesiaType.objects.create(name='بیهوشی تست دیتیل')
        clinical_doctor = make_doctor()

        surgery = make_surgery(
            clinical_doctor=clinical_doctor,
            assistant_surgeon=assistant,
            second_assistant_surgeon=second_assistant,
            scrub_employee=scrub,
            circulator_employee=circulator,
            anesthesiologist=anesthesiologist,
            anesthesia_technician=anesthesia_tech,
            anesthesia_type=anesthesia_type,
            operating_room_manager=or_manager,
            service_employee=service,
        )
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        data = response.data

        self.assertEqual(data['doctor_name'], clinical_doctor.full_name)
        self.assertEqual(data['assistant_surgeon_name'], assistant.full_name)
        self.assertEqual(data['second_assistant_surgeon_name'], second_assistant.full_name)
        self.assertEqual(data['scrub_employee_name'], scrub.full_name)
        self.assertEqual(data['circulator_employee_name'], circulator.full_name)
        self.assertEqual(data['anesthesiologist_name'], anesthesiologist.full_name)
        self.assertEqual(data['anesthesia_technician_name'], anesthesia_tech.full_name)
        self.assertEqual(data['anesthesia_type_name'], anesthesia_type.name)
        self.assertEqual(data['operating_room_manager_name'], or_manager.full_name)
        self.assertEqual(data['service_employee_name'], service.full_name)

        # No raw FK id exposed for the new role fields.
        for forbidden_key in (
            'assistant_surgeon', 'second_assistant_surgeon', 'scrub_employee',
            'circulator_employee', 'anesthesiologist', 'anesthesia_technician',
            'anesthesia_type', 'operating_room_manager', 'service_employee',
        ):
            self.assertNotIn(forbidden_key, data)

    def test_unset_roles_are_null(self):
        surgery = make_surgery()
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        self.assertIsNone(response.data['assistant_surgeon_name'])
        self.assertIsNone(response.data['anesthesia_type_name'])


# ---------------------------------------------------------------------------
# 9. Jalali Surgery date on the detail page's static markup path
# ---------------------------------------------------------------------------

class SurgeryDateFormattingTest(TestCase):
    def test_detail_js_uses_persian_format_helper_for_surgery_date(self):
        js_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'js' / 'surgery_history_detail.js'
        source = js_path.read_text(encoding='utf-8')
        info_tab_start = source.find('function renderInfoTab')
        info_tab_end = source.find('function renderItemsTab')
        self.assertIn('formatDate(data.surgery_date)', source[info_tab_start:info_tab_end])
