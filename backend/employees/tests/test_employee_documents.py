"""Regression tests for the Employee add IntegrityError caused by
credential_image_1/credential_image_2 schema drift, and for the repeatable
EmployeeDocument system that replaced those two legacy fixed fields.

Root cause: a migration that added NOT-NULL first_name/last_name/
credential_image_1/credential_image_2 columns had been applied to the local
dev database and then its file went missing from the codebase, leaving the
Employee model with no knowledge of those columns — every admin POST omitted
them from the INSERT and SQLite raised
`IntegrityError: NOT NULL constraint failed: employees_employee.credential_image_1`.

Covers:
 - the previously-failing admin POST now succeeds with zero/one/multiple
   documents
 - empty document rows never create EmployeeDocument records
 - editing an Employee without touching documents preserves them
 - existing documents remain visible on the change form
 - the data migration preserves legacy file paths into EmployeeDocument
"""
import datetime
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from PIL import Image

from employees.models import Employee, EmployeeDocument, JobPosition

User = get_user_model()

_TEST_MEDIA = tempfile.mkdtemp(prefix='emp_docs_test_')


def tearDownModule():
    shutil.rmtree(_TEST_MEDIA, ignore_errors=True)


def make_position(name='پرستار'):
    pos, _ = JobPosition.objects.get_or_create(name=name, defaults={'is_active': True})
    return pos


def make_employee(**kwargs):
    kwargs.setdefault('job_position', make_position())
    defaults = {
        'full_name': 'رضا احمدی',
        'national_id': '0012345678',
        'gender': 'male',
        'start_date': datetime.date(2023, 1, 1),
        'personal_phone': '09121234567',
        'emergency_contact_phone': '09129876543',
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_image_file(name='test.jpg', fmt='JPEG'):
    buf = BytesIO()
    Image.new('RGB', (10, 10), (100, 100, 100)).save(buf, format=fmt)
    buf.seek(0)
    ct = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}[fmt]
    return SimpleUploadedFile(name, buf.read(), content_type=ct)


def _base_post_data(position_pk, **overrides):
    data = {
        'full_name': 'کارمند تست مدرک',
        'national_id': '1112223334',
        'gender': 'male',
        'job_position': position_pk,
        'start_date': '2024-01-01',
        'is_active': 'on',
        'email': '',
        'personal_phone': '09121234567',
        'emergency_contact_phone': '09129876543',
        'address': '',
        'hourly_rate': '',
        'description': '',
        'wage_type': 'none',
        'monthly_amount': '',
        'hourly_rate_amount': '',
        'wage_start_date': '',
        'documents-TOTAL_FORMS': '1',
        'documents-INITIAL_FORMS': '0',
        'documents-MIN_NUM_FORMS': '0',
        'documents-MAX_NUM_FORMS': '1000',
        'documents-0-file': '',
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# The exact previously-failing admin POST
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=_TEST_MEDIA)
class EmployeeAdminAddPostTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(username='emp_add_admin', password='pass')
        self.client.force_login(self.admin)
        self.position = make_position()

    def test_add_post_no_longer_raises_integrity_error(self):
        resp = self.client.post('/admin/employees/employee/add/', _base_post_data(self.position.pk))
        self.assertNotEqual(resp.status_code, 500)

    def test_employee_can_be_created_with_no_document(self):
        resp = self.client.post('/admin/employees/employee/add/', _base_post_data(self.position.pk))
        self.assertEqual(resp.status_code, 302)
        emp = Employee.objects.get(national_id='1112223334')
        self.assertEqual(EmployeeDocument.objects.filter(employee=emp).count(), 0)

    def test_employee_can_be_created_with_one_document(self):
        data = _base_post_data(self.position.pk, national_id='2223334445')
        data['documents-0-file'] = make_image_file('doc1.jpg')
        resp = self.client.post('/admin/employees/employee/add/', data)
        self.assertEqual(resp.status_code, 302)
        emp = Employee.objects.get(national_id='2223334445')
        self.assertEqual(EmployeeDocument.objects.filter(employee=emp).count(), 1)

    def test_employee_can_be_created_with_multiple_documents(self):
        data = _base_post_data(self.position.pk, national_id='3334445556')
        data['documents-TOTAL_FORMS'] = '2'
        data['documents-0-file'] = make_image_file('doc1.jpg')
        data['documents-1-file'] = make_image_file('doc2.jpg')
        resp = self.client.post('/admin/employees/employee/add/', data)
        self.assertEqual(resp.status_code, 302)
        emp = Employee.objects.get(national_id='3334445556')
        self.assertEqual(EmployeeDocument.objects.filter(employee=emp).count(), 2)

    def test_empty_document_rows_do_not_create_records(self):
        data = _base_post_data(self.position.pk, national_id='4445556667')
        data['documents-TOTAL_FORMS'] = '3'
        data['documents-1-file'] = ''
        data['documents-2-file'] = ''
        resp = self.client.post('/admin/employees/employee/add/', data)
        self.assertEqual(resp.status_code, 302)
        emp = Employee.objects.get(national_id='4445556667')
        self.assertEqual(EmployeeDocument.objects.filter(employee=emp).count(), 0)

    def test_invalid_document_returns_form_errors_not_500(self):
        data = _base_post_data(self.position.pk, national_id='5556667778')
        data['documents-0-file'] = SimpleUploadedFile(
            'fake.jpg', b'not an image', content_type='image/jpeg',
        )
        resp = self.client.post('/admin/employees/employee/add/', data)
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not 500
        self.assertFalse(Employee.objects.filter(national_id='5556667778').exists())


