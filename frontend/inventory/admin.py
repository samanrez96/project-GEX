from decimal import Decimal

from django import forms
from django.contrib import admin

from common.admin import (
    DECIMAL_FORMFIELD_OVERRIDES,
    DecimalWidget,
    JALALI_FORMFIELD_OVERRIDES,
    JalaliAdminDatesMixin,
    JalaliFormDateForDateTimeField,
    MONEY_FORMFIELD_OVERRIDES,
    MoneyInput,
    clean_decimal_display,
)
from django.db.models import Count
from django.utils.html import format_html
from django.forms.models import BaseInlineFormSet

from inventory.models import (
    MovementType,
    Product,
    ProductCategory,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    SourceType,
    StockMovement,
    Vendor,
    VendorPhone,
)


 
# ---------------------------------------------------------------------------
# ProductVendor admin inline — form helpers (UI only, no model/logic changes)
# ---------------------------------------------------------------------------

# Currency dropdown choices: stored value → Persian display label.
# The model stores "IRR" (the default); showing "تومان" is display-only.
_CURRENCY_CHOICES = [
    ("IRR", "تومان"),
    ("USD", "USD"),
    ("EUR", "EUR"),
]



class ProductVendorInlineForm(forms.ModelForm):
    """Custom form for ProductVendor tabular inline on the Product edit page.

    Changes vs. default:
    - currency field: text input → Select with تومان/USD/EUR labels (UI only).
    - unit_price widget: strips trailing .00 from the displayed value.

    No model fields, validation rules, or save behavior are changed.
    """

    class Meta:
        model = ProductVendor
        fields = '__all__'
        widgets = {
            'currency': forms.Select(choices=_CURRENCY_CHOICES),
            'unit_price': MoneyInput(
                attrs={'style': 'direction:ltr;text-align:right;min-width:80px;'}
            ),
        }


# ---------------------------------------------------------------------------
# ProductCategory admin
# ---------------------------------------------------------------------------

class ChildCategoryInline(admin.StackedInline):
    model = ProductCategory
    fk_name = "parent"
    extra = 0
    fields = ("name", "description", "is_active")
    show_change_link = True
    verbose_name = "زیرشاخه مستقیم"
    verbose_name_plural = "زیرشاخه‌های مستقیم"


@admin.register(ProductCategory)
class ProductCategoryAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display   = ("name", "parent", "is_active", "created_at_jalali")
    list_filter    = ("is_active", "parent")
    search_fields  = ("name", "description")
    readonly_fields = ("created_at_jalali", "updated_at_jalali")
    inlines        = [ChildCategoryInline]

    fieldsets = (
        ("اطلاعات اصلی", {
            "fields": ("name", "description", "parent", "is_active"),
        }),
        ("زمان‌بندی", {
            "fields": ("created_at_jalali", "updated_at_jalali"),
        }),
    )


# ---------------------------------------------------------------------------
# Product admin
# ---------------------------------------------------------------------------

class ProductAdminForm(forms.ModelForm):
    """Custom form for Product admin.

    Adds a virtual ``initial_stock`` field (not a model field) that is
    processed by ``ProductAdmin.save_model()`` to create an opening
    MANUAL_ADJUSTMENT StockMovement when a new product is added.
    On edit forms the field is excluded from fieldsets and therefore never
    rendered or processed.

    ``desired_current_stock``/``stock_adjustment_reason`` are the edit-form
    counterpart: also virtual (Product.current_stock stays editable=False —
    see inventory/models.py), also excluded from the form entirely (not just
    hidden) whenever ProductAdmin.get_fieldsets() omits them for a
    non-main-administrator request, so a forged POST value from an
    unauthorized user has no field to bind to in the first place. The
    actual stock change is never applied here directly — save_model()
    hands the validated (desired_quantity, reason) pair to
    StockService.adjust_to_quantity(), the same canonical service any
    other stock correction would use.
    """

    initial_stock = forms.DecimalField(
        label="موجودی اولیه",
        required=False,
        min_value=Decimal("0"),
        widget=DecimalWidget(),
        help_text="موجودی اولیه را وارد کنید — یک حرکت انبار دستی ثبت می‌شود.",
    )

    unit = forms.CharField(
        label="واحد",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثلاً عدد، بسته، جعبه"}),
    )

    # required=False at the class level: Django's ModelFormMetaclass always
    # re-merges explicitly *declared* form fields back onto every generated
    # form class regardless of Meta.fields/the fields=[...] admin passes to
    # modelform_factory() — flatten_fieldsets() only controls what the
    # *template* renders, not what the form *validates*. A required=True
    # field declared here would therefore also apply (and silently fail,
    # since it's rendered nowhere) on the add form and on the edit form for
    # unauthorized users. ProductAdmin.get_form() is what actually makes
    # this required (and only for an authorized user editing an existing
    # Product) or removes it from the form entirely otherwise — see there.
    desired_current_stock = forms.DecimalField(
        label="موجودی فعلی",
        required=False,
        min_value=Decimal("0"),
        max_digits=12,
        decimal_places=3,
        widget=DecimalWidget(),
        help_text="تغییر این مقدار به‌صورت یک حرکت اصلاح موجودی در تاریخچه ثبت می‌شود.",
    )

    stock_adjustment_reason = forms.CharField(
        label="دلیل اصلاح موجودی (اختیاری)",
        required=False,
        help_text="اختیاری — در صورت نیاز، علت اصلاح موجودی را وارد کنید.",
        widget=forms.TextInput(attrs={"placeholder": "مثلاً اصلاح شمارش انبار"}),
    )

    class Meta:
        model  = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prefill with the real, current-at-page-load stock — never a
        # stale or guessed number. Only meaningful on an unbound (GET) form;
        # once bound, Django renders the submitted value instead regardless
        # of `initial`, so setting this unconditionally is safe.
        if self.instance and self.instance.pk and "desired_current_stock" in self.fields:
            self.fields["desired_current_stock"].initial = self.instance.current_stock

    # No clean() override needed anymore: stock_adjustment_reason is fully
    # optional now — StockService.adjust_to_quantity() falls back to a
    # generic "اصلاح دستی موجودی" description when it's left blank, so
    # there is nothing left to cross-validate here between
    # desired_current_stock and stock_adjustment_reason.


