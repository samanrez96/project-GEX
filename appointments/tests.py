import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from contacts.models import Doctor
from surgeries.models import Patient

from .models import Appointment, AppointmentStatus

User = get_user_model()

LIST_URL = "/api/v1/appointments/appointments/"


def _doctor(**kw):
    defaults = {"full_name": "دکتر تست"}
    defaults.update(kw)
    return Doctor.objects.create(**defaults)


def _patient(**kw):
    defaults = {"full_name": "بیمار تست"}
    defaults.update(kw)
    return Patient.objects.create(**defaults)


def _appointment(**kw):
    defaults = {
        "doctor": kw.pop("doctor", None) or _doctor(),
        "visit_date": datetime.date(2026, 8, 22),
        "start_time": datetime.time(10, 0),
    }
    defaults.update(kw)
    return Appointment.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class AppointmentModelTest(TestCase):

    def setUp(self):
        self.doctor = _doctor()

    def test_str_uses_display_patient_name(self):
        appt = _appointment(doctor=self.doctor, patient_name="نام دستی")
        self.assertIn("نام دستی", str(appt))

    def test_requires_patient_or_patient_name(self):
        appt = Appointment(
            doctor=self.doctor,
            visit_date=datetime.date(2026, 8, 22),
            start_time=datetime.time(10, 0),
        )
        with self.assertRaises(ValidationError):
            appt.clean()

    def test_patient_fk_alone_is_sufficient(self):
        patient = _patient()
        appt = Appointment(
            doctor=self.doctor,
            patient=patient,
            visit_date=datetime.date(2026, 8, 22),
            start_time=datetime.time(10, 0),
        )
        appt.clean()  # must not raise

    def test_patient_name_alone_is_sufficient(self):
        appt = Appointment(
            doctor=self.doctor,
            patient_name="مراجعه‌کننده تازه",
            visit_date=datetime.date(2026, 8, 22),
            start_time=datetime.time(10, 0),
        )
        appt.clean()  # must not raise

    def test_zero_duration_rejected(self):
        appt = Appointment(
            doctor=self.doctor,
            patient_name="تست",
            visit_date=datetime.date(2026, 8, 22),
            start_time=datetime.time(10, 0),
            duration_minutes=0,
        )
        with self.assertRaises(ValidationError):
            appt.clean()

    def test_display_patient_name_prefers_fk_over_free_text(self):
        patient = _patient(full_name="نام ثبت‌شده")
        appt = _appointment(doctor=self.doctor, patient=patient, patient_name="نام دستی نادیده")
        self.assertEqual(appt.display_patient_name, "نام ثبت‌شده")

    def test_no_conflict_check_double_booking_allowed(self):
        """Explicit business decision — no overlap validation."""
        _appointment(doctor=self.doctor, patient_name="اول", start_time=datetime.time(10, 0))
        second = _appointment(doctor=self.doctor, patient_name="دوم", start_time=datetime.time(10, 0))
        self.assertIsNotNone(second.pk)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class AppointmentAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="apptuser", password="pass")
        self.client.force_authenticate(user=self.user)
        self.doctor = _doctor()

    def test_create_with_existing_patient(self):
        patient = _patient()
        resp = self.client.post(LIST_URL, {
            "doctor": self.doctor.pk,
            "patient": patient.pk,
            "visit_date": "2026-08-22",
            "start_time": "10:00",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["patient_display_name"], patient.full_name)

    def test_create_with_free_text_patient_name(self):
        resp = self.client.post(LIST_URL, {
            "doctor": self.doctor.pk,
            "patient_name": "مراجعه‌کننده جدید",
            "patient_phone": "09120000000",
            "visit_date": "2026-08-22",
            "start_time": "11:00",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["patient_display_name"], "مراجعه‌کننده جدید")

    def test_create_without_patient_or_name_rejected(self):
        resp = self.client.post(LIST_URL, {
            "doctor": self.doctor.pk,
            "visit_date": "2026-08-22",
            "start_time": "10:00",
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_conflict_check_double_booking_returns_201(self):
        payload = {
            "doctor": self.doctor.pk,
            "patient_name": "بیمار",
            "visit_date": "2026-08-22",
            "start_time": "10:00",
        }
        self.assertEqual(self.client.post(LIST_URL, payload).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.post(LIST_URL, payload).status_code, status.HTTP_201_CREATED)

    def test_filter_by_doctor_and_date_range(self):
        other_doctor = _doctor(full_name="دکتر دیگر")
        _appointment(doctor=self.doctor, patient_name="در بازه", visit_date=datetime.date(2026, 8, 22))
        _appointment(doctor=self.doctor, patient_name="خارج از بازه", visit_date=datetime.date(2026, 9, 1))
        _appointment(doctor=other_doctor, patient_name="پزشک دیگر", visit_date=datetime.date(2026, 8, 22))

        resp = self.client.get(LIST_URL, {
            "doctor": self.doctor.pk,
            "visit_date__gte": "2026-08-17",
            "visit_date__lte": "2026-08-23",
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [r["patient_display_name"] for r in resp.data["results"]]
        self.assertEqual(names, ["در بازه"])

    def test_hidden_patient_appointment_excluded_from_list(self):
        hidden_patient = _patient(full_name="بیمار مخفی")
        hidden_patient.is_hidden = True
        hidden_patient.save(update_fields=["is_hidden"])
        _appointment(doctor=self.doctor, patient=hidden_patient)

        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in resp.data["results"]]
        self.assertEqual(ids, [])

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_status_default_is_scheduled(self):
        resp = self.client.post(LIST_URL, {
            "doctor": self.doctor.pk,
            "patient_name": "بیمار",
            "visit_date": "2026-08-22",
            "start_time": "10:00",
        })
        self.assertEqual(resp.data["status"], AppointmentStatus.SCHEDULED)


# ---------------------------------------------------------------------------
# Admin page tests
# ---------------------------------------------------------------------------

class AppointmentAdminPageTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(username="apptadmin", password="pass")
        self.client.force_login(self.admin)

    def test_calendar_page_loads(self):
        resp = self.client.get("/admin/appointments/calendar/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تقویم نوبت‌ها")

    def test_add_page_loads_with_prefill_params(self):
        doctor = _doctor()
        resp = self.client.get(
            f"/admin/appointments/appointment/add/?doctor={doctor.pk}&visit_date=2026-08-22&start_time=10:00"
        )
        self.assertEqual(resp.status_code, 200)

    def test_sidebar_link_present_on_admin_index(self):
        resp = self.client.get("/admin/")
        self.assertContains(resp, "appointments/calendar/")