# ---------------------------------------------------------------------------
# Change form — editing, existing documents visible/preserved
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=_TEST_MEDIA)
class EmployeeAdminChangePostTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(username='emp_change_admin', password='pass')
        self.client.force_login(self.admin)
        self.position = make_position()
        self.emp = make_employee(job_position=self.position, national_id='6667778889')
        self.doc = EmployeeDocument.objects.create(employee=self.emp, file=make_image_file('existing.jpg'))

    def test_change_form_displays_existing_document(self):
        resp = self.client.get(f'/admin/employees/employee/{self.emp.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'documents-0-id')

    def test_editing_without_touching_documents_preserves_them(self):
        data = _base_post_data(self.position.pk, national_id=self.emp.national_id, full_name='نام ویرایش‌شده')
        data['documents-INITIAL_FORMS'] = '1'
        data['documents-0-id'] = str(self.doc.pk)
        data['documents-0-file'] = ''  # unchanged — ClearableFileInput keeps existing file
        resp = self.client.post(f'/admin/employees/employee/{self.emp.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EmployeeDocument.objects.filter(employee=self.emp).count(), 1)
        self.assertTrue(EmployeeDocument.objects.filter(pk=self.doc.pk).exists())

    def test_deleting_a_document_via_formset_removes_it(self):
        data = _base_post_data(self.position.pk, national_id=self.emp.national_id)
        data['documents-INITIAL_FORMS'] = '1'
        data['documents-0-id'] = str(self.doc.pk)
        data['documents-0-file'] = ''
        data['documents-0-DELETE'] = 'on'
        resp = self.client.post(f'/admin/employees/employee/{self.emp.pk}/change/', data)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(EmployeeDocument.objects.filter(pk=self.doc.pk).exists())


# ---------------------------------------------------------------------------
# Model-level sanity: creating an Employee no longer needs the legacy fields
# ---------------------------------------------------------------------------

class EmployeeModelCreationTest(TestCase):

    def test_create_via_orm_without_legacy_fields(self):
        # This is exactly what raised IntegrityError before the fix — the
        # model/ORM path (not just the admin form) must also work.
        emp = make_employee(national_id='7778889990')
        self.assertIsNotNone(emp.pk)
        self.assertFalse(hasattr(emp, 'credential_image_1'))

    def test_no_integrity_error_on_bulk_create(self):
        try:
            make_employee(national_id='8889990001')
        except IntegrityError:
            self.fail('Employee creation raised IntegrityError')


# ---------------------------------------------------------------------------
# Data migration — legacy credential_image_1/2 preserved into EmployeeDocument
# ---------------------------------------------------------------------------

class LegacyCredentialImageMigrationTest(TransactionTestCase):
    """Exercises employees.migrations.0008_migrate_legacy_credential_images
    directly against the historical (pre-0009) model state, using Django's
    migration executor — the standard way to test a data migration in
    isolation. Restores the schema to the latest migration in tearDown so
    later tests in the same run see the normal, current model state.
    """

    reset_sequences = True

    def tearDown(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        targets = [key for key in executor.loader.graph.leaf_nodes() if key[0] == 'employees']
        executor.migrate(targets)

    def test_legacy_files_copied_into_employee_document(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        migrate_from = [('employees', '0007_employeedocument')]
        migrate_to = [('employees', '0008_migrate_legacy_credential_images')]

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)

        old_apps = executor.loader.project_state(migrate_from).apps
        OldEmployee = old_apps.get_model('employees', 'Employee')
        OldJobPosition = old_apps.get_model('employees', 'JobPosition')

        pos = OldJobPosition.objects.create(name='بایگانی', is_active=True)
        emp_with_files = OldEmployee.objects.create(
            full_name='کارمند بایگانی', national_id='9990001112',
            gender='male', job_position=pos,
            start_date=datetime.date(2020, 1, 1),
            personal_phone='09120000000', emergency_contact_phone='09120000001',
            credential_image_1='employees/credential-1/2020/01/legacy1.jpg',
            credential_image_2='employees/credential-2/2020/01/legacy2.jpg',
        )
        emp_without_files = OldEmployee.objects.create(
            full_name='کارمند بدون مدرک', national_id='9990001113',
            gender='female', job_position=pos,
            start_date=datetime.date(2020, 1, 1),
            personal_phone='09120000002', emergency_contact_phone='09120000003',
            credential_image_1='', credential_image_2='',
        )

        # Migrate forward through the data migration.
        executor = MigrationExecutor(connection)
        executor.migrate(migrate_to)
        new_apps = executor.loader.project_state(migrate_to).apps
        NewEmployeeDocument = new_apps.get_model('employees', 'EmployeeDocument')

        docs = list(
            NewEmployeeDocument.objects.filter(employee_id=emp_with_files.pk)
            .order_by('id').values_list('file', flat=True)
        )
        self.assertEqual(docs, [
            'employees/credential-1/2020/01/legacy1.jpg',
            'employees/credential-2/2020/01/legacy2.jpg',
        ])
        self.assertEqual(
            NewEmployeeDocument.objects.filter(employee_id=emp_without_files.pk).count(), 0,
        )

    def test_migration_is_idempotent_when_rerun(self):
        import importlib

        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        migrate_from = [('employees', '0007_employeedocument')]
        migrate_to = [('employees', '0008_migrate_legacy_credential_images')]

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)
        old_apps = executor.loader.project_state(migrate_from).apps
        OldEmployee = old_apps.get_model('employees', 'Employee')
        OldJobPosition = old_apps.get_model('employees', 'JobPosition')

        pos = OldJobPosition.objects.create(name='بایگانی۲', is_active=True)
        emp = OldEmployee.objects.create(
            full_name='کارمند تکرار', national_id='9990001114',
            gender='male', job_position=pos,
            start_date=datetime.date(2020, 1, 1),
            personal_phone='09120000004', emergency_contact_phone='09120000005',
            credential_image_1='employees/credential-1/2020/01/dup.jpg',
            credential_image_2='',
        )

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_to)

        # Call the same forwards() function again directly, against the
        # same historical apps state — must not create a duplicate row for
        # a file name that's already been copied.
        migration_module = importlib.import_module(
            'employees.migrations.0008_migrate_legacy_credential_images'
        )
        post_migrate_apps = executor.loader.project_state(migrate_to).apps
        migration_module.forwards(post_migrate_apps, None)

        NewEmployeeDocument = post_migrate_apps.get_model('employees', 'EmployeeDocument')
        self.assertEqual(
            NewEmployeeDocument.objects.filter(employee_id=emp.pk).count(), 1,
        )
