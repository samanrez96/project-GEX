"""Targeted tests for Task 1 of 3 — Surgery general-information fields.

Covers: new SurgeryHistory fields, Employee role fields (any active
Employee, no JobPosition restriction), Doctor-only second assistant
selection, AnesthesiaType add/delete/deactivate/reactivate, Jalali
date-only Surgery date, start/end time validation, admin add/edit field
order, and preservation of existing Surgery relations.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from contacts.models import Doctor, DoctorSpecialty
from employees.models import Employee, GenderChoice, JobPosition
from surgeries.models import AnesthesiaType, Patient, SurgeryHistory, SurgeryType

User = get_user_model()

_ctr = [0]


def _next():
    _ctr[0] += 1
    return _ctr[0]


def make_position(name):
    pos, _ = JobPosition.objects.get_or_create(name=name, defaults={'is_active': True})
    return pos


def make_employee(position_name='کمک جراح', is_active=True, **kw):
    n = _next()
    defaults = {
        'full_name': f'کارمند {n}',
        'national_id': f'EMP{n:06d}',
        'gender': GenderChoice.MALE,
        'job_position': make_position(position_name),
        'start_date': datetime.date(2022, 1, 1),
        'personal_phone': f'0912{n:07d}',
        'emergency_contact_phone': f'0913{n:07d}',
        'is_active': is_active,
    }
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def make_doctor(is_active=True, **kw):
    n = _next()
    specialty, _ = DoctorSpecialty.objects.get_or_create(name='تخصص تست عمومی')
    defaults = {
        'full_name': f'دکتر {n}',
        'specialty': specialty,
        'phone_number': f'0914{n:07d}',
        'is_active': is_active,
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


CHANGE_URL_TPL = '/admin/surgeries/surgeryhistory/{}/change/'
ADD_URL = '/admin/surgeries/surgeryhistory/add/'


def base_post_data(surgery):
    """Minimal valid POST body for the SurgeryHistoryAdminForm, using
    Jalali digits for surgery_date since JalaliFormDateForDateTimeField
    is now wired for that field."""
    return {
        'patient': str(surgery.patient_id),
        'surgery_type': str(surgery.surgery_type_id),
        'surgery_date': '1404/03/11',
        'amount': str(surgery.amount),
        'payment_status': surgery.payment_status,
        'status': surgery.status,
    }


# ---------------------------------------------------------------------------
# 1. New SurgeryHistory fields — model level
# ---------------------------------------------------------------------------

class SurgeryHistoryNewFieldsModelTest(TestCase):
    def test_legacy_style_creation_without_new_fields_still_works(self):
        surgery = make_surgery()
        surgery.refresh_from_db()
        self.assertIsNone(surgery.assistant_surgeon)
        self.assertIsNone(surgery.second_assistant_surgeon)
        self.assertIsNone(surgery.scrub_employee)
        self.assertIsNone(surgery.circulator_employee)
        self.assertIsNone(surgery.anesthesiologist)
        self.assertIsNone(surgery.anesthesia_technician)
        self.assertIsNone(surgery.anesthesia_type)
        self.assertIsNone(surgery.operating_room_manager)
        self.assertIsNone(surgery.service_employee)
        self.assertIsNone(surgery.surgery_start_time)
        self.assertIsNone(surgery.surgery_end_time)
        self.assertEqual(surgery.postoperative_diagnosis, '')
        self.assertEqual(surgery.operation_description, '')

    def test_all_new_fields_can_be_set_and_persisted(self):
        assistant = make_employee('کمک جراح')
        second_assistant = make_employee('کمک جراح')
        scrub = make_employee('اسکراب')
        circulator = make_employee('سیرکولر')
        anesthesiologist = make_employee('متخصص بیهوشی')
        anesthesia_tech = make_employee('تکنسین بیهوشی')
        or_manager = make_employee('خدمات')  # any position allowed
        service = make_employee('خدمات')
        anesthesia_type = AnesthesiaType.objects.create(name='بیهوشی عمومی تست')

        surgery = make_surgery(
            assistant_surgeon=assistant,
            second_assistant_surgeon=second_assistant,
            scrub_employee=scrub,
            circulator_employee=circulator,
            anesthesiologist=anesthesiologist,
            anesthesia_technician=anesthesia_tech,
            anesthesia_type=anesthesia_type,
            operating_room_manager=or_manager,
            service_employee=service,
            surgery_start_time=datetime.time(9, 0),
            surgery_end_time=datetime.time(11, 30),
            postoperative_diagnosis='تشخیص تست',
            operation_description='شرح تست',
        )
        surgery.refresh_from_db()
        self.assertEqual(surgery.assistant_surgeon_id, assistant.pk)
        self.assertEqual(surgery.second_assistant_surgeon_id, second_assistant.pk)
        self.assertEqual(surgery.scrub_employee_id, scrub.pk)
        self.assertEqual(surgery.circulator_employee_id, circulator.pk)
        self.assertEqual(surgery.anesthesiologist_id, anesthesiologist.pk)
        self.assertEqual(surgery.anesthesia_technician_id, anesthesia_tech.pk)
        self.assertEqual(surgery.anesthesia_type_id, anesthesia_type.pk)
        self.assertEqual(surgery.operating_room_manager_id, or_manager.pk)
        self.assertEqual(surgery.service_employee_id, service.pk)
        self.assertEqual(surgery.surgery_start_time, datetime.time(9, 0))
        self.assertEqual(surgery.surgery_end_time, datetime.time(11, 30))
        self.assertEqual(surgery.postoperative_diagnosis, 'تشخیص تست')
        self.assertEqual(surgery.operation_description, 'شرح تست')

    def test_deleting_employee_sets_role_fields_null_not_cascade(self):
        assistant = make_employee('کمک جراح')
        surgery = make_surgery(assistant_surgeon=assistant)
        assistant.delete()
        surgery.refresh_from_db()
        self.assertTrue(SurgeryHistory.objects.filter(pk=surgery.pk).exists())
        self.assertIsNone(surgery.assistant_surgeon)

    def test_deleting_employee_sets_second_assistant_null_not_cascade(self):
        second_assistant = make_employee('کمک جراح')
        surgery = make_surgery(second_assistant_surgeon=second_assistant)
        second_assistant.delete()
        surgery.refresh_from_db()
        self.assertTrue(SurgeryHistory.objects.filter(pk=surgery.pk).exists())
        self.assertIsNone(surgery.second_assistant_surgeon)

    def test_clinical_doctor_label_relabeled(self):
        field = SurgeryHistory._meta.get_field('clinical_doctor')
        self.assertEqual(field.verbose_name, 'نام جراح/درمانگر')

    def test_surgery_date_label_relabeled(self):
        field = SurgeryHistory._meta.get_field('surgery_date')
        self.assertEqual(field.verbose_name, 'تاریخ عمل')


# ---------------------------------------------------------------------------
# 2. AnesthesiaType model
# ---------------------------------------------------------------------------

class AnesthesiaTypeModelTest(TestCase):
    def test_create_and_str(self):
        at = AnesthesiaType.objects.create(name='بیهوشی موضعی')
        self.assertEqual(str(at), 'بیهوشی موضعی')
        self.assertTrue(at.is_active)

    def test_name_unique(self):
        AnesthesiaType.objects.create(name='بیهوشی نخاعی')
        with self.assertRaises(Exception):
            AnesthesiaType.objects.create(name='بیهوشی نخاعی')

    def test_verbose_names(self):
        self.assertEqual(AnesthesiaType._meta.verbose_name, 'نوع بیهوشی')
        self.assertEqual(AnesthesiaType._meta.verbose_name_plural, 'انواع بیهوشی')


# ---------------------------------------------------------------------------
# 3. Start/end time validation
# ---------------------------------------------------------------------------

class SurgeryTimeValidationTest(TestCase):
    def test_end_before_start_rejected(self):
        surgery = make_surgery(surgery_start_time=datetime.time(11, 0), surgery_end_time=datetime.time(9, 0))
        with self.assertRaises(ValidationError) as ctx:
            surgery.full_clean()
        self.assertIn('surgery_end_time', ctx.exception.message_dict)
        self.assertEqual(
            ctx.exception.message_dict['surgery_end_time'][0],
            'ساعت اتمام عمل نمی‌تواند قبل از ساعت شروع عمل باشد.',
        )

    def test_end_after_start_accepted(self):
        surgery = make_surgery(surgery_start_time=datetime.time(9, 0), surgery_end_time=datetime.time(11, 0))
        surgery.full_clean()  # should not raise

    def test_only_start_time_set_accepted(self):
        surgery = make_surgery(surgery_start_time=datetime.time(9, 0))
        surgery.full_clean()

    def test_equal_times_accepted(self):
        surgery = make_surgery(surgery_start_time=datetime.time(9, 0), surgery_end_time=datetime.time(9, 0))
        surgery.full_clean()

    def test_end_before_start_rejected_via_admin_post(self):
        superuser = User.objects.create_superuser(username='admin_time', password='pass123', email='t@t.com')
        self.client.login(username='admin_time', password='pass123')
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['surgery_start_time'] = '11:00:00'
        data['surgery_end_time'] = '09:00:00'
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 200)  # re-rendered with errors, not redirected
        self.assertContains(response, 'ساعت اتمام عمل نمی‌تواند قبل از ساعت شروع عمل باشد.')


# ---------------------------------------------------------------------------
# 4. Employee role fields: any active Employee, no JobPosition restriction
#    (form-level, incl. forged POST)
# ---------------------------------------------------------------------------

class EmployeeRoleFieldsUseAllEmployeesTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_pos', password='pass123', email='p@p.com')
        self.client.login(username='admin_pos', password='pass123')

    def test_assistant_surgeon_autocomplete_search_includes_any_active_position(self):
        # These are duties during surgery, not separate jobs — the AJAX
        # search (AutocompleteSelect only pre-renders the selected option;
        # everything else is fetched via /admin/autocomplete/) must return
        # every active Employee regardless of JobPosition.
        one = make_employee('اسکراب', full_name='جستجوپذیر یک')
        other = make_employee('کمک جراح', full_name='جستجوپذیر دو')
        response = self.client.get('/admin/autocomplete/', {
            'app_label': 'surgeries',
            'model_name': 'surgeryhistory',
            'field_name': 'assistant_surgeon',
            'term': 'جستجوپذیر',
        })
        self.assertEqual(response.status_code, 200)
        result_ids = {r['id'] for r in response.json()['results']}
        self.assertIn(str(one.pk), result_ids)
        self.assertIn(str(other.pk), result_ids)

    def test_post_with_any_active_job_position_accepted(self):
        # No more "این کارمند دارای پوزیشن «...» نیست." validation — any
        # active Employee, whatever their JobPosition, may be assigned.
        employee = make_employee('اسکراب')
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['assistant_surgeon'] = str(employee.pk)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertEqual(surgery.assistant_surgeon_id, employee.pk)

    def test_blank_role_fields_accepted(self):
        surgery = make_surgery()
        data = base_post_data(surgery)
        # All 7 employee role fields + second_assistant_surgeon + anesthesia_type
        # intentionally omitted/blank.
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertIsNone(surgery.assistant_surgeon)
        self.assertIsNone(surgery.scrub_employee)
        self.assertIsNone(surgery.circulator_employee)
        self.assertIsNone(surgery.anesthesiologist)
        self.assertIsNone(surgery.anesthesia_technician)
        self.assertIsNone(surgery.operating_room_manager)
        self.assertIsNone(surgery.service_employee)
        self.assertIsNone(surgery.second_assistant_surgeon)
        self.assertIsNone(surgery.anesthesia_type)

    def test_forged_post_inactive_employee_rejected(self):
        inactive = make_employee('کمک جراح', is_active=False)
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['assistant_surgeon'] = str(inactive.pk)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'این کارمند غیرفعال است و برای انتساب جدید قابل انتخاب نیست.')

    def test_correct_position_accepted(self):
        right = make_employee('کمک جراح')
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['assistant_surgeon'] = str(right.pk)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertEqual(surgery.assistant_surgeon_id, right.pk)

    def test_operating_room_manager_accepts_any_position(self):
        any_position_employee = make_employee('خدمات')
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['operating_room_manager'] = str(any_position_employee.pk)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertEqual(surgery.operating_room_manager_id, any_position_employee.pk)

    def test_existing_assignment_stays_valid_after_position_changes(self):
        employee = make_employee('کمک جراح')
        surgery = make_surgery(assistant_surgeon=employee)
        # Position changes after the surgery was saved.
        employee.job_position = make_position('اسکراب')
        employee.save(update_fields=['job_position'])

        data = base_post_data(surgery)
        data['assistant_surgeon'] = str(employee.pk)  # unchanged value resubmitted
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertEqual(surgery.assistant_surgeon_id, employee.pk)

    def test_no_duplicate_job_position_created(self):
        make_employee('کمک جراح')
        count_before = JobPosition.objects.filter(name='کمک جراح').count()
        self.client.get(ADD_URL)
        count_after = JobPosition.objects.filter(name='کمک جراح').count()
        self.assertEqual(count_before, count_after)
        self.assertEqual(count_after, 1)


# ---------------------------------------------------------------------------
# 4b. Autocomplete/search widget config for the role fields
# ---------------------------------------------------------------------------

class EmployeeRoleAutocompleteWidgetTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_ac', password='pass123', email='ac@ac.com')
        self.client.login(username='admin_ac', password='pass123')

    def test_employee_role_fields_render_as_select2_autocomplete(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        for field_id in (
            'id_assistant_surgeon', 'id_scrub_employee', 'id_circulator_employee',
            'id_anesthesiologist', 'id_anesthesia_technician',
            'id_operating_room_manager', 'id_service_employee',
            'id_second_assistant_surgeon',
        ):
            start = content.find(f'id="{field_id}"')
            self.assertNotEqual(start, -1, f'{field_id} not found')
            tag = content[start:content.find('</select>', start)]
            self.assertIn('admin-autocomplete', tag, f'{field_id} is not a Select2 autocomplete widget')
            self.assertIn('data-ajax--url', tag, f'{field_id} has no AJAX search endpoint configured')

    def test_employee_role_autocomplete_targets_employee_model(self):
        field = SurgeryHistory._meta.get_field('assistant_surgeon')
        self.assertEqual(field.remote_field.model.__name__, 'Employee')

    def test_second_assistant_autocomplete_targets_employee_model(self):
        field = SurgeryHistory._meta.get_field('second_assistant_surgeon')
        self.assertEqual(field.remote_field.model.__name__, 'Employee')


# ---------------------------------------------------------------------------
# 5. Second assistant surgeon: Employee-based, same as the other role fields
# ---------------------------------------------------------------------------

class SecondAssistantSurgeonEmployeeTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_2a', password='pass123', email='2a@2a.com')
        self.client.login(username='admin_2a', password='pass123')

    def test_field_present_on_form(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        self.assertIn('id_second_assistant_surgeon', content)

    def test_active_employee_of_any_position_accepted(self):
        employee = make_employee('اسکراب')
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['second_assistant_surgeon'] = str(employee.pk)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertEqual(surgery.second_assistant_surgeon_id, employee.pk)

    def test_inactive_employee_rejected_for_new_assignment(self):
        employee = make_employee('کمک جراح', is_active=False)
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['second_assistant_surgeon'] = str(employee.pk)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'این کارمند غیرفعال است و برای انتساب جدید قابل انتخاب نیست.')

    def test_doctor_pk_cannot_be_forged_into_employee_field(self):
        """A Doctor pk that happens to collide with no Employee row must be
        rejected as an invalid choice (proves the field resolves against the
        Employee table, not Doctor)."""
        doctor = make_doctor()
        # Guarantee no Employee shares this pk in this test's data.
        from employees.models import Employee
        self.assertFalse(Employee.objects.filter(pk=doctor.pk).exists())
        surgery = make_surgery()
        data = base_post_data(surgery)
        data['second_assistant_surgeon'] = str(doctor.pk)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 200)

    def test_blank_second_assistant_accepted(self):
        surgery = make_surgery()
        data = base_post_data(surgery)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        self.assertIsNone(surgery.second_assistant_surgeon)

    def test_detail_api_displays_employee_full_name(self):
        employee = make_employee('کمک جراح', full_name='کارمند نمایش‌داده‌شده')
        surgery = make_surgery(second_assistant_surgeon=employee)
        self.client.logout()
        api_user = User.objects.create_user(username='api_2a', password='pass123')
        self.client.force_login(api_user)
        response = self.client.get(f'/api/v1/surgeries/history/{surgery.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['second_assistant_surgeon_name'], 'کارمند نمایش‌داده‌شده')


# ---------------------------------------------------------------------------
# 6. AnesthesiaType add/delete/deactivate/reactivate endpoints
# ---------------------------------------------------------------------------

class AnesthesiaTypeEndpointsTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_at', password='pass123', email='at@at.com')
        self.client.login(username='admin_at', password='pass123')

    def test_create_unused_type(self):
        response = self.client.post(
            '/admin/surgeries/surgeryhistory/anesthesia-type/create/',
            data='{"name": "بیهوشی جدید"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(AnesthesiaType.objects.filter(name='بیهوشی جدید').exists())

    def test_create_duplicate_rejected(self):
        AnesthesiaType.objects.create(name='بیهوشی تکراری')
        response = self.client.post(
            '/admin/surgeries/surgeryhistory/anesthesia-type/create/',
            data='{"name": "بیهوشی تکراری"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_delete_unused_type_hard_deletes(self):
        at = AnesthesiaType.objects.create(name='بیهوشی بدون استفاده')
        response = self.client.post(f'/admin/surgeries/surgeryhistory/anesthesia-type/{at.pk}/delete/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(AnesthesiaType.objects.filter(pk=at.pk).exists())

    def test_delete_used_type_blocked(self):
        at = AnesthesiaType.objects.create(name='بیهوشی در حال استفاده')
        make_surgery(anesthesia_type=at)
        response = self.client.post(f'/admin/surgeries/surgeryhistory/anesthesia-type/{at.pk}/delete/')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'anesthesia_type_in_use')
        self.assertTrue(AnesthesiaType.objects.filter(pk=at.pk).exists())

    def test_deactivate_used_type_keeps_existing_records(self):
        at = AnesthesiaType.objects.create(name='بیهوشی برای غیرفعال‌سازی')
        surgery = make_surgery(anesthesia_type=at)
        response = self.client.post(f'/admin/surgeries/surgeryhistory/anesthesia-type/{at.pk}/deactivate/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        at.refresh_from_db()
        self.assertFalse(at.is_active)
        surgery.refresh_from_db()
        self.assertEqual(surgery.anesthesia_type_id, at.pk)

    def test_inactive_type_excluded_from_new_assignment_dropdown(self):
        at = AnesthesiaType.objects.create(name='بیهوشی غیرفعال شده', is_active=False)
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        select_start = content.find('id_anesthesia_type')
        select_html = content[select_start:content.find('</select>', select_start)]
        self.assertNotIn(f'value="{at.pk}"', select_html)

    def test_inactive_type_still_visible_on_existing_surgery(self):
        at = AnesthesiaType.objects.create(name='بیهوشی غیرفعال با رکورد')
        surgery = make_surgery(anesthesia_type=at)
        at.is_active = False
        at.save(update_fields=['is_active'])
        response = self.client.get(CHANGE_URL_TPL.format(surgery.pk))
        content = response.content.decode()
        select_start = content.find('id_anesthesia_type')
        select_html = content[select_start:content.find('</select>', select_start)]
        self.assertIn(f'value="{at.pk}"', select_html)

    def test_reactivate_type(self):
        at = AnesthesiaType.objects.create(name='بیهوشی برای فعال‌سازی مجدد', is_active=False)
        response = self.client.post(f'/admin/surgeries/surgeryhistory/anesthesia-type/{at.pk}/activate/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        at.refresh_from_db()
        self.assertTrue(at.is_active)

    def test_get_request_rejected_for_mutation_endpoints(self):
        response = self.client.get('/admin/surgeries/surgeryhistory/anesthesia-type/create/')
        self.assertEqual(response.status_code, 405)

    def test_unauthenticated_request_rejected(self):
        self.client.logout()
        response = self.client.post(
            '/admin/surgeries/surgeryhistory/anesthesia-type/create/',
            data='{"name": "بدون احراز هویت"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)


# ---------------------------------------------------------------------------
# 7. Jalali date-only Surgery date
# ---------------------------------------------------------------------------

class SurgeryDateJalaliDateOnlyTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_date', password='pass123', email='d@d.com')
        self.client.login(username='admin_date', password='pass123')

    def test_add_form_shows_jalali_date_text_input_not_datetime(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        start = content.find('id_surgery_date')
        field_html = content[max(0, start - 200):start + 400]
        self.assertIn('jalali-date-input', field_html)
        # Date-only placeholder (no time portion like "HH:MM")
        self.assertNotIn('۱۲:۳۰', field_html)

    def test_posting_date_only_string_saves_correct_calendar_day(self):
        from django.utils import timezone as dj_timezone

        from common.dates import to_jalali_date

        surgery = make_surgery()
        data = base_post_data(surgery)
        data['surgery_date'] = '1404/02/05'
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
        surgery.refresh_from_db()
        local_dt = dj_timezone.localtime(surgery.surgery_date)
        self.assertEqual(to_jalali_date(local_dt), '۱۴۰۴/۰۲/۰۵')
        self.assertEqual(local_dt.time(), datetime.time(0, 0))


# ---------------------------------------------------------------------------
# 8. Add/edit form field order
# ---------------------------------------------------------------------------

class FormFieldOrderTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_order', password='pass123', email='o@o.com')
        self.client.login(username='admin_order', password='pass123')

    def test_general_section_renamed(self):
        response = self.client.get(ADD_URL)
        self.assertContains(response, 'اطلاعات عمومی عمل')
        self.assertNotContains(response, '<h2>اطلاعات عمل</h2>')

    def test_field_order_matches_spec(self):
        response = self.client.get(ADD_URL)
        content = response.content.decode()
        expected_ids_in_order = [
            'id_patient', 'id_surgery_type', 'id_surgery_date', 'id_clinical_doctor',
            'id_assistant_surgeon', 'id_second_assistant_surgeon',
            'id_scrub_employee', 'id_circulator_employee',
            'id_anesthesiologist', 'id_anesthesia_technician', 'id_anesthesia_type',
            'id_surgery_start_time', 'id_surgery_end_time',
            'id_operating_room_manager', 'id_service_employee',
            'id_postoperative_diagnosis', 'id_operation_description',
        ]
        positions = [content.find(f'"{field_id}"') for field_id in expected_ids_in_order]
        for field_id, pos in zip(expected_ids_in_order, positions):
            self.assertNotEqual(pos, -1, f'{field_id} not found in rendered form')
        self.assertEqual(positions, sorted(positions), 'Fields are not in the required order')

    def test_case_code_row_field_not_editable_input(self):
        surgery = make_surgery()
        response = self.client.get(CHANGE_URL_TPL.format(surgery.pk))
        content = response.content.decode()
        self.assertNotIn('id="id_case_code"', content)


# ---------------------------------------------------------------------------
# 9. Preservation of existing Surgery relations across the migration
# ---------------------------------------------------------------------------

class ExistingRelationsPreservedTest(TestCase):
    def test_pre_existing_style_surgery_keeps_relations_after_resave(self):
        doctor = make_doctor()
        surgery = make_surgery(clinical_doctor=doctor, status='PLANNED')
        original_pk = surgery.pk
        original_patient_id = surgery.patient_id
        original_amount = surgery.amount
        surgery.save()
        surgery.refresh_from_db()
        self.assertEqual(surgery.pk, original_pk)
        self.assertEqual(surgery.patient_id, original_patient_id)
        self.assertEqual(surgery.clinical_doctor_id, doctor.pk)
        self.assertEqual(surgery.amount, original_amount)
        self.assertEqual(surgery.status, 'PLANNED')


# ---------------------------------------------------------------------------
# 10. Fields that remain required on SurgeryHistory
# ---------------------------------------------------------------------------

class RequiredFieldsStillValidateTest(TestCase):
    """patient, surgery_type, surgery_date and amount are genuinely needed
    (patient/surgery_type identify what happened; amount/surgery_date drive
    Finance's university/doctor share calculations) — everything else on
    this form (team fields, anesthesia_type, times, diagnosis/description,
    second assistant) is optional. This locks in that only these four still
    reject a blank submission.
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admin_req', password='pass123', email='r@r.com')
        self.client.login(username='admin_req', password='pass123')

    def test_missing_patient_rejected(self):
        surgery = make_surgery()
        data = base_post_data(surgery)
        del data['patient']
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'این مقدار لازم است.')

    def test_missing_surgery_type_rejected(self):
        surgery = make_surgery()
        data = base_post_data(surgery)
        del data['surgery_type']
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'این مقدار لازم است.')

    def test_missing_amount_rejected(self):
        surgery = make_surgery()
        data = base_post_data(surgery)
        del data['amount']
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'این مقدار لازم است.')

    def test_minimal_required_fields_only_saves_successfully(self):
        surgery = make_surgery()
        data = base_post_data(surgery)
        response = self.client.post(CHANGE_URL_TPL.format(surgery.pk), data)
        self.assertEqual(response.status_code, 302)
