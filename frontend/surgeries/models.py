"""Surgery models.

Tracks surgical procedures and the inventory items consumed during each
operation.  Stock OUT movements are created atomically when a surgery is
marked COMPLETED, via Surgery.complete().
"""

import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models, transaction
from django.utils import timezone

from accounts.permissions import is_main_administrator


# ---------------------------------------------------------------------------
# Patient gender — Patient-specific (not employees.GenderChoice, which also
# offers "سایر"/other; Patient must only ever offer مرد/زن).
# ---------------------------------------------------------------------------

class Gender(models.TextChoices):
    MALE   = 'MALE',   'مرد'
    FEMALE = 'FEMALE', 'زن'


class MaritalStatus(models.TextChoices):
    SINGLE = 'SINGLE', 'مجرد'
    MARRIED = 'MARRIED', 'متأهل'
    DIVORCED = 'DIVORCED', 'مطلقه'
    WIDOWED = 'WIDOWED', 'همسر فوت شده'


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------

class PatientQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Canonical Patient visibility rule — the single place every view,
        serializer, autocomplete, and export must go through instead of
        each re-implementing ``.filter(is_hidden=False)`` independently.

        The main administrator (see ``accounts.permissions.is_main_administrator``)
        sees every Patient, hidden or not. Everyone else only ever sees
        non-hidden Patients — a hidden Patient must not be discoverable by
        ID, search, or count for anyone else.
        """
        if is_main_administrator(user):
            return self
        return self.filter(is_hidden=False)


class PatientManager(models.Manager.from_queryset(PatientQuerySet)):
    pass


class Patient(models.Model):
    """Patient record for the surgery clinic."""

    full_name    = models.CharField(max_length=200, verbose_name='نام و نام خانوادگی')
    national_id  = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='کد ملی',
    )
    case_code    = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='کد پرونده',
        help_text='کد پرونده باید منحصربه‌فرد باشد.',
    )
    # Separate from case_code: an internal clinic-assigned code (distinct
    # numbering scheme). Optional — existing Patient rows have no value to
    # backfill it from — but unique whenever it is actually set. NULL (not
    # an empty string) is what "not set" means here, so multiple Patients
    # can each leave it blank without colliding; see clean() and the
    # conditional constraint below for how blank input is kept out of the
    # unique check.
    internal_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name='کد داخلی بیمار',
        help_text='اختیاری — در صورت تکمیل، باید منحصربه‌فرد باشد.',
    )
    # Nullable at the DB level so existing Patient rows (registered before
    # this field existed) remain valid and readable — there is no safe way
    # to invent an age/gender for historical records. New registrations are
    # required to fill both, enforced in PatientAdminForm/PatientSerializer,
    # not at the database level.
    age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(130, message='سن باید حداکثر ۱۳۰ سال باشد.')],
        verbose_name='سن بیمار',
    )
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        null=True,
        blank=True,
        verbose_name='جنسیت',
    )
    marital_status = models.CharField(
        max_length=12,
        choices=MaritalStatus.choices,
        null=True,
        blank=True,
        verbose_name='وضعیت تأهل',
    )
    phone_number = models.CharField(max_length=20, verbose_name='شماره موبایل')
    description  = models.TextField(blank=True, default='', verbose_name='توضیحات')
    # Visibility — distinct from any "active/inactive" business status this
    # model might gain later. A hidden Patient is not deactivated or
    # archived; it is simply invisible to everyone except the main
    # administrator (see accounts.permissions.is_main_administrator and
    # PatientQuerySet.visible_to above, the single canonical enforcement
    # point for this rule).
    is_hidden  = models.BooleanField(
        default=False,
        verbose_name='مخفی',
        help_text='بیمار مخفی فقط برای مدیر اصلی سیستم قابل مشاهده است.',
    )
    hidden_at  = models.DateTimeField(null=True, blank=True, verbose_name='زمان مخفی‌سازی')
    hidden_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='مخفی‌شده توسط',
    )
    created_at   = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at   = models.DateTimeField(auto_now=True,     verbose_name='آخرین ویرایش')

    objects = PatientManager()

    class Meta:
        verbose_name        = 'بیمار'
        verbose_name_plural = 'بیماران'
        ordering            = ['-created_at']
        constraints = [
            # Mirrors inventory.Product.barcode's pattern: NULL is exempt
            # from the SQL unique index (NULL ≠ NULL) but an explicit empty
            # string is not, so it is excluded here too — otherwise two
            # Patients saved with internal_code='' would collide.
            models.UniqueConstraint(
                fields=['internal_code'],
                condition=models.Q(internal_code__isnull=False) & ~models.Q(internal_code=''),
                name='unique_patient_internal_code_when_set',
                violation_error_message='کد داخلی بیمار باید یکتا باشد.',
            ),
        ]
        indexes = [
            models.Index(fields=['case_code'],      name='idx_patient_case_code'),
            models.Index(fields=['internal_code'],  name='idx_patient_internal_code'),
            models.Index(fields=['phone_number'],   name='idx_patient_phone'),
        ]

    def clean(self):
        if self.internal_code is not None:
            self.internal_code = self.internal_code.strip() or None

    def hide(self, user):
        """Mark this Patient hidden and record who/when (minimal audit —
        this project has no larger audit subsystem to hook into)."""
        self.is_hidden = True
        self.hidden_at = timezone.now()
        self.hidden_by = user
        self.save(update_fields=['is_hidden', 'hidden_at', 'hidden_by', 'updated_at'])

    def unhide(self):
        """Restore visibility. Idempotent — calling this on an already
        visible Patient is a harmless no-op save."""
        self.is_hidden = False
        self.hidden_at = None
        self.hidden_by = None
        self.save(update_fields=['is_hidden', 'hidden_at', 'hidden_by', 'updated_at'])

    def __str__(self) -> str:
        return f'{self.full_name} ({self.case_code})'

    def __repr__(self) -> str:
        return f'<Patient pk={self.pk} case_code={self.case_code!r}>'


class SurgeryStatus(models.TextChoices):
    PLANNED     = "PLANNED",     "برنامه‌ریزی شده"
    IN_PROGRESS = "IN_PROGRESS", "در حال انجام"
    COMPLETED   = "COMPLETED",   "انجام شده"
    CANCELLED   = "CANCELLED",   "لغو شده"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "در انتظار پرداخت"
    PARTIAL = "PARTIAL", "پرداخت ناقص"
    PAID    = "PAID",    "پرداخت شده"


class AnesthesiaType(models.Model):
    """Authoritative, manageable list of anesthesia types.

    Managed exclusively from the SurgeryHistory add/edit form's inline
    modal (mirrors contacts.DoctorSpecialty) — no standalone admin page.
    """

    name = models.CharField(max_length=150, unique=True, verbose_name='نام نوع بیهوشی')
    is_active = models.BooleanField(default=True, verbose_name='فعال')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name = 'نوع بیهوشی'
        verbose_name_plural = 'انواع بیهوشی'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class SurgeryHistoryQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Strict rule for a Surgery whose Patient is hidden: the whole
        record is excluded for everyone except the main administrator —
        not just the patient's name, since SurgeryHistory itself archives
        its own copies of identifying fields (case_code, phone_number,
        medical_record_code) independent of the ``patient`` FK, so masking
        individual fields would still leave those exposed.
        """
        if is_main_administrator(user):
            return self
        return self.filter(patient__is_hidden=False)