@admin.register(Product)
class ProductAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    change_list_template = "admin/inventory/product/change_list.html"
    # Use Django's built-in generic change_form.html instead of the app-specific one.
    # The app-specific change_form.html is a read-only detail view (for /detail/ URL);
    # it must NOT be used for /change/ (edit) or Django renders a read-only page.
    change_form_template = "admin/change_form.html"
    form                 = ProductAdminForm
    formfield_overrides  = {**JALALI_FORMFIELD_OVERRIDES, **DECIMAL_FORMFIELD_OVERRIDES}

    list_display        = (
        "internal_code", "name", "product_type",
        "purchase_price", "current_stock", "minimum_stock",
        "is_low_stock",
    )
    list_display_links  = ("internal_code", "name")
    list_filter         = ("product_type", "is_active")
    search_fields       = ("name", "internal_code")
    # Fields hidden from every form (kept in DB but not managed via admin UI).
    exclude             = ("sale_price", "barcode", "category", "is_active", "vendors")

    class Media:
        js = ('admin/js/product_add_form.js',)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _has_confirmed_purchase(self, obj):
        """True if *obj* has at least one CONFIRMED purchase item with price > 0.

        Used to decide whether purchase_price is auto-managed (read-only) or
        still a manual/fallback value (editable).
        """
        return PurchaseItem.objects.filter(
            product=obj,
            purchase__status=PurchaseStatus.CONFIRMED,
            unit_price__gt=0,
        ).exists()

    # ── Dynamic form configuration ────────────────────────────────────────────

    def _can_adjust_stock(self, request):
        """Only the main administrator may edit موجودی فعلی from this form —
        stock adjustment is sensitive enough to need more than ordinary
        Product change permission. Everyone else keeps the existing
        read-only current_stock_display exactly as before."""
        from accounts.permissions import is_main_administrator
        return is_main_administrator(request.user)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            # Add form: only timestamps are readonly; purchase_price is editable.
            return ("created_at_jalali", "updated_at_jalali")

        # Edit form: current_stock is read-only unless the user may adjust it
        # (in which case desired_current_stock/stock_adjustment_reason take
        # its place in the fieldset below instead).
        base = ["created_at_jalali", "updated_at_jalali"]
        if not self._can_adjust_stock(request):
            base = ["current_stock_display"] + base
        if self._has_confirmed_purchase(obj):
            # purchase_price is auto-managed by PriceService — prevent POST override
            # and show it via the clean-formatted display method.
            base = ["purchase_price", "purchase_price_display"] + base
        return tuple(base)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            # Add form: show initial_stock input; no timestamps (nothing to display yet).
            return (
                ("اطلاعات اصلی", {
                    "fields": ("name", "internal_code", "product_type", "unit"),
                }),
                ("قیمت و موجودی", {
                    "description": (
                        "قیمت و موجودی اولیه را وارد کنید. "
                        "پس از اولین خرید تأییدشده، قیمت خودکار به‌روز می‌شود."
                    ),
                    "fields": ("purchase_price", "initial_stock", "minimum_stock"),
                }),
                ("توضیحات داخلی", {
                    "fields": ("internal_notes",),
                }),
            )

        # Edit form: current_stock is read-only via display method, unless
        # the requesting user may adjust it — then the editable pair
        # replaces it in the same fieldset (same position, same section).
        price_field = (
            "purchase_price_display"
            if self._has_confirmed_purchase(obj)
            else "purchase_price"
        )
        stock_fields = (
            ("desired_current_stock", "stock_adjustment_reason")
            if self._can_adjust_stock(request)
            else ("current_stock_display",)
        )
        return (
            ("اطلاعات اصلی", {
                "fields": ("name", "internal_code", "product_type", "unit"),
            }),
            ("قیمت و موجودی", {
                "fields": (price_field, "minimum_stock") + stock_fields,
            }),
            ("توضیحات داخلی", {
                "fields": ("internal_notes",),
            }),
            ("زمان‌بندی", {
                "fields": ("created_at_jalali", "updated_at_jalali"),
                "classes": ("collapse",),
            }),
        )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if field and db_field.name == "purchase_price":
            field.label    = "قیمت خرید اولیه (تومان)"
            field.help_text = "پس از اولین خرید تأییدشده، قیمت خودکار به‌روز می‌شود."
            field.widget = MoneyInput()
        return field

    def get_form(self, request, obj=None, **kwargs):
        """Finish what get_fieldsets() started for desired_current_stock/
        stock_adjustment_reason: excluding a field from a fieldset only
        stops Django's *template* from rendering it — ModelFormMetaclass
        always re-merges explicitly declared form fields back onto every
        generated form class regardless of Meta.fields (see
        ProductAdminForm.desired_current_stock's comment). So the field
        must be removed here, on the form class itself, whenever it
        shouldn't apply — otherwise a required=True version would fail
        validation invisibly (rendered nowhere, so no field-level error is
        ever shown) on the add form, and an unauthorized user's forged POST
        value for it would still be read into cleaned_data.
        """
        form_class = super().get_form(request, obj, **kwargs)
        if obj is not None and self._can_adjust_stock(request):
            form_class.base_fields["desired_current_stock"].required = True
        else:
            form_class.base_fields.pop("desired_current_stock", None)
            form_class.base_fields.pop("stock_adjustment_reason", None)
        return form_class

    def save_model(self, request, obj, form, change):
        from django.db import transaction

        from inventory.services import StockService

        # Product metadata save + stock adjustment either both succeed or
        # both roll back — StockService.adjust_to_quantity() re-reads the
        # authoritative stock under its own row lock, so a concurrent
        # Purchase/Surgery consumption between page load and this save is
        # never lost or overwritten.
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if not change:
                initial_stock = form.cleaned_data.get("initial_stock")
                if initial_stock and initial_stock > 0:
                    StockService.create_movement(
                        product=obj,
                        quantity=initial_stock,
                        movement_type=MovementType.IN,
                        source_type=SourceType.MANUAL_ADJUSTMENT,
                        reference_id=f"initial-stock-{obj.pk}",
                        description="موجودی اولیه",
                    )
            elif "desired_current_stock" in form.cleaned_data and self._can_adjust_stock(request):
                desired = form.cleaned_data.get("desired_current_stock")
                reason  = form.cleaned_data.get("stock_adjustment_reason") or ""
                if desired is not None:
                    StockService.adjust_to_quantity(
                        product=obj,
                        desired_quantity=desired,
                        reason=reason,
                        user=request.user,
                    )

    def get_urls(self):
        from django.urls import path

        from inventory.admin_views import product_purge_view

        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:product_id>/detail/",
                self.admin_site.admin_view(product_detail_view),
                name="inventory_product_detail",
            ),
            path(
                "<int:product_id>/purge/",
                self.admin_site.admin_view(product_purge_view),
                name="inventory_product_purge",
            ),
        ]
        return custom_urls + urls

    def has_delete_permission(self, request, obj=None):
        """Only the main administrator may permanently purge a Product.

        Ordinary staff (even with a raw 'delete_product' permission) never
        see the delete action — deactivation (is_active=False) is the safe
        path for everyone else. See ProductPurgeService for why a plain
        delete can never work here (multiple PROTECT relations).
        """
        from accounts.permissions import is_main_administrator
        return is_main_administrator(request.user)

    def delete_view(self, request, object_id, extra_context=None):
        """Redirect to the custom purge preview/confirm page instead of
        Django's default delete_view — which would 500/error out on the
        PROTECT relations (StockMovement, PurchaseItem, SurgeryUsedItem,
        SurgeryConsumptionItem) before any confirmation is even shown.
        Handles both the changelist row action and the change-form
        'Delete' button, since both link to this same admin URL.
        """
        from django.shortcuts import redirect
        return redirect('admin:inventory_product_purge', product_id=object_id)

    # ── Readonly display methods ──────────────────────────────────────────────

    @admin.display(description="قیمت خرید | خودکار از آخرین خرید تأیید‌شده")
    def purchase_price_display(self, obj):
        """Clean-formatted read-only label — managed by PriceService."""
        if not obj.pk or not obj.purchase_price:
            return "—"
        return f"{clean_decimal_display(obj.purchase_price)} تومان"

    @admin.display(description="موجودی فعلی")
    def current_stock_display(self, obj):
        """Read-only stock value without trailing decimal zeros."""
        if not obj.pk:
            return "0"
        return clean_decimal_display(obj.current_stock) or "0"

    @admin.display(boolean=True, description="کمبود موجودی")
    def is_low_stock(self, obj):
        return obj.is_low_stock


