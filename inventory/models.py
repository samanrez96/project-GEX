from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class ProductCategory(models.Model):
    """Self-referential category tree for inventory items.

    Depth is unbounded by schema but capped at 10 in property helpers to
    guard against corrupted circular data without raising RecursionError.
    The two root categories ("دارو", "تجهیزات") are seeded by data migration —
    they are never hardcoded here.
    """

    name = models.CharField(max_length=100, verbose_name="نام")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,  # never silently destroy a subtree
        related_name="children",
        verbose_name="دسته‌بندی والد",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name = "دسته‌بندی محصول"
        verbose_name_plural = "دسته‌بندی‌های محصول"
        ordering = ["name"]
        unique_together = [("name", "parent")]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def full_path(self) -> str:
        """Return slash-separated ancestor chain, root first.

        Caps at depth 10 so corrupted circular data never causes infinite
        recursion — returns the partial path collected so far instead.
        """
        parts = []
        node = self
        for _ in range(10):
            parts.append(node.name)
            if node.parent_id is None:
                break
            node = node.parent  # traverses up; relies on FK select_related
        else:
            parts.append("…")
        parts.reverse()
        return " / ".join(parts)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_children(self):
        """Return the QuerySet of direct children."""
        return ProductCategory.objects.filter(parent=self)

    def get_all_descendants(self, _depth: int = 0) -> list:
        """Return a flat list of all descendants (depth-first).

        Hard-stops at depth 10 to prevent a stack overflow on corrupted
        circular data. Returns whatever has been collected so far.
        """
        if _depth >= 10:
            return []
        result = []
        for child in self.get_children():
            result.append(child)
            result.extend(child.get_all_descendants(_depth=_depth + 1))
        return result

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        """Prevent a category from being its own ancestor (circular reference)."""
        if self.parent_id is None:
            return
        node = self.parent
        visited = set()
        while node is not None:
            if node.pk == self.pk:
                raise ValidationError(
                    "یک دسته‌بندی نمی‌تواند زیرشاخه خودش باشد (ارجاع دایره‌ای)."
                )
            if node.pk in visited:
                # corrupted chain — stop traversal
                break
            visited.add(node.pk)
            node = node.parent

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return self.full_path

    def __repr__(self) -> str:
        return f"<ProductCategory pk={self.pk} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

# Policy constant — referenced by _apply_stock_delta and CLI-31.
# Set to False: negative stock is never allowed. Any operation that would
# cause current_stock to drop below 0 raises ValidationError immediately.
# CLI-31 should catch this and surface it as "insufficient stock" to the user.
ALLOW_NEGATIVE_STOCK = False


class ProductType(models.TextChoices):
    MEDICINE  = "medicine",  "دارو"
    EQUIPMENT = "equipment", "تجهیزات"


