"""Targeted tests for Task 3 of 3 — new شرح عمل detail tab, removal of the
visible یادداشت‌ها tab, and the procedure-description fields in the Surgery
add/edit form.

Covers: final tab order, شرح عمل tab contents/order, reuse of Task 1 fields
(no duplicates), safe multi-line escaping, admin-form field labels/sizes,
old Notes input no longer visible (but description column/data preserved),
detail API field coverage, and cache-busting version bump.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from contacts.models import Doctor, DoctorSpecialty
from employees.models import Employee, GenderChoice, JobPosition
from surgeries.models import AnesthesiaType, Patient, SurgeryHistory, SurgeryType

User = get_user_model()

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
    specialty, _ = DoctorSpecialty.objects.get_or_create(name='تخصص تست شرح عمل')
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


def change_page_url(pk):
    return f'/admin/surgeries/surgeryhistory/{pk}/change/'


ADD_URL = '/admin/surgeries/surgeryhistory/add/'


# ---------------------------------------------------------------------------
# 1. Final detail-tab order + removal of یادداشت‌ها
# ---------------------------------------------------------------------------

class DetailTabOrderTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_taborder', password='pass123', email='to@to.com')
        self.client.login(username='admin_taborder', password='pass123')
        self.surgery = make_surgery()

    def test_notes_tab_removed(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        content = response.content.decode()
        self.assertNotIn('یادداشت‌ها', content)
        self.assertNotIn('data-tab="notes"', content)
        self.assertNotIn('id="shd-panel-notes"', content)

    def test_procedure_tab_present(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        content = response.content.decode()
        self.assertIn('>شرح عمل<', content)
        self.assertIn('data-tab="procedure"', content)
        self.assertIn('id="shd-panel-procedure"', content)

    def test_items_and_commission_tabs_still_present(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        content = response.content.decode()
        self.assertIn('data-tab="items"', content)
        self.assertIn('data-tab="commission"', content)

    def test_tab_order_is_exact(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        content = response.content.decode()
        tab_bar_start = content.find('shd-tab-bar')
        tab_bar_end = content.find('</div>', tab_bar_start)
        tab_bar_html = content[tab_bar_start:tab_bar_end]
        order = re.findall(r'data-tab="([a-z]+)"', tab_bar_html)
        self.assertEqual(order, ['info', 'procedure', 'items', 'commission'])

    def test_panel_order_matches_tab_order(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        content = response.content.decode()
        positions = {
            tab: content.find(f'id="shd-panel-{tab}"')
            for tab in ('info', 'procedure', 'items', 'commission')
        }
        for tab, pos in positions.items():
            self.assertNotEqual(pos, -1, f'panel for {tab} not found')
        ordered = sorted(positions, key=positions.get)
        self.assertEqual(ordered, ['info', 'procedure', 'items', 'commission'])


# ---------------------------------------------------------------------------
# 2. Cache-busting version bump
# ---------------------------------------------------------------------------

class DetailScriptVersionTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_ver', password='pass123', email='v@v.com')
        self.client.login(username='admin_ver', password='pass123')
        self.surgery = make_surgery()

    def test_detail_js_has_cache_busting_query_param(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        content = response.content.decode()
        match = re.search(r'admin/js/surgery_history_detail\.js\?v=(\d+)', content)
        self.assertIsNotNone(match, 'surgery_history_detail.js is missing a ?v= cache-busting param')
        self.assertNotEqual(match.group(1), '0')

    def test_detail_css_has_cache_busting_query_param(self):
        response = self.client.get(detail_page_url(self.surgery.pk))
        content = response.content.decode()
        match = re.search(r'admin/css/surgery_history_detail\.css\?v=(\d+)', content)
        self.assertIsNotNone(match)


# ---------------------------------------------------------------------------
# 3. شرح عمل tab field order (JS source) — no duplicate fields created
# ---------------------------------------------------------------------------

class ProcedureTabFieldOrderTest(TestCase):
    def setUp(self):
        self.js_path = Path(settings.BASE_DIR) / 'static' / 'admin' / 'js' / 'surgery_history_detail.js'
        self.js_source = self.js_path.read_text(encoding='utf-8')
        start = self.js_source.find('function renderProcedureTab')
        end = self.js_source.find('function renderTimeline')
        self.procedure_fn_body = self.js_source[start:end]

    def test_render_notes_tab_removed(self):
        self.assertNotIn('function renderNotesTab', self.js_source)
        self.assertNotIn("case 'notes'", self.js_source)
        self.assertNotIn('shd-notes-card', self.js_source)

    def test_field_order_matches_spec(self):
        expected_labels_in_order = [
            'نام بیمار', 'نام جراح/درمانگر', 'کمک اول جراح', 'کمک دوم جراح',
            'بیهوشی‌دهنده', 'نوع بیهوشی', 'تشخیص بعد از عمل', 'شرح عمل و مشاهدات',
        ]
        positions = [self.procedure_fn_body.find(f"['{label}'") for label in expected_labels_in_order]
        for label, pos in zip(expected_labels_in_order, positions):
            self.assertNotEqual(pos, -1, f'{label} not found in renderProcedureTab')
        self.assertEqual(positions, sorted(positions))

    def test_uses_existing_data_fields_not_new_ones(self):
        self.assertIn('data.patient_name', self.procedure_fn_body)
        self.assertIn('data.doctor_name', self.procedure_fn_body)
        self.assertIn('data.assistant_surgeon_name', self.procedure_fn_body)
        self.assertIn('data.second_assistant_surgeon_name', self.procedure_fn_body)
        self.assertIn('data.anesthesiologist_name', self.procedure_fn_body)
        self.assertIn('data.anesthesia_type_name', self.procedure_fn_body)
        self.assertIn('data.postoperative_diagnosis', self.procedure_fn_body)
        self.assertIn('data.operation_description', self.procedure_fn_body)

    def test_anesthesiologist_relabeled_beside_original_field(self):
        # Label text differs from the admin form's "متخصص بیهوشی" but reads
        # the SAME anesthesiologist_name field — no new model field.
        self.assertIn('بیهوشی‌دهنده', self.procedure_fn_body)
        self.assertNotIn('متخصص بیهوشی', self.procedure_fn_body)

    def test_multiline_fields_are_html_escaped_not_raw_innerhtml(self):
        multiline_fn_start = self.js_source.find('function multilineOrMuted')
        multiline_fn_end = self.js_source.find('function renderProcedureTab')
        multiline_body = self.js_source[multiline_fn_start:multiline_fn_end]
        self.assertIn('escapeHtml(value)', multiline_body)
        self.assertIn('shd-pre-wrap', multiline_body)


# ---------------------------------------------------------------------------
# 4. Admin add/edit form: description no longer visible, new fields present
# ---------------------------------------------------------------------------

class AdminFormFieldsTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_form3', password='pass123', email='f3@f3.com')
        self.client.login(username='admin_form3', password='pass123')

    def test_description_textarea_not_in_visible_add_form(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        self.assertNotIn('id="id_description"', content)

    def test_description_textarea_not_in_visible_change_form(self):
        surgery = make_surgery(description='یادداشت قدیمی مهم')
        response = self.client.get(change_page_url(surgery.pk))
        content = response.content.decode()
        self.assertNotIn('id="id_description"', content)

    def test_required_procedure_fields_present_in_add_form(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        for field_id in (
            'id_assistant_surgeon', 'id_second_assistant_surgeon',
            'id_anesthesiologist', 'id_anesthesia_type',
            'id_postoperative_diagnosis', 'id_operation_description',
        ):
            self.assertIn(f'id="{field_id}"', content)

    def test_anesthesiologist_label_is_متخصص_بیهوشی_in_admin_form(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        label_start = content.find('for="id_anesthesiologist"')
        label_snippet = content[label_start:label_start + 120]
        self.assertIn('متخصص بیهوشی', label_snippet)

    def test_operation_description_textarea_larger_than_diagnosis(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        # rows="N" precedes id="..." within the <textarea> tag itself, so
        # look backward from the id attribute (the label's for="id_..."
        # appears earlier on the page and has no rows attribute at all).
        diag_id_pos = content.find('id="id_postoperative_diagnosis"')
        diag_tag = content[max(0, diag_id_pos - 150):diag_id_pos]
        op_id_pos = content.find('id="id_operation_description"')
        op_tag = content[max(0, op_id_pos - 150):op_id_pos]
        diag_rows = re.search(r'rows="(\d+)"', diag_tag)
        op_rows = re.search(r'rows="(\d+)"', op_tag)
        self.assertIsNotNone(diag_rows)
        self.assertIsNotNone(op_rows)
        self.assertGreater(int(op_rows.group(1)), int(diag_rows.group(1)))


# ---------------------------------------------------------------------------
# 5. Old description data preserved (no destructive migration)
# ---------------------------------------------------------------------------

class DescriptionDataPreservedTest(TestCase):
    def test_existing_description_value_untouched_by_unrelated_save(self):
        surgery = make_surgery(description='یادداشت تاریخی حساس')
        surgery.status = surgery.status  # no-op change
        surgery.save()
        surgery.refresh_from_db()
        self.assertEqual(surgery.description, 'یادداشت تاریخی حساس')

    def test_description_field_still_exists_on_model(self):
        field_names = {f.name for f in SurgeryHistory._meta.get_fields()}
        self.assertIn('description', field_names)

    def test_description_still_present_in_api_response(self):
        surgery = make_surgery(description='یادداشت در دسترس API')
        superuser = User.objects.create_superuser(username='admin_api_desc', password='pass123', email='ad@ad.com')
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=superuser)
        response = client.get(f'{API_URL}{surgery.pk}/')
        self.assertEqual(response.data['description'], 'یادداشت در دسترس API')

    def test_edit_form_save_without_description_field_preserves_old_value(self):
        surgery = make_surgery(description='یادداشت باید باقی بماند')
        User.objects.create_superuser(username='admin_preserve', password='pass123', email='pr@pr.com')
        from django.test import Client
        client = Client()
        client.login(username='admin_preserve', password='pass123')
        data = {
            'patient': str(surgery.patient_id),
            'surgery_type': str(surgery.surgery_type_id),
            'surgery_date': '1404/03/11',
            'amount': str(surgery.amount),
            'payment_status': surgery.payment_status,
            'status': surgery.status,
        }
        response = client.post(change_page_url(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertEqual(surgery.description, 'یادداشت باید باقی بماند')


# ---------------------------------------------------------------------------
# 6. Detail API provides all values required by the شرح عمل tab
# ---------------------------------------------------------------------------

class ProcedureTabAPIFieldsTest(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_procapi', password='pass123', email='pa@pa.com')
        self.client.force_authenticate(user=self.superuser)

    def test_all_required_fields_present_and_populated(self):
        assistant = make_employee('کمک جراح')
        second_assistant = make_employee('کمک جراح')
        anesthesiologist = make_employee('متخصص بیهوشی')
        anesthesia_type = AnesthesiaType.objects.create(name='بیهوشی تست شرح عمل')
        clinical_doctor = make_doctor()

        surgery = make_surgery(
            clinical_doctor=clinical_doctor,
            assistant_surgeon=assistant,
            second_assistant_surgeon=second_assistant,
            anesthesiologist=anesthesiologist,
            anesthesia_type=anesthesia_type,
            postoperative_diagnosis='تشخیص نمونه',
            operation_description='شرح نمونه شامل\nچند خط متن',
        )
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        data = response.data

        self.assertEqual(data['patient_name'], surgery.patient.full_name)
        self.assertEqual(data['doctor_name'], clinical_doctor.full_name)
        self.assertEqual(data['assistant_surgeon_name'], assistant.full_name)
        self.assertEqual(data['second_assistant_surgeon_name'], second_assistant.full_name)
        self.assertEqual(data['anesthesiologist_name'], anesthesiologist.full_name)
        self.assertEqual(data['anesthesia_type_name'], anesthesia_type.name)
        self.assertEqual(data['postoperative_diagnosis'], 'تشخیص نمونه')
        self.assertEqual(data['operation_description'], 'شرح نمونه شامل\nچند خط متن')

    def test_missing_values_are_null_or_empty_consistently(self):
        surgery = make_surgery()
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        data = response.data
        self.assertIsNone(data['assistant_surgeon_name'])
        self.assertIsNone(data['second_assistant_surgeon_name'])
        self.assertIsNone(data['anesthesiologist_name'])
        self.assertIsNone(data['anesthesia_type_name'])
        self.assertEqual(data['postoperative_diagnosis'], '')
        self.assertEqual(data['operation_description'], '')

    def test_unrelated_api_fields_unchanged(self):
        surgery = make_surgery(amount=Decimal('1234567'))
        response = self.client.get(f'{API_URL}{surgery.pk}/')
        self.assertEqual(response.data['amount'], '1234567.00')
        self.assertIn('center_commission_income_amount', response.data)
        self.assertIn('previous_surgeries', response.data)