# ---------------------------------------------------------------------------
# Product detail standalone view (registered via ProductAdmin.get_urls)
# No @admin.site.admin_view here — it is already wrapped in get_urls.
# ---------------------------------------------------------------------------

def product_detail_view(request, product_id):
    from django.shortcuts import get_object_or_404, render

    from accounts.permissions import is_main_administrator

    product = get_object_or_404(Product, pk=product_id)
    pa = ProductAdmin(Product, admin.site)
    context = {
        **admin.site.each_context(request),
        "original":              product,
        "has_change_permission": pa.has_change_permission(request, product),
        "has_delete_permission": pa.has_delete_permission(request, product),
        "has_add_permission":    pa.has_add_permission(request),
        "is_main_administrator": is_main_administrator(request.user),
        "opts":                  Product._meta,
        "app_label":             Product._meta.app_label,
    }
    return render(request, "admin/inventory/product/change_form.html", context)


# ---------------------------------------------------------------------------
# ProductVendor inline — embedded inside ProductAdmin
# ---------------------------------------------------------------------------

class ProductVendorInline(JalaliAdminDatesMixin, admin.StackedInline):
    """Show/edit all vendor links directly from the Product change page.

    Rendered collapsed-by-default (one summary line per relation) by
    product_vendor_inline.js — the DOM/fields below are untouched (still a
    normal Django StackedInline formset with real TOTAL_FORMS/INITIAL_FORMS
    management data), the JS only toggles a CSS class that hides/shows the
    existing fieldset, so add/edit/delete/validation all keep working
    exactly as Django already handles them.
    """

    model               = ProductVendor
    fk_name             = "product"
    extra               = 0
    form                = ProductVendorInlineForm   # currency select + clean price
    autocomplete_fields = ("vendor",)
    readonly_fields     = ("created_at_jalali", "updated_at_jalali")
    formfield_overrides = JALALI_FORMFIELD_OVERRIDES   # last_price_date → Jalali
    fields              = (
        "vendor", "is_primary", "is_active",
        "supplier_product_name", "supplier_product_code",
        "unit_price", "currency", "last_price_date",
        "minimum_order_quantity", "lead_time_days",
        "notes", "created_at_jalali", "updated_at_jalali",
    )
    verbose_name        = "فروشنده"
    verbose_name_plural = "فروشندگان محصول"

    class Media:
        css = {"all": ("admin/css/product_vendor_inline.css",)}
        js  = ("admin/js/product_vendor_inline.js",)


