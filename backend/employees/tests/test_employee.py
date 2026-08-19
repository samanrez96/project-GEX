import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, GenderChoice, JobPosition

LIST_URL = "/api/v2/employees/"

User = get_user_model()


def get_position(name="پرستار"):
    pos, _ = JobPosition.objects.get_or_create(name=name, defaults={"is_active": True})
    return pos


def make_employee(**kwargs):
    if "job_position" not in kwargs:
        kwargs["job_position"] = get_position()
    defaults = {
        "full_name":               "علی رضایی",
        "national_id":             "0012345678",
        "gender":                  GenderChoice.MALE,
        "start_date":              datetime.date(2022, 3, 1),
        "personal_phone":          "09121234567",
        "emergency_contact_phone": "09129876543",
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class EmployeeModelTest(TestCase):

    def test_create_employee(self):
        emp = make_employee()
        self.assertIsNotNone(emp.pk)
        self.assertEqual(emp.full_name, "علی رضایی")
        self.assertTrue(emp.is_active)

    def test_str_method(self):
        pos = get_position("پرستار")
        emp = make_employee(job_position=pos)
        self.assertIn("علی رضایی", str(emp))
        self.assertIn("پرستار", str(emp))

    def test_defaults(self):
        emp = make_employee()
        self.assertTrue(emp.is_active)
        self.assertEqual(emp.description, "")
        self.assertEqual(emp.address, "")
        self.assertEqual(emp.email, "")

    def test_national_id_unique(self):
        make_employee(national_id="1234567890")
        with self.assertRaises(IntegrityError):
            make_employee(national_id="1234567890", full_name="فرد دیگر")

    def test_gender_choices(self):
        pos = get_position()
        emp_male = Employee.objects.create(
            full_name="مرد", national_id="1111111111", gender=GenderChoice.MALE,
            job_position=pos, start_date=datetime.date(2022, 1, 1),
            personal_phone="09120000001", emergency_contact_phone="09120000002",
        )
        emp_female = Employee.objects.create(
            full_name="زن", national_id="2222222222", gender=GenderChoice.FEMALE,
            job_position=pos, start_date=datetime.date(2022, 1, 1),
            personal_phone="09120000003", emergency_contact_phone="09120000004",
        )
        emp_other = Employee.objects.create(
            full_name="سایر", national_id="3333333333", gender=GenderChoice.OTHER,
            job_position=pos, start_date=datetime.date(2022, 1, 1),
            personal_phone="09120000005", emergency_contact_phone="09120000006",
        )
        self.assertEqual(emp_male.get_gender_display(),   "مرد")
        self.assertEqual(emp_female.get_gender_display(), "زن")
        self.assertEqual(emp_other.get_gender_display(),  "سایر")

    def test_ordering_by_full_name(self):
        pos = get_position()
        Employee.objects.create(
            full_name="ب نام", national_id="0000000001", gender=GenderChoice.MALE,
            job_position=pos, start_date=datetime.date(2022, 1, 1),
            personal_phone="09120000001", emergency_contact_phone="09120000002",
        )
        Employee.objects.create(
            full_name="الف نام", national_id="0000000002", gender=GenderChoice.MALE,
            job_position=pos, start_date=datetime.date(2022, 1, 1),
            personal_phone="09120000003", emergency_contact_phone="09120000004",
        )
        names = list(Employee.objects.values_list("full_name", flat=True))
        self.assertEqual(names, sorted(names))

    def test_created_at_auto_set(self):
        emp = make_employee()
        self.assertIsNotNone(emp.created_at)

    def test_updated_at_auto_set(self):
        emp = make_employee()
        self.assertIsNotNone(emp.updated_at)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class EmployeeAPITest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="emp_user", password="pass")
        self.client.force_authenticate(user=self.user)
        self.position = get_position("پرستار")

    def test_list_employees_empty(self):
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create_employee(self):
        pos = get_position("متخصص بیهوشی")
        payload = {
            "full_name":               "مریم احمدی",
            "national_id":             "9876543210",
            "gender":                  "female",
            "job_position":            pos.pk,
            "start_date":              "2023-05-01",
            "personal_phone":          "09351112233",
            "emergency_contact_phone": "09359998877",
        }
        resp = self.client.post(LIST_URL, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["full_name"], "مریم احمدی")
        self.assertTrue(resp.data["is_active"])

    def test_list_returns_employees(self):
        make_employee(national_id="0012345678", job_position=self.position)
        make_employee(full_name="نام دیگر", national_id="9999999999", job_position=self.position)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        count = resp.data.get("count", len(resp.data))
        self.assertEqual(count, 2)

    def test_retrieve_employee(self):
        emp = make_employee(job_position=self.position)
        resp = self.client.get(f"{LIST_URL}{emp.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["national_id"], emp.national_id)

    def test_update_employee(self):
        emp = make_employee(job_position=self.position)
        new_pos = get_position("تکنسین")
        resp = self.client.patch(
            f"{LIST_URL}{emp.pk}/",
            {"job_position": new_pos.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        emp.refresh_from_db()
        self.assertEqual(emp.job_position_id, new_pos.pk)

    def test_delete_employee(self):
        emp = make_employee(job_position=self.position)
        resp = self.client.delete(f"{LIST_URL}{emp.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Employee.objects.filter(pk=emp.pk).exists())

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_duplicate_national_id_returns_400(self):
        make_employee(national_id="1234567890", job_position=self.position)
        payload = {
            "full_name":               "فرد دیگر",
            "national_id":             "1234567890",
            "gender":                  "male",
            "job_position":            self.position.pk,
            "start_date":              "2023-01-01",
            "personal_phone":          "09120000001",
            "emergency_contact_phone": "09120000002",
        }
        resp = self.client.post(LIST_URL, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_is_active(self):
        make_employee(national_id="1111111111", is_active=True,  job_position=self.position)
        make_employee(national_id="2222222222", is_active=False, job_position=self.position)
        resp = self.client.get(LIST_URL, {"is_active": "true"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        count = resp.data.get("count", len(resp.data))
        self.assertEqual(count, 1)

    def test_filter_by_gender(self):
        make_employee(national_id="1111111111", gender=GenderChoice.MALE,   job_position=self.position)
        make_employee(national_id="2222222222", gender=GenderChoice.FEMALE, job_position=self.position)
        resp = self.client.get(LIST_URL, {"gender": "female"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        count = resp.data.get("count", len(resp.data))
        self.assertEqual(count, 1)

    def test_search_by_name(self):
        make_employee(full_name="احمد کریمی", national_id="1111111111", job_position=self.position)
        make_employee(full_name="رضا نوری",   national_id="2222222222", job_position=self.position)
        resp = self.client.get(LIST_URL, {"search": "احمد"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        count = resp.data.get("count", len(resp.data))
        self.assertEqual(count, 1)