class SurgeryHistoryManager(models.Manager.from_queryset(SurgeryHistoryQuerySet)):
    pass


class SurgeryHistory(models.Model):
    """Financial and clinical record of a performed surgery.

    Captures the business side of a surgery: who the patient is, which doctor
    performed it, the fee, payment status, and overall status.  Inventory
    consumption details are tracked via SurgeryUsedItem (one-to-many).
    """

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name='surgery_histories',
        verbose_name='بیمار',
    )
    case_code = models.CharField(
        max_length=50,
        verbose_name='ردیف',
        help_text='کد پرونده بیمار هنگام ثبت (کپی از بیمار برای آرشیو).',
    )
    medical_record_code = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='کد پرونده',
        help_text='کد پرونده پزشکی مربوط به این عمل جراحی.',
    )
    phone_number = models.CharField(
        max_length=20,
        verbose_name='شماره تلفن',
        help_text='شماره تماس هنگام ثبت (کپی از بیمار برای آرشیو).',
    )
    clinical_doctor = models.ForeignKey(
        'contacts.Doctor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='surgery_histories',
        verbose_name='نام جراح/درمانگر',
    )
    doctor_or_therapist = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='surgery_histories',
        verbose_name='کارمند درمانگر (برای محاسبه کمیسیون)',
    )
    surgery_type = models.ForeignKey(
        'SurgeryType',
        on_delete=models.PROTECT,
        related_name='surgery_histories',
        verbose_name='نوع عمل',
    )
    surgery_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='تاریخ عمل',
    )

    # ── General-information roles (Phase 1 / Task 1) ──────────────────
    # All optional (nullable) for backward compatibility with existing
    # records. SET_NULL mirrors the existing clinical_doctor/
    # doctor_or_therapist convention on this model — an Employee or Doctor
    # deletion must never cascade-delete a SurgeryHistory record.
    assistant_surgeon = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assistant_surgeon_surgeries',
        verbose_name='کمک اول جراح',
    )
    second_assistant_surgeon = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='second_assistant_surgeries',
        verbose_name='کمک دوم جراح',
    )
    scrub_employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scrub_surgeries',
        verbose_name='اسکراب',
    )
    circulator_employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='circulator_surgeries',
        verbose_name='سیرکولر',
    )
    anesthesiologist = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='anesthesiologist_surgeries',
        verbose_name='متخصص بیهوشی',
    )
    anesthesia_technician = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='anesthesia_technician_surgeries',
        verbose_name='تکنسین بیهوشی',
    )
    anesthesia_type = models.ForeignKey(
        AnesthesiaType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='surgery_histories',
        verbose_name='نوع بیهوشی',
    )
    operating_room_manager = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operating_room_manager_surgeries',
        verbose_name='مسئول اتاق عمل',
    )
    service_employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_surgeries',
        verbose_name='خدمات',
    )
    surgery_start_time = models.TimeField(null=True, blank=True, verbose_name='ساعت شروع عمل')
    surgery_end_time = models.TimeField(null=True, blank=True, verbose_name='ساعت اتمام عمل')
    postoperative_diagnosis = models.TextField(blank=True, default='', verbose_name='تشخیص بعد از عمل')
    operation_description = models.TextField(blank=True, default='', verbose_name='شرح عمل و مشاهدات')
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='مبلغ',
        help_text='هزینه عمل جراحی به تومان.',
    )
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name='وضعیت پرداخت',
    )
    # Center commission — exactly one of these may be set.
    # If center_commission_amount is set it takes priority over percent.
    # If both are None, no finance income is generated for this surgery.
    center_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='درصد کمیسیون مرکز',
        help_text='درصد سهم مرکز از مبلغ عمل (۰ تا ۱۰۰).',
    )
    center_commission_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='مبلغ کمیسیون مرکز',
        help_text='مبلغ ثابت سهم مرکز. اگر تنظیم شود، بر درصد اولویت دارد.',
    )
    description = models.TextField(blank=True, default='', verbose_name='توضیحات')
    status = models.CharField(
        max_length=20,
        choices=SurgeryStatus.choices,
        default=SurgeryStatus.PLANNED,
        verbose_name='وضعیت عمل',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True,     verbose_name='آخرین ویرایش')

    objects = SurgeryHistoryManager()

    class Meta:
        verbose_name        = 'تاریخچه عمل جراحی'
        verbose_name_plural = 'تاریخچه اعمال جراحی'
        ordering            = ['-surgery_date', '-created_at']
        indexes = [
            models.Index(fields=['patient'],        name='idx_sh_patient'),
            models.Index(fields=['surgery_type'],   name='idx_sh_surgery_type'),
            models.Index(fields=['surgery_date'],   name='idx_sh_surgery_date'),
            models.Index(fields=['status'],         name='idx_sh_status'),
            models.Index(fields=['payment_status'], name='idx_sh_payment_status'),
        ]

    def clean(self):
        if self.amount is not None and self.amount < 0:
            raise ValidationError({'amount': 'مبلغ نمی‌تواند منفی باشد.'})
        if self.center_commission_percent is not None:
            if self.center_commission_percent < 0 or self.center_commission_percent > 100:
                raise ValidationError({
                    'center_commission_percent': 'درصد کمیسیون مرکز باید بین ۰ تا ۱۰۰ باشد.',
                })
        if self.center_commission_amount is not None and self.center_commission_amount < 0:
            raise ValidationError({
                'center_commission_amount': 'مبلغ کمیسیون مرکز نمی‌تواند منفی باشد.',
            })
        if self.surgery_start_time and self.surgery_end_time and self.surgery_end_time < self.surgery_start_time:
            raise ValidationError({
                'surgery_end_time': 'ساعت اتمام عمل نمی‌تواند قبل از ساعت شروع عمل باشد.',
            })
        if self.status == SurgeryStatus.COMPLETED and self.clinical_doctor_id and self.surgery_type_id:
            # Finalization requires an exact DoctorSurgeryRate for this
            # (doctor, surgery type) pair — this only guards the admin
            # save path; the API path is separately guarded by
            # SurgeryFinanceService.sync_doctor_fee_expense so both entry
            # points block consistently.
            from contacts.services import DoctorRateService
            if DoctorRateService.get_rate(self.clinical_doctor, self.surgery_type) is None:
                raise ValidationError({
                    'status': 'برای تکمیل این عمل، نرخ پزشک برای این نوع عمل ثبت نشده است.',
                })

    # ── Business share calculations (45 % university / 55 % doctor) ──

    @property
    def university_share(self) -> Decimal:
        """45% of surgery amount goes to the university."""
        if self.amount is None:
            return Decimal('0')
        return (self.amount * Decimal('45') / Decimal('100')).quantize(Decimal('1'))

    @property
    def doctor_share(self) -> Decimal:
        """55% of surgery amount goes to the doctor/therapist."""
        if self.amount is None:
            return Decimal('0')
        return (self.amount * Decimal('55') / Decimal('100')).quantize(Decimal('1'))

    def save(self, *args, **kwargs):
        if self.patient_id and not self.case_code:
            self.case_code = self.patient.case_code
        if self.patient_id and not self.phone_number:
            self.phone_number = self.patient.phone_number
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        date_str = self.surgery_date.strftime('%Y-%m-%d')
        return f'تاریخچه #{self.pk} — {self.patient.full_name} ({date_str})'

    def __repr__(self) -> str:
        return f'<SurgeryHistory pk={self.pk} patient={self.patient_id} status={self.status}>'


