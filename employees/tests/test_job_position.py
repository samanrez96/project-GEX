import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from employees.models import Employee, GenderChoice, JobPosition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(name="پوزیشن‌تست", is_active=True):
    """Create a JobPosition with a unique-enough default name."""
    return JobPosition.objects.create(name=name, is_active=is_active)


def make_employee(position, is_active=True, national_id="1234567890"):
    return Employee.objects.create(
        full_name="علی محمدی",
        national_id=national_id,
        gender=GenderChoice.MALE,
        job_position=position,
        start_date=datetime.date(2024, 1, 1),
        personal_phone="09121234567",
        emergency_contact_phone="09129876543",
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class JobPositionModelTest(TestCase):

    def test_create_and_str(self):
        pos = make_position(name="حسابدار‌تست")
        self.assertEqual(str(pos), "حسابدار‌تست")
        self.assertTrue(pos.pk)

    def test_name_unique_constraint(self):
        make_position(name="یکتا‌تست")
        with self.assertRaises(IntegrityError):
            JobPosition.objects.create(name="یکتا‌تست")

    def test_get_active_employee_count_correct(self):
        pos = make_position()
        make_employee(pos, is_active=True,  national_id="1111111111")
        make_employee(pos, is_active=True,  national_id="2222222222")
        self.assertEqual(pos.get_active_employee_count(), 2)

    def test_get_active_employee_count_ignores_inactive(self):
        pos = make_position(name="پوزیشن‌مختلط")
        make_employee(pos, is_active=True,  national_id="3333333333")
        make_employee(pos, is_active=False, national_id="4444444444")
        self.assertEqual(pos.get_active_employee_count(), 1)

    def test_get_active_employee_count_zero_no_employees(self):
        pos = make_position(name="پوزیشن‌خالی")
        self.assertEqual(pos.get_active_employee_count(), 0)

    def test_clean_blocks_deactivation_with_active_employees(self):
        pos = make_position(name="غیرفعال‌بلاک")
        make_employee(pos, national_id="9999999990")
        pos.is_active = False
        with self.assertRaises(ValidationError):
            pos.clean()

    def test_clean_allows_deactivation_with_no_active_employees(self):
        pos = make_position(name="غیرفعال‌آزاد")
        pos.is_active = False
        pos.clean()  # must not raise

    def test_clean_allows_deactivation_when_employees_are_inactive(self):
        pos = make_position(name="غیرفعال‌غیرفعال")
        make_employee(pos, is_active=False, national_id="8888888880")
        pos.is_active = False
        pos.clean()  # must not raise

    def test_seeded_positions_exist(self):
        seeded = [
            "متخصص بیهوشی", "پرستار", "تکنسین",
            "اپراتور", "منشی", "حسابدار",
        ]
        for name in seeded:
            self.assertTrue(
                JobPosition.objects.filter(name=name).exists(),
                f"Seeded position '{name}' not found",
            )

    def test_seeded_positions_idempotent(self):
        count_before = JobPosition.objects.count()
        # Calling get_or_create for seeded names must not create duplicates
        for name in ["متخصص بیهوشی", "پرستار", "تکنسین", "اپراتور", "منشی", "حسابدار"]:
            JobPosition.objects.get_or_create(name=name)
        count_after = JobPosition.objects.count()
        self.assertEqual(count_before, count_after)

    def test_get_active_employee_count_uses_annotation(self):
        """When _active_employee_count is pre-set, no DB query is fired."""
        pos = make_position(name="انوتیشن‌تست")
        pos._active_employee_count = 42
        self.assertEqual(pos.get_active_employee_count(), 42)

    def test_ordering_by_name(self):
        # Verify Meta.ordering=['name'] is respected.
        # Use get_or_create so we don't break PROTECT FK constraints from CommissionRule.
        JobPosition.objects.get_or_create(name="ی", defaults={"is_active": True})
        JobPosition.objects.get_or_create(name="ا", defaults={"is_active": True})
        names = list(
            JobPosition.objects.filter(name__in=["ی", "ا"]).values_list("name", flat=True)
        )
        self.assertEqual(names, sorted(names))


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class JobPositionAPITest(APITestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser_pos", password="pass")
        self.client.force_authenticate(user=self.user)

    def _url(self, pk=None):
        if pk:
            return f"/api/v1/employees/positions/{pk}/"
        return "/api/v1/employees/positions/"

    def _results(self, res):
        """Extract list items from a potentially-paginated response."""
        data = res.data
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        return data

    def test_list_returns_all_positions(self):
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # At least the 6 seeded positions
        count = res.data.get("count", len(res.data))
        self.assertGreaterEqual(count, 6)

    def test_filter_is_active_true(self):
        make_position(name="غیرفعال‌فیلتر۱", is_active=False)
        res = self.client.get(self._url() + "?is_active=true")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in self._results(res)]
        self.assertNotIn("غیرفعال‌فیلتر۱", names)

    def test_filter_is_active_false(self):
        make_position(name="غیرفعال‌فیلتر۲", is_active=False)
        res = self.client.get(self._url() + "?is_active=false")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in self._results(res)]
        self.assertIn("غیرفعال‌فیلتر۲", names)

    def test_list_uses_list_serializer(self):
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        first = self._results(res)[0]
        self.assertNotIn("description", first)
        self.assertNotIn("active_employee_count", first)
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("is_active", first)

    def test_retrieve_uses_full_serializer(self):
        pos = make_position(name="تکنسین‌تست۲")
        res = self.client.get(self._url(pos.pk))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("description", res.data)
        self.assertIn("active_employee_count", res.data)

    def test_create_position(self):
        res = self.client.post(self._url(), {"name": "مشاور", "is_active": True})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(JobPosition.objects.filter(name="مشاور").exists())

    def test_create_duplicate_name_returns_400(self):
        JobPosition.objects.create(name="تکراری‌API")
        res = self.client.post(self._url(), {"name": "تکراری‌API"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_with_active_employees_returns_400(self):
        pos = make_position(name="حذف‌نشدنی‌API")
        make_employee(pos, national_id="5555555551")
        res = self.client.delete(self._url(pos.pk))
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(JobPosition.objects.filter(pk=pos.pk).exists())

    def test_delete_with_no_active_employees_returns_204(self):
        pos = make_position(name="حذف‌شدنی‌API")
        res = self.client.delete(self._url(pos.pk))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(JobPosition.objects.filter(pk=pos.pk).exists())

    def test_deactivate_with_active_employees_returns_400(self):
        pos = make_position(name="غیرفعال‌سازی‌API", is_active=True)
        make_employee(pos, national_id="6666666661")
        res = self.client.patch(self._url(pos.pk), {"is_active": False})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