# Attach inline to the existing ProductAdmin
ProductAdmin.inlines = [ProductVendorInline]


# ---------------------------------------------------------------------------
# ProductVendor inline — embedded inside VendorAdmin (reverse direction)
# ---------------------------------------------------------------------------

class VendorProductInline(JalaliAdminDatesMixin, admin.TabularInline):
    """Show/edit product links directly from the Vendor change page."""

    model               = ProductVendor
    fk_name             = "vendor"
    extra               = 0
    autocomplete_fields = ("product",)
    readonly_fields     = ("created_at_jalali", "updated_at_jalali")
    formfield_overrides = {**JALALI_FORMFIELD_OVERRIDES, **MONEY_FORMFIELD_OVERRIDES}
    fields              = (
        "product", "is_primary", "is_active",
        "supplier_product_name", "supplier_product_code",
        "unit_price", "currency", "last_price_date",
        "minimum_order_quantity", "lead_time_days",
        "notes", "created_at_jalali", "updated_at_jalali",
    )
    verbose_name        = "محصول"
    verbose_name_plural = "محصولات این فروشنده"


# ---------------------------------------------------------------------------
# ProductVendor standalone admin
# ---------------------------------------------------------------------------

@admin.register(ProductVendor)
class ProductVendorAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = (
        "product", "vendor", "supplier_product_code",
        "get_unit_price_display", "currency", "minimum_order_quantity",
        "lead_time_days", "is_primary", "is_active", "last_price_date_jalali",
    )
    list_filter     = ("is_active", "is_primary", "currency")
    search_fields   = (
        "product__name", "product__internal_code",
        "vendor__name",
        "supplier_product_name", "supplier_product_code",
    )
    ordering        = ("vendor__name", "product__name")
    readonly_fields = ("created_at_jalali", "updated_at_jalali")
    autocomplete_fields = ("product", "vendor")
    formfield_overrides = {**JALALI_FORMFIELD_OVERRIDES, **MONEY_FORMFIELD_OVERRIDES}

    @admin.display(description="قیمت واحد", ordering="unit_price")
    def get_unit_price_display(self, obj):
        return clean_decimal_display(obj.unit_price)

    fieldsets = (
        ("ارتباط", {
            "fields": ("product", "vendor", "is_primary", "is_active"),
        }),
        ("شناسه نزد فروشنده", {
            "fields": ("supplier_product_name", "supplier_product_code"),
        }),
        ("قیمت‌گذاری", {
            "fields": ("unit_price", "currency", "last_price_date"),
        }),
        ("سفارش‌دهی", {
            "fields": ("minimum_order_quantity", "lead_time_days"),
        }),
        ("یادداشت", {
            "fields": ("notes",),
        }),
        ("زمان‌بندی", {
            "fields": ("created_at_jalali", "updated_at_jalali"),
        }),
    )


# ---------------------------------------------------------------------------
# Vendor admin
# ---------------------------------------------------------------------------