# ---------------------------------------------------------------------------
# SurgeryUsedItem
# ---------------------------------------------------------------------------

class SurgeryUsedItem(models.Model):
    """An inventory item used during a surgery recorded in SurgeryHistory.

    Tracks what was consumed for reporting and cost analysis purposes.
    Actual stock deduction is NOT performed here — that is handled by
    SurgeryConsumptionItem via the legacy Surgery.complete() workflow.
    """

    surgery = models.ForeignKey(
        SurgeryHistory,
        on_delete=models.CASCADE,
        related_name='used_items',
        verbose_name='تاریخچه عمل جراحی',
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='surgery_used_items',
        verbose_name='محصول / کالا',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name='مقدار',
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='واحد',
        help_text='اگر خالی باشد از محصول کپی می‌شود.',
    )
    description = models.TextField(blank=True, default='', verbose_name='توضیحات')
    created_at  = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at  = models.DateTimeField(auto_now=True,     verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'قلم مصرف تاریخچه عمل'
        verbose_name_plural = 'اقلام مصرف تاریخچه عمل'
        indexes = [
            models.Index(fields=['surgery'], name='idx_sui_surgery'),
            models.Index(fields=['product'], name='idx_sui_product'),
        ]

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': 'مقدار باید بزرگ‌تر از صفر باشد.'})

    def save(self, *args, **kwargs):
        if not self.unit and self.product_id:
            self.unit = self.product.unit
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.product.name} × {self.quantity} {self.unit}'

    def __repr__(self) -> str:
        return (
            f'<SurgeryUsedItem pk={self.pk} '
            f'surgery={self.surgery_id} product={self.product_id} qty={self.quantity}>'
        )