class Product(models.Model):
    """Central inventory entity.

    current_stock is sacred — it must NEVER be written directly via the API
    or admin form. Use _apply_stock_delta() exclusively (called by
    StockMovement in CLI-11/12). Two guard layers enforce this:
      1. editable=False + read_only in all serializers (API/admin layer)
      2. save() raises ValueError if current_stock changed without the
         _skip_stock_guard flag (model layer)
    """

    name           = models.CharField(max_length=200, verbose_name="نام محصول")
    internal_code  = models.CharField(max_length=50, unique=True, verbose_name="کد داخلی")
    product_type   = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        verbose_name="نوع محصول",
    )
    category = models.ForeignKey(
        ProductCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="دسته‌بندی",
    )
    # Many-to-many shortcut — the through table (ProductVendor) is defined below.
    # product.vendors.all()  → Vendor queryset
    # vendor.products.all()  → Product queryset
    vendors = models.ManyToManyField(
        "Vendor",
        through="ProductVendor",
        related_name="products",
        blank=True,
        verbose_name="فروشندگان",
    )
    unit           = models.CharField(max_length=50, blank=True, default="", verbose_name="واحد اندازه‌گیری")
    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name="قیمت خرید",
    )
    sale_price     = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        blank=True, verbose_name="قیمت فروش",
    )
    barcode        = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name="بارکد",
    )
    # editable=False: hidden from all ModelForm/admin forms; only _apply_stock_delta touches it
    current_stock  = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0"),
        editable=False, verbose_name="موجودی فعلی",
    )
    minimum_stock  = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0"),
        verbose_name="حداقل موجودی (هشدار)",
    )
    internal_notes = models.TextField(blank=True, verbose_name="یادداشت داخلی")
    is_active      = models.BooleanField(default=True, verbose_name="فعال")
    created_at     = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at     = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "محصول"
        verbose_name_plural = "محصولات"
        ordering            = ["-created_at"]
        constraints = [
            # Allow multiple NULL barcodes (NULL ≠ NULL in SQL) while
            # keeping a true unique constraint on non-null values.
            models.UniqueConstraint(
                fields=["barcode"],
                condition=models.Q(barcode__isnull=False),
                name="unique_barcode_when_set",
            ),
        ]
        indexes = [
            models.Index(fields=["internal_code"],  name="idx_product_internal_code"),
            models.Index(fields=["barcode"],         name="idx_product_barcode"),
            models.Index(fields=["product_type"],    name="idx_product_type"),
            models.Index(fields=["is_active"],       name="idx_product_is_active"),
            # Added for price-range filters (CLI-11) and low-stock ordering
            models.Index(fields=["purchase_price"],  name="idx_product_purchase_price"),
            models.Index(fields=["current_stock"],   name="idx_product_current_stock"),
        ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_low_stock(self) -> bool:
        """True when stock is at or below the alert threshold (and threshold is set)."""
        return self.minimum_stock > 0 and self.current_stock <= self.minimum_stock

    @property
    def is_out_of_stock(self) -> bool:
        return self.current_stock <= 0

    # ------------------------------------------------------------------
    # Stock mutation — the ONLY sanctioned way to change current_stock
    # ------------------------------------------------------------------

    @transaction.atomic
    def _apply_stock_delta(self, delta: Decimal, save: bool = True) -> None:
        """Add delta (positive or negative) to current_stock.

        Reads the authoritative stock value from the database with a row-level
        lock (SELECT FOR UPDATE) on databases that support it (PostgreSQL,
        MySQL). This prevents lost-update races when two concurrent requests
        try to adjust the same product's stock simultaneously.

        On SQLite (used in tests and development), SELECT FOR UPDATE is not
        supported; Django silently skips the clause, which is safe because
        SQLite serialises writes at the file level anyway.

        Raises ValidationError if the result would be negative and
        ALLOW_NEGATIVE_STOCK is False (see module constant).
        Must be called inside a transaction when chained with StockMovement.
        """
        from django.db import connection

        # Fetch the current DB value with an optional row lock.
        qs = Product.objects.filter(pk=self.pk)
        if connection.features.has_select_for_update:
            qs = qs.select_for_update()
        db_stock = qs.values_list("current_stock", flat=True).get()

        new_stock = db_stock + Decimal(str(delta))
        if not ALLOW_NEGATIVE_STOCK and new_stock < 0:
            raise ValidationError(
                f"موجودی کافی نیست. موجودی فعلی: {db_stock}، "
                f"تغییر درخواستی: {delta}"
            )
        self.current_stock = new_stock
        if save:
            self._skip_stock_guard = True
            try:
                self.save(update_fields=["current_stock", "updated_at"])
            finally:
                self._skip_stock_guard = False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        super().clean()

        # Category-type consistency check.
        # Skipped when category is None (category is optional — see design notes).
        if self.category_id is not None and self.category is not None:
            root = self.category
            visited = set()
            while root.parent_id is not None:
                if root.pk in visited:
                    break
                visited.add(root.pk)
                root = root.parent

            expected_root_name = (
                "دارو" if self.product_type == ProductType.MEDICINE else "تجهیزات"
            )
            if root.name != expected_root_name:
                raise ValidationError(
                    {
                        "category": (
                            f"دسته‌بندی انتخابی با نوع محصول سازگار نیست. "
                            f"برای نوع «{self.get_product_type_display()}» "
                            f"باید زیرمجموعه «{expected_root_name}» باشد."
                        )
                    }
                )

    # ------------------------------------------------------------------
    # Save guard — model-level enforcement for current_stock immutability
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if self.pk is not None and not getattr(self, "_skip_stock_guard", False):
            db_stock = (
                Product.objects.filter(pk=self.pk)
                .values_list("current_stock", flat=True)
                .first()
            )
            if db_stock is not None and db_stock != self.current_stock:
                raise ValueError(
                    "current_stock cannot be modified directly. "
                    "Use _apply_stock_delta() instead."
                )
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.internal_code} — {self.name}"

    def __repr__(self) -> str:
        return f"<Product pk={self.pk} code={self.internal_code!r}>"