class VendorPhoneFormSet(BaseInlineFormSet):
    """Inline formset for VendorPhone; validates for duplicate phone numbers."""

    def clean(self):
        if any(self.errors):
            return
        phones_seen = []
        for form in self.forms:
            if self._should_delete_form(form):
                continue
            phone = (form.cleaned_data.get("phone") or "").strip()
            if not phone:
                continue
            if phone in phones_seen:
                raise forms.ValidationError(
                    "این شماره تلفن قبلاً برای این تامین‌کننده ثبت شده است."
                )
            phones_seen.append(phone)
        # Check against primary phone on existing vendors (edit mode)
        if self.instance and self.instance.pk:
            primary = (self.instance.phone_number or "").strip()
            if primary and primary in phones_seen:
                raise forms.ValidationError(
                    "این شماره قبلاً به عنوان شماره تلفن اصلی ثبت شده است."
                )


class VendorPhoneInline(admin.TabularInline):
    model = VendorPhone
    formset = VendorPhoneFormSet
    extra = 0
    fields = ("phone",)
    verbose_name = "شماره تلفن دیگر"
    verbose_name_plural = "شماره‌های تلفن دیگر"
    can_delete = True


@admin.register(Vendor)
class VendorAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    change_list_template = "admin/inventory/vendor/change_list.html"
    change_form_template = "admin/inventory/vendor/change_form.html"
    formfield_overrides  = {**JALALI_FORMFIELD_OVERRIDES, **DECIMAL_FORMFIELD_OVERRIDES}

    list_display    = (
        "name", "phone_display", "email",
        "current_balance", "is_active", "created_at_jalali",
    )
    list_filter     = ("is_active",)
    search_fields   = ("name", "phone_number", "email", "tax_id", "additional_phones__phone")
    readonly_fields = ("created_at_jalali", "updated_at_jalali")
    ordering        = ("name",)
    inlines         = [VendorPhoneInline]

    fieldsets = (
        ("اطلاعات اصلی", {
            "fields": ("name", "phone_number", "email", "address", "notes", "is_active"),
        }),
        ("اطلاعات مالی", {
            "fields": ("opening_balance", "current_balance", "tax_id", "bank_account"),
        }),
        ("زمان‌بندی", {
            "fields": ("created_at_jalali", "updated_at_jalali"),
        }),
    )

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:vendor_id>/detail/",
                self.admin_site.admin_view(vendor_detail_view),
                name="inventory_vendor_detail",
            ),
        ]
        return custom_urls + urls

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(extra_phone_count=Count("additional_phones", distinct=True))
            .distinct()
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            try:
                from inventory.services import VendorService
                extra_context["purchased_products"] = list(
                    VendorService.get_vendor_purchased_products(int(object_id))
                )
                extra_context["can_add_purchase"] = request.user.has_perm(
                    "inventory.add_purchase"
                )
            except (ValueError, TypeError):
                extra_context["purchased_products"] = []
                extra_context["can_add_purchase"] = False
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    @admin.display(description="شماره تلفن")
    def phone_display(self, obj):
        phone = obj.phone_number or "—"
        count = getattr(obj, "extra_phone_count", 0)
        if count:
            return format_html(
                '{} <span style="font-size:11px;color:var(--muted,#888)">+{} شماره دیگر</span>',
                phone,
                count,
            )
        return phone


# ---------------------------------------------------------------------------
# Vendor detail standalone view (registered via VendorAdmin.get_urls)
# ---------------------------------------------------------------------------

def vendor_detail_view(request, vendor_id):
    from django.shortcuts import get_object_or_404, render
    from inventory.services import VendorService
    vendor = get_object_or_404(Vendor, pk=vendor_id)
    va = VendorAdmin(Vendor, admin.site)
    product_links = (
        ProductVendor.objects
        .filter(vendor=vendor)
        .select_related("product")
        .order_by("product__name")
    )
    purchased_products = list(VendorService.get_vendor_purchased_products(vendor.pk))
    can_add_purchase = request.user.has_perm("inventory.add_purchase")
    context = {
        **admin.site.each_context(request),
        "original":              vendor,
        "has_change_permission": va.has_change_permission(request, vendor),
        "has_delete_permission": va.has_delete_permission(request, vendor),
        "opts":                  Vendor._meta,
        "app_label":             Vendor._meta.app_label,
        "additional_phones":     list(vendor.additional_phones.all()),
        "product_links":         list(product_links),
        "purchased_products":    purchased_products,
        "can_add_purchase":      can_add_purchase,
    }
    return render(request, "admin/inventory/vendor/detail.html", context)


# ---------------------------------------------------------------------------
# StockMovement inline — embedded inside ProductAdmin
# ---------------------------------------------------------------------------