class Surgery(models.Model):
    """A surgical procedure, linked to consumption of inventory items.

    Workflow:
      1. Create Surgery (status=PLANNED) + add SurgeryConsumptionItems.
      2. Optionally update status to IN_PROGRESS.
      3. Call surgery.complete() to transition to COMPLETED.
         complete() creates one OUT StockMovement per consumption item and
         sets stock_applied=True so the operation is idempotent.

    The stock_applied flag ensures that calling complete() more than once
    never creates duplicate stock movements.
    """

    patient_name = models.CharField(max_length=200, verbose_name="نام بیمار")
    surgery_date = models.DateTimeField(
        default=timezone.now,
        verbose_name="تاریخ عمل",
    )
    surgeon_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="نام جراح",
        help_text="تا پیاده‌سازی مدل Employee این فیلد متن آزاد است.",
    )
    notes = models.TextField(blank=True, default="", verbose_name="یادداشت")
    status = models.CharField(
        max_length=20,
        choices=SurgeryStatus.choices,
        default=SurgeryStatus.PLANNED,
        verbose_name="وضعیت",
    )

    # Idempotency guard: set True after OUT stock movements are created.
    stock_applied = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="موجودی اعمال شده",
        help_text="True پس از ایجاد حرکات موجودی OUT. از اعمال دوباره جلوگیری می‌کند.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "عمل جراحی"
        verbose_name_plural = "اعمال جراحی"
        ordering            = ["-surgery_date", "-created_at"]
        indexes = [
            models.Index(fields=["status"],       name="idx_surgery_status"),
            models.Index(fields=["surgery_date"], name="idx_surgery_date"),
        ]

    # ------------------------------------------------------------------
    # Business logic
    # ------------------------------------------------------------------

    @transaction.atomic
    def complete(self):
        """Transition to COMPLETED and create OUT StockMovements (idempotent).

        If stock_applied is already True, only the status is updated —
        no duplicate movements are created.

        Raises ValidationError if:
          - surgery is already CANCELLED
          - any product has insufficient stock (propagated from _apply_stock_delta)
        """
        if self.status == SurgeryStatus.CANCELLED:
            raise ValidationError("عمل جراحی لغو شده را نمی‌توان تکمیل کرد.")

        if not self.stock_applied:
            # Lazy imports avoid circular dependency: surgeries → inventory
            from inventory.models import MovementType, SourceType
            from inventory.services import StockService

            items = self.consumption_items.select_related("product").all()
            for item in items:
                StockService.create_movement(
                    product=item.product,
                    quantity=item.quantity,
                    movement_type=MovementType.OUT,
                    source_type=SourceType.SURGERY_CONSUMPTION,
                    reference_id=f"surgery-{self.pk}",
                    description=f"عمل جراحی #{self.pk} — {self.patient_name}",
                    movement_date=self.surgery_date,
                )
            self.stock_applied = True

        self.status = SurgeryStatus.COMPLETED
        self.save(update_fields=["status", "stock_applied", "updated_at"])

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        date_str = self.surgery_date.strftime("%Y-%m-%d")
        return f"جراحی #{self.pk} — {self.patient_name} ({date_str})"

    def __repr__(self) -> str:
        return (
            f"<Surgery pk={self.pk} "
            f"patient={self.patient_name!r} status={self.status}>"
        )


