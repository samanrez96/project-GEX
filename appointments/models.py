from django.core.exceptions import ValidationError
from django.db import models


class AppointmentStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'برنامه‌ریزی‌شده'
    COMPLETED = 'COMPLETED', 'انجام‌شده'
    CANCELLED = 'CANCELLED', 'لغو شده'
    NO_SHOW   = 'NO_SHOW',   'عدم مراجعه'


class Appointment(models.Model):
    """A scheduled patient visit with a doctor — regular office booking,
    not tied to a surgery. Deliberately no double-booking check (business
    decision — reception staff are trusted to avoid it manually) and no
    required link to an existing Patient record (a first-time caller can
    be booked ahead via patient_name/patient_phone before ever being
    registered as a real Patient).
    """

    doctor = models.ForeignKey(
        'contacts.Doctor',
        on_delete=models.PROTECT,
        related_name='appointments',
        verbose_name='پزشک',
    )
    patient = models.ForeignKey(
        'surgeries.Patient',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        verbose_name='بیمار (ثبت‌شده)',
        help_text='در صورت خالی بودن، از نام و شماره تماس زیر استفاده می‌شود.',
    )
    patient_name = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name='نام بیمار (در صورت نبودن در سیستم)',
    )
    patient_phone = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name='شماره تماس بیمار',
    )
    visit_date = models.DateField(verbose_name='تاریخ ویزیت')
    start_time = models.TimeField(verbose_name='ساعت شروع')
    duration_minutes = models.PositiveIntegerField(
        default=30, verbose_name='مدت (دقیقه)',
    )
    status = models.CharField(
        max_length=10,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.SCHEDULED,
        verbose_name='وضعیت',
    )
    reason = models.CharField(
        max_length=200, blank=True, default='', verbose_name='علت مراجعه',
    )
    description = models.TextField(blank=True, default='', verbose_name='توضیحات')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'نوبت'
        verbose_name_plural = 'نوبت‌ها'
        ordering = ['visit_date', 'start_time']
        indexes = [
            models.Index(fields=['doctor', 'visit_date'], name='idx_appt_doctor_date'),
            models.Index(fields=['visit_date'], name='idx_appt_date'),
        ]

    def clean(self):
        if not self.patient_id and not self.patient_name.strip():
            raise ValidationError(
                'باید یا یک بیمار ثبت‌شده انتخاب شود یا نام بیمار وارد شود.'
            )
        if self.duration_minutes is not None and self.duration_minutes <= 0:
            raise ValidationError({'duration_minutes': 'مدت زمان باید بزرگ‌تر از صفر باشد.'})

    @property
    def display_patient_name(self) -> str:
        if self.patient_id:
            return self.patient.full_name
        return self.patient_name

    def __str__(self) -> str:
        return f'{self.display_patient_name} — {self.doctor.full_name} — {self.visit_date} {self.start_time}'