class StockMovementInline(JalaliAdminDatesMixin, admin.TabularInline):
    """Read-only stock-movement history inside the Product change page.

    Rendering note: the table markup itself is Django's normal
    TabularInline output (kept as-is — it already produces valid
    <table>/<thead>/<tbody>/<tr>/<td> structure and Django's own
    management-form handling, so touching the template would be a needless
    risk). The visual bug this project hit was a *CSS* bug, not a markup
    bug: the shared rule `#content-main .form-row { display:flex }`
    (rtl_responsive.css) was written for StackedInline's `<div
    class="form-row">` field wrappers, but Django's tabular.html also puts
    `class="form-row"` on each `<tr>` — turning every row into a flex
    container that wraps its <td>s onto separate lines instead of table
    columns. Fixed at the source (rtl_responsive.css) rather than here.
    product_movement_table.js only wraps the already-correct table in a
    `.product-movement-table-scroll` div and adds an empty-state row when
    there are zero movements — it does not alter any field/input.
    """

    model           = StockMovement
    fk_name         = "product"
    extra           = 0
    can_delete      = False
    readonly_fields = (
        "movement_type", "source_type", "quantity_display", "unit",
        "reference_display", "movement_date_jalali", "description", "created_at_jalali",
    )
    fields          = readonly_fields
    ordering        = ("-movement_date",)
    verbose_name        = "حرکت موجودی"
    verbose_name_plural = "تاریخچه حرکات موجودی"

    class Media:
        css = {"all": ("admin/css/product_movement_table.css",)}
        js  = ("admin/js/product_movement_table.js",)

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="مقدار")
    def quantity_display(self, obj):
        return clean_decimal_display(obj.quantity)

    @admin.display(description="شناسه مرجع")
    def reference_display(self, obj):
        """Link reference_id to its source Purchase/Surgery record when it
        still exists; otherwise show the raw text (never a broken link).

        reference_id is always written by a canonical service
        (StockService/Purchase.confirm/Purchase.cancel/
        SurgeryInventoryService) using one of a few fixed prefixes — this
        is stable pattern matching against a known format, not fuzzy text
        matching against a description.
        """
        import re as _re

        from django.urls import reverse

        ref = (obj.reference_id or "").strip()
        if not ref:
            return "—"

        m = _re.match(r"^(?:cancel-)?purchase-(\d+)$", ref)
        if m:
            pk = int(m.group(1))
            if Purchase.objects.filter(pk=pk).exists():
                url = reverse("admin:inventory_purchase_change", args=[pk])
                return format_html('<a href="{}">{}</a>', url, ref)
            return ref

        m = _re.match(r"^surgery-history-(\d+)$", ref)
        if m:
            from surgeries.models import SurgeryHistory
            pk = int(m.group(1))
            if SurgeryHistory.objects.filter(pk=pk).exists():
                url = reverse("admin:surgeries_surgeryhistory_detail", args=[pk])
                return format_html('<a href="{}">{}</a>', url, ref)
            return ref

        m = _re.match(r"^surgery-(\d+)$", ref)
        if m:
            from surgeries.models import Surgery
            pk = int(m.group(1))
            if Surgery.objects.filter(pk=pk).exists():
                url = reverse("admin:surgeries_surgery_change", args=[pk])
                return format_html('<a href="{}">{}</a>', url, ref)
            return ref

        return ref


# Attach StockMovement history inline to ProductAdmin (keep ProductVendorInline first)
ProductAdmin.inlines = [ProductVendorInline, StockMovementInline]


# ---------------------------------------------------------------------------
# StockMovement standalone admin
# ---------------------------------------------------------------------------

