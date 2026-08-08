from django.core.exceptions import ValidationError
from django.db import models, transaction

from common.text import normalize_identifier
from common.uploads import (
    doctor_medical_certificate_upload_path,
    doctor_national_card_upload_path,
    validate_image_upload,
)

_NORMALIZED_FIELDS = ('national_id', 'medical_system_number', 'clinic_phone')
_DOCUMENT_IMAGE_FIELDS = ('medical_certificate_image', 'national_card_image')


class CooperationStatus(models.TextChoices):
    ACTIVE   = 'active',   'فعال'
    INACTIVE = 'inactive', 'غیرفعال'
    PENDING  = 'pending',  'در انتظار'


class DoctorSpecialty(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name='عنوان تخصص')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'تخصص پزشک'
        verbose_name_plural = 'تخصص‌های پزشکان'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class Doctor(models.Model):
    full_name = models.CharField(max_length=200, verbose_name='نام و نام خانوادگی')
    # Derived from full_name (see DoctorAdminForm.clean()) — the visible UI
    # keeps the single "نام و نام خانوادگی" field; these exist so first/last
    # name can be queried/reported on separately without a second identity
    # section in the form.
    first_name = models.CharField(max_length=100, blank=True, default='', verbose_name='نام')
    last_name = models.CharField(max_length=100, blank=True, default='', verbose_name='نام خانوادگی')
    national_id = models.CharField(
        max_length=20, blank=True, default='', verbose_name='کد ملی',
    )
    medical_system_number = models.CharField(
        max_length=30, blank=True, default='', verbose_name='شماره نظام پزشکی',
    )
    specialty = models.ForeignKey(
        DoctorSpecialty,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='doctors',
        verbose_name='تخصص',
    )
    collaboration_start_date = models.DateField(
        null=True, blank=True, verbose_name='تاریخ شروع همکاری',
    )
    license_last_renewal_date = models.DateField(
        null=True, blank=True, verbose_name='تاریخ آخرین تمدید پروانه',
    )
    phone_number = models.CharField(
        max_length=20, blank=True, default='', verbose_name='شماره تلفن همراه',
    )
    clinic_phone = models.CharField(
        max_length=30, blank=True, default='', verbose_name='شماره تلفن مطب / کلینیک',
    )
    email = models.EmailField(blank=True, default='', verbose_name='ایمیل')
    address = models.TextField(blank=True, default='', verbose_name='آدرس')
    medical_certificate_image = models.ImageField(
        upload_to=doctor_medical_certificate_upload_path,
        blank=True,
        validators=[validate_image_upload],
        verbose_name='مدرک پزشکی',
    )
    national_card_image = models.ImageField(
        upload_to=doctor_national_card_upload_path,
        blank=True,
        validators=[validate_image_upload],
        verbose_name='کارت ملی',
    )
    center_commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name='درصد کمیسیون مرکز',
    )
    rate_per_surgery = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='نرخ هر عمل (تومان)',
        help_text='مبلغ ثابت دستمزد پزشک به ازای هر عمل. می‌تواند برای هر پزشک متفاوت باشد.',
    )
    cooperation_status = models.CharField(
        max_length=10,
        choices=CooperationStatus.choices,
        default=CooperationStatus.ACTIVE,
        verbose_name='وضعیت همکاری',
    )
    notes = models.TextField(blank=True, default='', verbose_name='یادداشت')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'اطلاعات تماس دکتر'
        verbose_name_plural = 'اطلاعات تماس دکترها'
        ordering = ['full_name']
        indexes = [
            models.Index(fields=['is_active'], name='idx_dc_is_active'),
            models.Index(fields=['cooperation_status'], name='idx_dc_coop_status'),
            models.Index(fields=['phone_number'], name='idx_dc_phone'),
        ]

    def clean(self):
        if self.center_commission_percent is not None:
            if self.center_commission_percent < 0 or self.center_commission_percent > 100:
                raise ValidationError({
                    'center_commission_percent': 'درصد کمیسیون مرکز باید بین ۰ تا ۱۰۰ باشد.',
                })

    def save(self, *args, **kwargs):
        # Single normalization point for every write path (admin form, DRF
        # API, direct ORM) — trims whitespace and converts Persian/Arabic
        # digits to ASCII while preserving leading zeros. The existing
        # mobile phone_number field is left untouched: no prior project
        # behavior normalizes it, per existing convention.
        for field_name in _NORMALIZED_FIELDS:
            setattr(self, field_name, normalize_identifier(getattr(self, field_name)))

        # Capture the currently-stored document filenames (if any) before
        # the update, so a replaced/cleared file's old copy can be removed
        # from storage — but only after the DB write actually commits.
        # Model-level (not a signal) so it covers the admin form and the
        # DRF API uniformly with a single implementation.
        old_names = {}
        if self.pk:
            old = (
                Doctor.objects.filter(pk=self.pk)
                .values(*_DOCUMENT_IMAGE_FIELDS)
                .first()
            )
            if old:
                old_names = old

        super().save(*args, **kwargs)

        for field_name, old_name in old_names.items():
            new_field = getattr(self, field_name)
            new_name = new_field.name or ''
            if old_name and old_name != new_name:
                storage = new_field.storage

                def _delete_stale(storage=storage, name=old_name):
                    try:
                        if storage.exists(name):
                            storage.delete(name)
                    except Exception:
                        pass  # cleanup failure must never surface as a crash

                transaction.on_commit(_delete_stale)

    def delete(self, *args, **kwargs):
        stale = [
            (f.storage, f.name)
            for f in (getattr(self, name) for name in _DOCUMENT_IMAGE_FIELDS)
            if f and f.name
        ]
        result = super().delete(*args, **kwargs)

        def _cleanup():
            for storage, name in stale:
                try:
                    if storage.exists(name):
                        storage.delete(name)
                except Exception:
                    pass

        transaction.on_commit(_cleanup)
        return result

    def __str__(self) -> str:
        specialty = self.specialty.name if self.specialty_id else 'بدون تخصص'
        return f'{self.full_name} — {specialty}'

    def __repr__(self) -> str:
        return f'<Doctor pk={self.pk} name={self.full_name!r}>'


class DoctorSurgeryRate(models.Model):
    """A Doctor's fee for one specific Surgery Type.

    Purely a rate-management record for this phase — not consumed by any
    Surgery finalization, commission, or Finance calculation.
    """

    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name='surgery_rates',
        verbose_name='پزشک',
    )
    surgery_type = models.ForeignKey(
        'surgeries.SurgeryType',
        on_delete=models.PROTECT,
        related_name='doctor_rates',
        verbose_name='نوع عمل',
    )
    rate = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name='نرخ هر عمل (تومان)',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'نرخ پزشک به ازای نوع عمل'
        verbose_name_plural = 'نرخ‌های پزشک به تفکیک نوع عمل'
        ordering = ['doctor__full_name', 'surgery_type__name']
        unique_together = [('doctor', 'surgery_type')]

    def clean(self):
        if self.rate is not None and self.rate < 0:
            raise ValidationError({'rate': 'نرخ نمی‌تواند منفی باشد.'})

    def __str__(self) -> str:
        return f'{self.doctor} — {self.surgery_type}: {self.rate}'