# ---------------------------------------------------------------------------
# Vendor (Supplier)
# ---------------------------------------------------------------------------


class Vendor(models.Model):
    """Supplier / vendor that provides products or services to the clinic.

    Financial tracking uses two balance fields:
      opening_balance — set once when the vendor record is created (what the
                        clinic owed them on day one).
      current_balance — updated by purchase/payment transactions (CLI-13+).

    Sign convention: positive current_balance means the clinic owes money to
    the vendor; negative means the clinic has a credit with the vendor.
    """

    name         = models.CharField(max_length=255, verbose_name="نام فروشنده")
    phone_number = models.CharField(max_length=20, blank=True, default="", verbose_name="شماره تلفن")
    email        = models.EmailField(blank=True, default="", verbose_name="ایمیل")
    address      = models.TextField(blank=True, default="", verbose_name="آدرس")
    notes        = models.TextField(blank=True, default="", verbose_name="یادداشت")
    is_active    = models.BooleanField(default=True, verbose_name="فعال")

    # Financial information
    opening_balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="موجودی اولیه",
        help_text=(
            "مانده‌ی اولیه‌ای که کلینیک هنگام ثبت فروشنده به وی بدهکار/بستانکار بود."
        ),
    )
    current_balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="موجودی جاری",
        help_text=(
            "مانده‌ی جاری حساب. مثبت: کلینیک بدهکار است. منفی: کلینیک طلبکار است."
        ),
    )
    tax_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="کد اقتصادی / شناسه مالیاتی",
    )
    bank_account = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="اطلاعات حساب بانکی",
        help_text="شماره شبا یا شماره حساب جاری برای پرداخت.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "فروشنده"
        verbose_name_plural = "فروشندگان"
        ordering            = ["name"]
        indexes = [
            models.Index(fields=["is_active"], name="idx_vendor_is_active"),
        ]

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<Vendor pk={self.pk} name={self.name!r}>"


# ---------------------------------------------------------------------------
# VendorPhone (additional phone numbers for a vendor)
# ---------------------------------------------------------------------------


class VendorPhone(models.Model):
    """Additional phone numbers for a vendor beyond the primary phone_number."""

    vendor = models.ForeignKey(
        Vendor,
        related_name="additional_phones",
        on_delete=models.CASCADE,
    )
    phone = models.CharField(max_length=20, verbose_name="شماره تلفن")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "شماره تلفن دیگر"
        verbose_name_plural = "شماره‌های تلفن دیگر"
        ordering = ["order", "created_at"]
        unique_together = [("vendor", "phone")]

    def __str__(self) -> str:
        return f"{self.vendor.name} — {self.phone}"

    def __repr__(self) -> str:
        return f"<VendorPhone pk={self.pk} vendor={self.vendor_id} phone={self.phone!r}>"


# ---------------------------------------------------------------------------
# ProductVendor (explicit many-to-many through table)
# ---------------------------------------------------------------------------