@admin.register(StockMovement)
class StockMovementAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    list_display    = (
        "product", "movement_type", "source_type",
        "get_quantity_display", "unit", "reference_id",
        "movement_date_jalali", "created_at_jalali",
    )
    list_filter     = ("movement_type", "source_type")
    search_fields   = (
        "product__name", "product__internal_code",
        "description", "reference_id",
    )
    date_hierarchy  = "movement_date"
    ordering        = ("-movement_date", "-created_at")
    # movement_date defaults to timezone.now, so showing it read-only (Jalali)
    # doesn't block the (rare) admin add — the default fills it in.
    readonly_fields = ("movement_date_jalali", "created_at_jalali", "updated_at_jalali")

    fieldsets = (
        ("محصول و مقدار", {
            "fields": ("product", "quantity", "unit"),
        }),
        ("نوع و منبع حرکت", {
            "fields": ("movement_type", "source_type", "reference_id"),
        }),
        ("زمان‌بندی رویداد", {
            "fields": ("movement_date_jalali",),
        }),
        ("توضیحات", {
            "fields": ("description",),
        }),
        ("زمان ثبت", {
            "fields": ("created_at_jalali", "updated_at_jalali"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="مقدار", ordering="quantity")
    def get_quantity_display(self, obj):
        return clean_decimal_display(obj.quantity)

    def has_change_permission(self, request, obj=None):
        """Stock movements are append-only — forbid editing in admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Never delete stock history through admin."""
        return False


# ---------------------------------------------------------------------------
# Purchase admin
# ---------------------------------------------------------------------------

class PurchaseItemInline(JalaliAdminDatesMixin, admin.TabularInline):
    """Manage purchase line items directly from the Purchase change page.

    Items are editable in all purchase statuses (PENDING / CONFIRMED / CANCELLED).
    For CONFIRMED purchases, PurchaseAdmin.save_related() automatically creates
    delta StockMovements so inventory stays in sync with every edit.
    """

    model               = PurchaseItem
    fk_name             = "purchase"
    extra               = 0
    formfield_overrides = DECIMAL_FORMFIELD_OVERRIDES
    readonly_fields     = ("unit", "created_at_jalali", "updated_at_jalali")
    fields          = (
        "product", "quantity", "unit", "unit_price", "manual_total", "notes",
        "created_at_jalali", "updated_at_jalali",
    )
    verbose_name        = "قلم خرید"
    verbose_name_plural = "اقلام خرید"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield and db_field.name in ('unit_price', 'manual_total'):
            formfield.widget = MoneyInput()
        return formfield


@admin.register(Purchase)
class PurchaseAdmin(JalaliAdminDatesMixin, admin.ModelAdmin):
    change_list_template = "admin/inventory/purchase/change_list.html"
    change_form_template = "admin/inventory/purchase/change_form.html"

    list_display    = (
        "pk", "vendor", "reference_number",
        "purchase_date", "status", "stock_applied", "created_at",
    )
    list_filter     = ("status", "stock_applied", "vendor")
    search_fields   = ("reference_number", "vendor__name", "notes")
    ordering        = ("-purchase_date", "-created_at")
    readonly_fields = ("stock_applied", "created_at_jalali", "updated_at_jalali")
    date_hierarchy  = "purchase_date"
    inlines         = [PurchaseItemInline]
    # CLI-70: edit the Gregorian purchase_date through a Jalali text input.
    formfield_overrides = JALALI_FORMFIELD_OVERRIDES

    fieldsets = (
        ("اطلاعات خرید", {
            "fields": (
                "vendor", "reference_number",
                "purchase_date", "status", "notes",
            ),
        }),
        ("وضعیت موجودی", {
            "fields": ("stock_applied",),
            "description": (
                "پس از تأیید خرید، حرکات موجودی IN برای هر قلم ایجاد می‌شوند."
            ),
        }),
        ("زمان‌بندی", {
            "fields": ("created_at_jalali", "updated_at_jalali"),
            "classes": ("collapse",),
        }),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "purchase_date":
            return JalaliFormDateForDateTimeField(
                label="تاریخ خرید",
                required=True,
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_related(self, request, form, formsets, change):
        """Save inline items, sync stock for confirmed purchases, and recalculate prices.

        For CONFIRMED purchases (stock_applied=True), a snapshot of items is taken
        BEFORE super() saves the formset so that delta StockMovements can be created
        for any quantity, product, addition, or deletion changes.  Finance is kept in
        sync automatically by the on_purchase_item_saved / on_purchase_item_deleted
        signals defined in inventory/signals.py.

        Price recalculation runs AFTER super() so the correct final item state is used.
        Capturing old_product_ids before super() ensures that products removed or
        replaced by a product FK change are also recalculated.
        """
        from django.db import transaction as db_transaction

        purchase = form.instance

        # Snapshot confirmed-purchase items BEFORE the formset saves so we can
        # compute the delta and emit adjustment StockMovements afterward.
        needs_stock_sync = (
            change
            and purchase.status == PurchaseStatus.CONFIRMED
            and purchase.stock_applied
        )
        old_items_snapshot = {}
        if needs_stock_sync:
            old_items_snapshot = {
                item.pk: {
                    "product_id": item.product_id,
                    "quantity":   item.quantity,
                }
                for item in purchase.items.all()
            }

        # Capture product_ids BEFORE super() so that a product FK change
        # also recalculates the OLD product's price.
        old_product_ids = (
            set(purchase.items.values_list("product_id", flat=True))
            if change else set()
        )

        super().save_related(request, form, formsets, change)

        # Stock sync for CONFIRMED purchase edits — atomic savepoint so that a
        # movement failure rolls back only the stock changes, not the item saves.
        if needs_stock_sync:
            try:
                with db_transaction.atomic():
                    self._sync_purchase_stock_edit(purchase, old_items_snapshot)
            except Exception as exc:
                from django.contrib import messages as dj_msgs
                from django.core.exceptions import ValidationError as VE
                err = (
                    "; ".join(exc.messages)
                    if isinstance(exc, VE) and hasattr(exc, "messages")
                    else str(exc)
                )
                dj_msgs.error(
                    request,
                    "تغییرات ذخیره شد، اما به‌روزرسانی موجودی ناموفق بود: " + err,
                )

        from inventory.services import PriceService

        # Establish vendor↔product links (any status).
        PriceService.ensure_vendor_product_link(purchase)

        # Recalculate prices for every affected product.
        new_product_ids = set(purchase.items.values_list("product_id", flat=True))
        for product_id in (old_product_ids | new_product_ids):
            PriceService.recalculate_product_price(product_id)

    def _sync_purchase_stock_edit(self, purchase, old_items_snapshot):
        """Create delta StockMovements when a confirmed Purchase's items change.

        Compares old_items_snapshot (captured before formset save) with the current
        DB state and emits IN/OUT movements for each difference.  Finance sync is
        handled by the on_purchase_item_saved / on_purchase_item_deleted signals.
        """
        from inventory.services import StockService

        new_items = {
            item.pk: {"product_id": item.product_id, "quantity": item.quantity}
            for item in purchase.items.all()
        }

        ref    = f"edit-purchase-{purchase.pk}"
        label  = purchase.reference_number or f"#{purchase.pk}"
        vendor = purchase.vendor.name
        base   = f"ویرایش خرید {label} — {vendor}"

        # Deletions and modifications
        for pk, old in old_items_snapshot.items():
            if pk not in new_items:
                # Item removed → reverse its stock contribution
                StockService.create_movement(
                    product=old["product_id"],
                    quantity=old["quantity"],
                    movement_type=MovementType.OUT,
                    source_type=SourceType.PURCHASE,
                    reference_id=ref,
                    description=f"{base} — برگشت قلم حذف‌شده",
                    movement_date=purchase.purchase_date,
                )
            else:
                new = new_items[pk]
                if new["product_id"] != old["product_id"]:
                    # Product replaced → reverse old, apply new
                    StockService.create_movement(
                        product=old["product_id"],
                        quantity=old["quantity"],
                        movement_type=MovementType.OUT,
                        source_type=SourceType.PURCHASE,
                        reference_id=ref,
                        description=f"{base} — تغییر محصول (برگشت قدیم)",
                        movement_date=purchase.purchase_date,
                    )
                    StockService.create_movement(
                        product=new["product_id"],
                        quantity=new["quantity"],
                        movement_type=MovementType.IN,
                        source_type=SourceType.PURCHASE,
                        reference_id=ref,
                        description=f"{base} — تغییر محصول (اضافه جدید)",
                        movement_date=purchase.purchase_date,
                    )
                else:
                    # Same product — emit delta movement if quantity changed
                    delta = new["quantity"] - old["quantity"]
                    if delta > 0:
                        StockService.create_movement(
                            product=new["product_id"],
                            quantity=delta,
                            movement_type=MovementType.IN,
                            source_type=SourceType.PURCHASE,
                            reference_id=ref,
                            description=f"{base} — افزایش مقدار",
                            movement_date=purchase.purchase_date,
                        )
                    elif delta < 0:
                        StockService.create_movement(
                            product=new["product_id"],
                            quantity=-delta,
                            movement_type=MovementType.OUT,
                            source_type=SourceType.PURCHASE,
                            reference_id=ref,
                            description=f"{base} — کاهش مقدار",
                            movement_date=purchase.purchase_date,
                        )

        # Additions — items not present in the old snapshot
        for pk, new in new_items.items():
            if pk not in old_items_snapshot:
                StockService.create_movement(
                    product=new["product_id"],
                    quantity=new["quantity"],
                    movement_type=MovementType.IN,
                    source_type=SourceType.PURCHASE,
                    reference_id=ref,
                    description=f"{base} — افزودن قلم جدید",
                    movement_date=purchase.purchase_date,
                )

    def has_delete_permission(self, request, obj=None):
        """Block deletion of purchases that have affected inventory.

        A purchase is protected from deletion when:
          - stock_applied is True  — IN movements were created for it.
          - status is CONFIRMED    — belt-and-suspenders guard.

        Use the cancel action to reverse inventory effects before any cleanup.
        """
        if obj is not None and (obj.stock_applied or obj.status == PurchaseStatus.CONFIRMED):
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        """Status is always read-only for existing purchases.

        Status transitions are managed exclusively through the confirm/cancel
        workflow actions, never through a raw dropdown in the form.
        """
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None and "status" not in fields:
            fields.append("status")
        return tuple(fields)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            try:
                purchase = self.get_object(request, object_id)
                if purchase is not None:
                    extra_context["show_confirm_btn"] = (
                        purchase.status == PurchaseStatus.PENDING
                    )
                    extra_context["show_cancel_btn"] = purchase.status in (
                        PurchaseStatus.PENDING,
                        PurchaseStatus.CONFIRMED,
                    )
                    extra_context["show_restore_btn"] = (
                        purchase.status == PurchaseStatus.CANCELLED
                    )
                    extra_context["purchase_was_confirmed"] = purchase.stock_applied
            except Exception:
                pass
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def response_change(self, request, obj):
        from django.contrib import messages as django_messages
        from django.core.exceptions import ValidationError
        from django.http import HttpResponseRedirect

        action = request.POST.get("_action")

        if action == "confirm":
            try:
                obj.refresh_from_db()
                obj.confirm()
                self.message_user(
                    request,
                    "خرید با موفقیت تأیید شد و موجودی و اطلاعات مالی به‌روزرسانی شدند.",
                    django_messages.SUCCESS,
                )
            except ValidationError as exc:
                err = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
                self.message_user(request, err, django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        if action == "cancel":
            try:
                obj.refresh_from_db()
                obj.cancel()
                self.message_user(
                    request,
                    "خرید با موفقیت لغو شد.",
                    django_messages.SUCCESS,
                )
            except ValidationError as exc:
                err = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
                self.message_user(request, err, django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        if action == "restore":
            try:
                obj.refresh_from_db()
                if obj.status != PurchaseStatus.CANCELLED:
                    self.message_user(
                        request,
                        "فقط خریدهای لغو شده را می‌توان بازگرداند.",
                        django_messages.WARNING,
                    )
                else:
                    obj.status = PurchaseStatus.PENDING
                    obj.stock_applied = False
                    obj.save(update_fields=["status", "stock_applied", "updated_at"])
                    self.message_user(
                        request,
                        "خرید به وضعیت «در انتظار تأیید» بازگردانده شد.",
                        django_messages.SUCCESS,
                    )
            except Exception as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)