class SurgeryConsumptionItem(models.Model):
    """A single product consumed during a surgical procedure.

    Items are recorded before (or during) the surgery.  Actual stock
    deduction happens only when Surgery.complete() is called.
    """

    surgery = models.ForeignKey(
        Surgery,
        on_delete=models.CASCADE,
        related_name="consumption_items",
        verbose_name="عمل جراحی",
    )
    # String reference prevents import-time circular dependency.
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="surgery_consumption_items",
        verbose_name="محصول",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="مقدار مصرف",
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="واحد",
        help_text="اگر خالی باشد از محصول کپی می‌شود.",
    )
    notes = models.TextField(blank=True, default="", verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "قلم مصرف جراحی"
        verbose_name_plural = "اقلام مصرف جراحی"
        indexes = [
            models.Index(fields=["surgery"], name="idx_sci_surgery"),
            models.Index(fields=["product"], name="idx_sci_product"),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "مقدار باید بزرگ‌تر از صفر باشد."})

    # ------------------------------------------------------------------
    # Save — auto-fills unit from product
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if not self.unit and self.product_id:
            self.unit = self.product.unit
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.product.name} × {self.quantity} {self.unit}"

    def __repr__(self) -> str:
        return (
            f"<SurgeryConsumptionItem pk={self.pk} "
            f"product={self.product_id} qty={self.quantity}>"
        )


# ---------------------------------------------------------------------------
# SurgeryType
# ---------------------------------------------------------------------------

class SurgeryType(models.Model):
    name        = models.CharField(max_length=150, unique=True, verbose_name='نام عمل')
    code        = models.CharField(max_length=50,  unique=True, verbose_name='کد')
    base_rate   = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='نرخ پایه')
    description = models.TextField(blank=True, verbose_name='توضیحات')
    is_active   = models.BooleanField(default=True, verbose_name='فعال')
    created_at  = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at  = models.DateTimeField(auto_now=True,     verbose_name='آخرین ویرایش')

    class Meta:
        verbose_name        = 'نوع عمل جراحی'
        verbose_name_plural = 'انواع عمل جراحی'
        ordering            = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.code})'

    def get_active_commission_rule_count(self) -> int:
        return self.commission_rules.filter(is_active=True).count()

    def clean(self):
        super().clean()
        if self.code and not re.match(r'^[a-z0-9_]+$', self.code):
            raise ValidationError(
                {'code': 'کد باید فقط شامل حروف کوچک انگلیسی، اعداد و زیرخط باشد.'}
            )
        if self.base_rate is not None and self.base_rate < 0:
            raise ValidationError({'base_rate': 'نرخ پایه نمی‌تواند منفی باشد.'})
        if not self.is_active and self.pk and self.get_active_commission_rule_count() > 0:
            raise ValidationError(
                {'is_active': 'این نوع عمل دارای قوانین کمیسیون فعال است و قابل غیرفعال کردن نیست.'}
            )

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.lower()
        super().save(*args, **kwargs)