class ProductVendor(models.Model):
    """Explicit many-to-many through table linking Product to Vendor.

    Stores supplier-specific product data: the vendor's own name/code for
    this product, their quoted price, lead time, and ordering constraints.

    Reverse accessors:
      product.product_vendors.all()  — all vendor rows for this product
      vendor.product_vendors.all()   — all product rows from this vendor

    Convenient M2M traversal (via the Product.vendors accessor):
      product.vendors.all()          — Vendor queryset
      vendor.products.all()          — Product queryset
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_vendors",
        verbose_name="محصول",
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="product_vendors",
        verbose_name="فروشنده",
    )

    # ------------------------------------------------------------------
    # Supplier-specific identification
    # ------------------------------------------------------------------
    supplier_product_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="نام محصول نزد فروشنده",
        help_text="نامی که فروشنده برای این محصول به‌کار می‌برد.",
    )
    supplier_product_code = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="کد محصول نزد فروشنده",
        help_text="کد یا SKU فروشنده برای این محصول.",
    )

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="قیمت واحد",
    )
    currency = models.CharField(
        max_length=10,
        default="IRR",
        verbose_name="واحد پول",
        help_text="کد ارز، مثلاً IRR، USD، EUR.",
    )
    last_price_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ آخرین قیمت",
        help_text="تاریخی که این قیمت آخرین بار تأیید یا به‌روز شد.",
    )

    # ------------------------------------------------------------------
    # Ordering constraints
    # ------------------------------------------------------------------
    minimum_order_quantity = models.PositiveIntegerField(
        default=1,
        verbose_name="حداقل مقدار سفارش",
    )
    lead_time_days = models.PositiveIntegerField(
        default=0,
        verbose_name="مدت تحویل (روز)",
        help_text="تعداد روزهای کاری تا تحویل سفارش.",
    )

    # ------------------------------------------------------------------
    # Status & notes
    # ------------------------------------------------------------------
    is_primary = models.BooleanField(default=False, verbose_name="فروشنده اصلی")
    is_active  = models.BooleanField(default=True,  verbose_name="فعال")
    notes      = models.TextField(blank=True, default="", verbose_name="یادداشت")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "فروشنده محصول"
        verbose_name_plural = "فروشندگان محصول"
        ordering            = ["-is_primary", "vendor__name"]
        # The old unique_product_vendor constraint on (product, vendor) was too
        # restrictive: the same vendor can supply the same product at different
        # prices or with different ordering conditions.  Exact-duplicate prevention
        # is now enforced at the serializer/form layer instead of the DB layer.
        indexes = [
            models.Index(fields=["product"],               name="idx_pv_product"),
            models.Index(fields=["vendor"],                name="idx_pv_vendor"),
            models.Index(fields=["supplier_product_code"], name="idx_pv_supplier_code"),
            models.Index(fields=["is_active"],             name="idx_pv_is_active"),
        ]

    def __str__(self) -> str:
        label = " (اصلی)" if self.is_primary else ""
        name  = self.supplier_product_name or self.product.name
        return f"{self.vendor.name}{label} ← {name}"

    def __repr__(self) -> str:
        return f"<ProductVendor product={self.product_id} vendor={self.vendor_id}>"


# ---------------------------------------------------------------------------
# StockMovement
# ---------------------------------------------------------------------------


class MovementType(models.TextChoices):
    IN         = "IN",         "ورود به انبار"
    OUT        = "OUT",        "خروج از انبار"
    ADJUSTMENT = "ADJUSTMENT", "تعدیل موجودی"


class SourceType(models.TextChoices):
    PURCHASE            = "PURCHASE",            "خرید"
    SURGERY_CONSUMPTION = "SURGERY_CONSUMPTION", "مصرف در عمل جراحی"
    MANUAL_ADJUSTMENT   = "MANUAL_ADJUSTMENT",   "تعدیل دستی"
    RETURN              = "RETURN",              "مرجوعی"
    OTHER               = "OTHER",               "سایر"


class StockMovement(models.Model):
    """Immutable audit-log of every inventory change.

    Each row records one increase (IN / ADJUSTMENT) or decrease (OUT) in a
    product's current_stock. The save() method atomically updates
    Product.current_stock via _apply_stock_delta(); stock must NEVER be
    changed without creating a StockMovement.

    Direction rules:
      IN / ADJUSTMENT → delta = +quantity (increases stock)
      OUT             → delta = -quantity (decreases stock)

    Append-only convention: the API viewset exposes only POST + GET.
    Do not delete or edit existing rows — this table is the audit trail.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,  # never silently destroy audit history
        related_name="stock_movements",
        verbose_name="محصول",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="مقدار",
        help_text="همیشه مثبت. جهت تغییر موجودی از نوع حرکت تعیین می‌شود.",
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="واحد",
        help_text="واحد اندازه‌گیری هنگام ثبت (برای تاریخچه). اگر خالی باشد از محصول کپی می‌شود.",
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        verbose_name="نوع حرکت",
    )
    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
        default=SourceType.OTHER,
        verbose_name="منبع حرکت",
    )
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="شناسه مرجع",
        help_text="شناسه شیء مرتبط (مثلاً شناسه فاکتور خرید یا عمل جراحی).",
    )
    movement_date = models.DateTimeField(
        default=timezone.now,
        verbose_name="تاریخ حرکت",
        help_text="زمان واقعی رویداد — ممکن است با تاریخ ثبت (created_at) متفاوت باشد.",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ثبت")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "حرکت موجودی"
        verbose_name_plural = "حرکات موجودی"
        ordering            = ["-movement_date", "-created_at"]
        indexes = [
            models.Index(fields=["product"],       name="idx_sm_product"),
            models.Index(fields=["movement_type"], name="idx_sm_movement_type"),
            models.Index(fields=["source_type"],   name="idx_sm_source_type"),
            models.Index(fields=["movement_date"], name="idx_sm_movement_date"),
            models.Index(fields=["reference_id"],  name="idx_sm_reference_id"),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError(
                {"quantity": "مقدار باید بزرگ‌تر از صفر باشد."}
            )

    # ------------------------------------------------------------------
    # Save — auto-fills unit and atomically applies the stock delta on create
    # ------------------------------------------------------------------

    @transaction.atomic
    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # Inherit unit from product when not explicitly provided
        if is_new and not self.unit:
            self.unit = self.product.unit

        super().save(*args, **kwargs)

        if is_new:
            delta = (
                self.quantity
                if self.movement_type != MovementType.OUT
                else -self.quantity
            )
            # _apply_stock_delta is itself @transaction.atomic → becomes a savepoint
            self.product._apply_stock_delta(delta, save=True)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return (
            f"{self.get_movement_type_display()} | "
            f"{self.product.internal_code} | "
            f"{self.quantity} {self.unit}"
        )

    def __repr__(self) -> str:
        return (
            f"<StockMovement pk={self.pk} product={self.product_id} "
            f"type={self.movement_type} qty={self.quantity}>"
        )


# ---------------------------------------------------------------------------
# Purchase / PurchaseItem
# ---------------------------------------------------------------------------


class PurchaseStatus(models.TextChoices):
    PENDING   = "PENDING",   "در انتظار تأیید"
    CONFIRMED = "CONFIRMED", "تأیید شده"
    CANCELLED = "CANCELLED", "لغو شده"


class Purchase(models.Model):
    """A purchase order from a vendor.

    Workflow:
      1. Create Purchase (status=PENDING) + add PurchaseItems.
      2. Call purchase.confirm() to transition to CONFIRMED.
         confirm() creates one IN StockMovement per item and sets
         stock_applied=True so the operation is idempotent.

    The stock_applied flag ensures that calling confirm() more than once
    never creates duplicate stock movements.
    """

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name="purchases",
        verbose_name="فروشنده",
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="شماره مرجع / فاکتور",
        help_text="شماره فاکتور یا شماره سفارش خرید.",
    )
    purchase_date = models.DateTimeField(
        default=timezone.now,
        verbose_name="تاریخ خرید",
    )
    status = models.CharField(
        max_length=20,
        choices=PurchaseStatus.choices,
        default=PurchaseStatus.PENDING,
        verbose_name="وضعیت",
    )
    notes = models.TextField(blank=True, default="", verbose_name="یادداشت")

    # Idempotency guard: set True after stock movements are created.
    # editable=False keeps it out of admin forms; only confirm() writes it.
    stock_applied = models.BooleanField(
        default=False,
        editable=False,
        verbose_name="موجودی اعمال شده",
        help_text="True پس از ایجاد حرکات موجودی. از اعمال دوباره جلوگیری می‌کند.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "خرید"
        verbose_name_plural = "خریدها"
        ordering            = ["-purchase_date", "-created_at"]
        indexes = [
            models.Index(fields=["vendor"],        name="idx_purchase_vendor"),
            models.Index(fields=["status"],        name="idx_purchase_status"),
            models.Index(fields=["purchase_date"], name="idx_purchase_date"),
        ]

    # ------------------------------------------------------------------
    # Business logic
    # ------------------------------------------------------------------

    @transaction.atomic
    def cancel(self):
        """Cancel the purchase, reversing stock if already confirmed.

        If stock_applied is True, creates one OUT StockMovement per item to
        undo the earlier IN movements.  The whole reversal is atomic: if any
        product has insufficient stock (consumed downstream), the transaction
        rolls back and a ValidationError is raised naming the product.

        After saving CANCELLED status, PriceService.recalculate_product_price
        is called for each affected product so that the next-latest confirmed
        purchase price fills in (or the price stays unchanged if none remains).

        Raises ValidationError if:
          - purchase is already CANCELLED
          - stock_applied is True and reversal would make any product negative
            (propagated from _apply_stock_delta via StockService)
        """
        if self.status == PurchaseStatus.CANCELLED:
            raise ValidationError("این خرید قبلاً لغو شده است.")

        was_confirmed = self.stock_applied

        # Collect all items before setting status — needed for both stock
        # reversal (CONFIRMED) and price recalculation (any status).
        all_items = list(self.items.select_related("product").all())

        if was_confirmed:
            from inventory.services import StockService  # avoid circular import

            for item in all_items:
                try:
                    StockService.create_movement(
                        product=item.product,
                        quantity=item.quantity,
                        movement_type=MovementType.OUT,
                        source_type=SourceType.RETURN,
                        reference_id=f"cancel-purchase-{self.pk}",
                        description=f"برگشت خرید — {self.vendor.name}",
                    )
                except ValidationError:
                    raise ValidationError(
                        f"لغو خرید امکان‌پذیر نیست: موجودی "
                        f"«{item.product.name}» برای برگشت ناکافی است."
                    )

        self.status = PurchaseStatus.CANCELLED
        self.save(update_fields=["status", "updated_at"])

        # Recalculate prices after this purchase is CANCELLED in DB so the
        # query inside recalculate_product_price correctly excludes it.
        # Applies to both CONFIRMED and PENDING cancellations.
        if all_items:
            from inventory.services import PriceService
            product_ids = {
                item.product_id for item in all_items
                if item.unit_price and item.unit_price > 0
            }
            for product_id in product_ids:
                PriceService.recalculate_product_price(product_id)

    @transaction.atomic
    def confirm(self):
        """Transition to CONFIRMED and create IN StockMovements (idempotent).

        If stock_applied is already True, only the status is updated —
        no duplicate movements are created.

        After saving the CONFIRMED status, PriceService is called to:
          1. Update or create ProductVendor.unit_price for each item's vendor.
          2. Recalculate Product.purchase_price from the overall latest confirmed
             purchase (so an older purchase confirmed after a newer one never
             overwrites the newer price).

        Raises ValidationError if:
          - purchase is already CANCELLED
          - purchase has no items
          - any product would drop below zero (propagated from _apply_stock_delta)
        """
        if self.status == PurchaseStatus.CANCELLED:
            raise ValidationError("خرید لغو شده را نمی‌توان تأیید کرد.")

        # Always check for items — this runs even on idempotent re-confirm so that
        # a purchase whose items were deleted after confirmation cannot be re-confirmed.
        if not self.items.exists():
            raise ValidationError(
                "برای تأیید خرید، ابتدا حداقل یک قلم خرید اضافه کنید."
            )

        items_to_sync = []  # populated only on first confirm (idempotency guard)

        if not self.stock_applied:
            from inventory.services import StockService  # avoid circular import

            items_qs = self.items.select_related("product").all()
            items_list = list(items_qs)
            ref   = f"purchase-{self.pk}"
            label = self.reference_number or f"#{self.pk}"
            for item in items_list:
                StockService.create_movement(
                    product=item.product,
                    quantity=item.quantity,
                    movement_type=MovementType.IN,
                    source_type=SourceType.PURCHASE,
                    reference_id=ref,
                    description=(
                        f"خرید {label} — {self.vendor.name}"
                    ),
                    movement_date=self.purchase_date,
                )

            items_to_sync = [i for i in items_list if i.unit_price and i.unit_price > 0]
            self.stock_applied = True

        self.status = PurchaseStatus.CONFIRMED
        self.save(update_fields=["status", "stock_applied", "updated_at"])

        # Price sync runs AFTER save so this purchase is already CONFIRMED in
        # the DB when recalculate_product_price queries for the latest purchase.
        if items_to_sync:
            from inventory.services import PriceService
            PriceService.sync_purchase_vendor_price(self, items_to_sync)
            distinct_product_ids = {item.product_id for item in items_to_sync}
            for product_id in distinct_product_ids:
                PriceService.recalculate_product_price(product_id)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        ref = f" ({self.reference_number})" if self.reference_number else ""
        return f"خرید #{self.pk}{ref} — {self.vendor.name}"

    def __repr__(self) -> str:
        return f"<Purchase pk={self.pk} vendor={self.vendor_id} status={self.status}>"


class PurchaseItem(models.Model):
    """A single product line inside a purchase order."""

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="خرید",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="purchase_items",
        verbose_name="محصول",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="مقدار",
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="واحد",
        help_text="اگر خالی باشد از محصول کپی می‌شود.",
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="قیمت واحد",
    )
    notes = models.TextField(blank=True, default="", verbose_name="یادداشت")
    manual_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="جمع ردیف دستی",
        help_text="اگر خالی باشد، جمع ردیف به‌صورت خودکار (مقدار × قیمت واحد) محاسبه می‌شود.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="آخرین ویرایش")

    class Meta:
        verbose_name        = "قلم خرید"
        verbose_name_plural = "اقلام خرید"
        indexes = [
            models.Index(fields=["purchase"], name="idx_pi_purchase"),
            models.Index(fields=["product"],  name="idx_pi_product"),
        ]

    # ------------------------------------------------------------------
    # Total helpers
    # ------------------------------------------------------------------

    @property
    def calculated_total(self) -> Decimal:
        return self.quantity * self.unit_price

    @property
    def effective_total(self) -> Decimal:
        """Return manual_total when set; otherwise quantity × unit_price."""
        if self.manual_total is not None:
            return self.manual_total
        return self.calculated_total

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": "مقدار باید بزرگ‌تر از صفر باشد."})
        if self.manual_total is not None and self.manual_total < 0:
            raise ValidationError({"manual_total": "جمع ردیف نمی‌تواند منفی باشد."})

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
            f"<PurchaseItem pk={self.pk} "
            f"product={self.product_id} qty={self.quantity}>"
        )
