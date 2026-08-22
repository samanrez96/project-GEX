from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, Q

from common.uploads import employee_document_upload_path, validate_image_upload


# ---------------------------------------------------------------------------
# Gender choices
# ---------------------------------------------------------------------------

class GenderChoice(models.TextChoices):
    MALE   = "male",   "مرد"
    FEMALE = "female", "زن"
    OTHER  = "other",  "سایر"


# ---------------------------------------------------------------------------
# JobPosition — must be defined before Employee (FK target)
# ---------------------------------------------------------------------------

class JobPosition(models.Model):
    name        = models.CharField(max_length=100, unique=True, verbose_name="نام پوزیشن")
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    is_active   = models.BooleanField(default=True, verbose_name="فعال")
    created_at  = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at  = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "پوزیشن شغلی"
        verbose_name_plural = "پوزیشن‌های شغلی"
        ordering            = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_active_employee_count(self) -> int:
        # Uses annotation when available (admin list view — zero extra queries).
        # Falls back to a COUNT query for single-object contexts (clean(), API).
        if hasattr(self, "_active_employee_count"):
            return self._active_employee_count
        return self.employees.filter(is_active=True).count()

    def clean(self):
        super().clean()
        if not self.is_active and self.pk:
            if self.get_active_employee_count() > 0:
                raise ValidationError(
                    "این پوزیشن دارای کارمندان فعال است و نمی‌توان آن را غیرفعال کرد."
                )


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

class Employee(models.Model):
    """Staff / personnel record for the surgery clinic."""

    # ── Identity ─────────────────────────────────────────────────────
    full_name = models.CharField(
        max_length=200,
        verbose_name="نام و نام خانوادگی",
    )
    # Not currently surfaced on the visible admin form (full_name remains
    # the single identity field there) — present so historically-applied
    # migration 0005 and the physical database schema stay consistent.
    first_name = models.CharField(
        max_length=100, blank=True, default='', verbose_name='نام',
    )
    last_name = models.CharField(
        max_length=100, blank=True, default='', verbose_name='نام خانوادگی',
    )
    national_id = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="کد ملی",
        help_text="کد ملی باید منحصربه‌فرد باشد.",
    )
    gender = models.CharField(
        max_length=10,
        choices=GenderChoice.choices,
        verbose_name="جنسیت",
    )

    # ── Job ──────────────────────────────────────────────────────────
    job_position = models.ForeignKey(
        JobPosition,
        on_delete=models.PROTECT,
        related_name="employees",
        verbose_name="سمت / عنوان شغلی",
    )
    start_date = models.DateField(
        verbose_name="تاریخ استخدام",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
    )

    # ── Contact ──────────────────────────────────────────────────────
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name="ایمیل",
    )
    personal_phone = models.CharField(
        max_length=20,
        verbose_name="تلفن شخصی",
    )
    emergency_contact_phone = models.CharField(
        max_length=20,
        verbose_name="تلفن اضطراری",
        help_text="شماره تماس در مواقع اضطراری (مثلاً خانواده).",
    )
    address = models.TextField(
        blank=True,
        default="",
        verbose_name="آدرس",
    )

    # ── Hourly wage (legacy) ───────────────────────────────────────────
    # Superseded by payroll.HourlyRate (effective-dated, historical rates)
    # for any employee configured via wage_type='hourly'. Kept only so
    # existing HourlyWorkRecord rows and pre-migration Employees keep
    # working — never written to by the new hourly payroll flow.
    hourly_rate = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="نرخ هر ساعت (قدیمی / بایگانی)",
        help_text=(
            "بخشی از سامانه قدیمی حقوق ساعتی — فقط برای سازگاری با رکوردهای قبلی "
            "(«رکوردهای ساعات کاری ماهانه») نگه داشته شده و برای کارمندان جدید استفاده نمی‌شود."
        ),
    )

    # ── Notes ────────────────────────────────────────────────────────
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات / یادداشت",
    )

    # ── Timestamps ───────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "کارمند"
        verbose_name_plural = "کارمندان"
        ordering            = ["full_name"]
        indexes = [
            models.Index(fields=["is_active"],   name="idx_emp_is_active"),
            models.Index(fields=["start_date"],  name="idx_emp_start_date"),
            models.Index(fields=["national_id"], name="idx_emp_national_id"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.job_position}"

    def __repr__(self) -> str:
        return f"<Employee pk={self.pk} name={self.full_name!r}>"


# ---------------------------------------------------------------------------
# EmployeeDocument — repeatable identity-document uploads for an Employee.
#
# The canonical document system, replacing the old fixed credential_image_1 /
# credential_image_2 fields (removed in migration 0008; any pre-existing
# non-empty files were copied here by the migration 0007 data migration
# first). An employee can have any number of documents. Managed exclusively
# as an inline formset on the Employee add/edit form (see employees/admin.py)
# — no standalone admin page/menu entry exists for this model.
# ---------------------------------------------------------------------------

class EmployeeDocument(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="کارمند",
    )
    file = models.ImageField(
        upload_to=employee_document_upload_path,
        validators=[validate_image_upload],
        verbose_name="مدرک",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name        = "مدرک کارمند"
        verbose_name_plural = "مدارک کارمند"
        ordering            = ["created_at", "id"]

    def __str__(self) -> str:
        return f"مدرک {self.employee.full_name} — #{self.pk}"

    def save(self, *args, **kwargs):
        old_name = ''
        if self.pk:
            old = EmployeeDocument.objects.filter(pk=self.pk).values('file').first()
            if old:
                old_name = old['file'] or ''

        super().save(*args, **kwargs)

        new_name = self.file.name or ''
        if old_name and old_name != new_name:
            storage = self.file.storage

            def _delete_stale(storage=storage, name=old_name):
                try:
                    if storage.exists(name):
                        storage.delete(name)
                except Exception:
                    pass

            transaction.on_commit(_delete_stale)

    def delete(self, *args, **kwargs):
        storage, name = self.file.storage, self.file.name
        result = super().delete(*args, **kwargs)

        if name:
            def _cleanup():
                try:
                    if storage.exists(name):
                        storage.delete(name)
                except Exception:
                    pass
            transaction.on_commit(_cleanup)

        return result


# ---------------------------------------------------------------------------
# EmployeePurchaseCommission — purchase-based employee commission
# ---------------------------------------------------------------------------

class EmployeePurchaseCommission(models.Model):
    """Commission paid to an employee based on a purchase/invoice saving.

    Distinct from surgery-based CommissionTransaction in payroll.
    """

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="purchase_commissions",
        verbose_name="کارمند",
    )
    purchase = models.ForeignKey(
        "inventory.Purchase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_commissions",
        verbose_name="فاکتور خرید",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="مبلغ کمیسیون (تومان)",
    )
    commission_date = models.DateField(verbose_name="تاریخ کمیسیون")
    description = models.TextField(blank=True, default="", verbose_name="توضیحات / دلیل")
    created_at  = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at  = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "کمیسیون خرید"
        verbose_name_plural = "کمیسیون‌های خرید"
        ordering            = ["-commission_date"]
        indexes = [
            models.Index(fields=["employee"],        name="idx_epc_employee"),
            models.Index(fields=["commission_date"], name="idx_epc_date"),
        ]

    def __str__(self) -> str:
        return f"{self.employee.full_name} — {self.amount:,} تومان ({self.commission_date})"
