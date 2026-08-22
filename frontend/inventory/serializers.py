from rest_framework import serializers

from inventory.models import (
    Product,
    ProductCategory,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    StockMovement,
    Vendor,
    VendorPhone,
)


# ---------------------------------------------------------------------------
# ProductCategory serializers
# ---------------------------------------------------------------------------

class ProductCategorySerializer(serializers.ModelSerializer):
    """Flat serializer — suitable for dropdowns and list endpoints."""

    full_path = serializers.CharField(read_only=True)

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "full_path", "parent", "is_active"]


class ProductCategoryTreeSerializer(serializers.ModelSerializer):
    """Nested recursive serializer — suitable for tree-display endpoints."""

    children = serializers.SerializerMethodField()
    depth    = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "description", "is_active", "depth", "children"]

    def get_children(self, obj) -> list:
        qs = obj.get_children().filter(is_active=True)
        return ProductCategoryTreeSerializer(qs, many=True).data

    def get_depth(self, obj) -> int:
        depth = 0
        node = obj
        visited = set()
        while node.parent_id is not None:
            if node.pk in visited:
                break
            visited.add(node.pk)
            depth += 1
            node = node.parent
        return depth


# ---------------------------------------------------------------------------
# Product serializers
# ---------------------------------------------------------------------------

class ProductSerializer(serializers.ModelSerializer):
    """Full serializer — for detail / form views.

    current_stock, is_low_stock, is_out_of_stock are read-only at the
    serializer level. Even if a payload includes current_stock the value
    is silently discarded before reaching the model.
    """

    current_stock    = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    is_low_stock     = serializers.BooleanField(read_only=True)
    is_out_of_stock  = serializers.BooleanField(read_only=True)
    category_detail  = serializers.SerializerMethodField()

    product_type_display = serializers.CharField(source="get_product_type_display", read_only=True)
    stock_status         = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "internal_code", "product_type", "product_type_display",
            "category", "category_detail",
            "unit", "purchase_price", "sale_price", "barcode",
            "current_stock",
            "minimum_stock", "internal_notes", "is_active",
            "is_low_stock", "is_out_of_stock", "stock_status",
            "created_at", "updated_at",
        ]
        read_only_fields = ["current_stock", "created_at", "updated_at"]
        extra_kwargs = {
            "internal_code": {"validators": []},
            "unit": {"required": False, "allow_blank": True, "default": ""},
            "sale_price": {"required": False},
            "barcode": {"required": False},
            "category": {"required": False, "allow_null": True},
            "is_active": {"required": False},
        }

    def get_stock_status(self, obj) -> str:
        if obj.is_out_of_stock:
            return "ناموجود"
        if obj.is_low_stock:
            return "کم‌موجودی"
        return "موجود"

    def get_category_detail(self, obj) -> dict | None:
        if obj.category_id is None:
            return None
        return ProductCategorySerializer(obj.category).data

    def validate_internal_code(self, value):
        qs = Product.objects.filter(internal_code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "محصولی با این کد داخلی قبلاً ثبت شده است."
            )
        return value

    def validate_purchase_price(self, value):
        if value < 0:
            raise serializers.ValidationError("قیمت خرید نمی‌تواند منفی باشد.")
        return value

    def validate_sale_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("قیمت فروش نمی‌تواند منفی باشد.")
        return value

    def validate_minimum_stock(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("حداقل موجودی نمی‌تواند منفی باشد.")
        return value


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for list views and dropdowns.

    Also backs the Surgery used-item modal's Product selector — category_name
    and barcode were added for that (both additive, read-only; existing
    consumers of this serializer are unaffected). ProductViewSet.get_queryset()
    include category__name and barcode in its .only() for list actions so
    these don't trigger a per-row deferred-field query.
    """

    current_stock       = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    is_low_stock        = serializers.BooleanField(read_only=True)
    is_out_of_stock     = serializers.BooleanField(read_only=True)
    product_type_display = serializers.CharField(source="get_product_type_display", read_only=True)
    stock_status        = serializers.SerializerMethodField()
    category_name        = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta:
        model = Product
        fields = [
            "id", "name", "internal_code", "product_type", "product_type_display",
            "category", "category_name", "unit", "purchase_price", "sale_price",
            "current_stock", "minimum_stock", "barcode",
            "is_low_stock", "is_out_of_stock", "stock_status", "is_active",
        ]
        read_only_fields = ["current_stock"]

    def get_stock_status(self, obj) -> str:
        if obj.is_out_of_stock:
            return "ناموجود"
        if obj.is_low_stock:
            return "کم‌موجودی"
        return "موجود"


class ProductStockSerializer(serializers.ModelSerializer):
    """Read-only serializer for StockMovement (CLI-11) to reference products."""

    current_stock = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "internal_code", "current_stock", "unit"]
        read_only_fields = ["id", "name", "internal_code", "current_stock", "unit"]


# ---------------------------------------------------------------------------
# Inventory stock report serializers
# ---------------------------------------------------------------------------

class InventoryStockProductSerializer(serializers.ModelSerializer):
    """Per-product row in the inventory stock report."""

    current_stock   = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    is_low_stock    = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    inventory_value = serializers.SerializerMethodField()
    category_name   = serializers.CharField(source='category.name', default=None, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "internal_code", "product_type",
            "category", "category_name",
            "unit", "purchase_price",
            "current_stock", "minimum_stock",
            "is_low_stock", "is_out_of_stock",
            "inventory_value",
            "is_active",
        ]
        read_only_fields = fields

    def get_inventory_value(self, obj) -> str:
        from decimal import Decimal
        value = obj.current_stock * obj.purchase_price
        return str(value.quantize(Decimal('0.01')))


class InventoryStockReportSummarySerializer(serializers.Serializer):
    """Summary section of the inventory stock report."""

    total_products        = serializers.IntegerField()
    low_stock_count       = serializers.IntegerField()
    out_of_stock_count    = serializers.IntegerField()
    total_inventory_value = serializers.DecimalField(max_digits=20, decimal_places=2)


# ---------------------------------------------------------------------------
# Vendor serializers
# ---------------------------------------------------------------------------

class VendorPhoneSerializer(serializers.ModelSerializer):
    """Serializer for a single additional phone number."""

    class Meta:
        model  = VendorPhone
        fields = ["id", "phone", "order"]


class VendorListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for list views and dropdowns."""

    phones = serializers.SerializerMethodField()

    class Meta:
        model  = Vendor
        fields = [
            "id", "name", "phone_number", "email", "address", "notes", "phones",
        ]

    def get_phones(self, obj):
        phones = []
        if obj.phone_number:
            phones.append(obj.phone_number)
        for ap in obj.additional_phones.values_list("phone", flat=True):
            phones.append(ap)
        return phones


class VendorSerializer(serializers.ModelSerializer):
    """Full serializer — for detail / create / update views."""

    phones = serializers.SerializerMethodField()
    additional_phones = VendorPhoneSerializer(many=True, read_only=True)

    class Meta:
        model  = Vendor
        fields = [
            "id", "name", "phone_number", "email",
            "address", "notes", "is_active",
            "opening_balance", "current_balance",
            "tax_id", "bank_account",
            "created_at", "updated_at",
            "phones", "additional_phones",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_phones(self, obj):
        phones = []
        if obj.phone_number:
            phones.append(obj.phone_number)
        for ap in obj.additional_phones.values_list("phone", flat=True):
            phones.append(ap)
        return phones


# ---------------------------------------------------------------------------
# ProductVendor serializers
# ---------------------------------------------------------------------------

class ProductVendorListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for list views.

    Embeds minimal product/vendor names to avoid extra round-trips.

    Purchase statistics (total_purchased_quantity, latest_purchase_date) are
    populated from context['purchase_stats'] — a dict keyed by vendor_id that
    is computed once in the viewset's list() override, avoiding N+1 queries.
    """

    product_name             = serializers.CharField(source="product.name",          read_only=True)
    product_code             = serializers.CharField(source="product.internal_code",  read_only=True)
    vendor_name              = serializers.CharField(source="vendor.name",            read_only=True)
    vendor_url               = serializers.SerializerMethodField()
    vendor_detail_url        = serializers.SerializerMethodField()
    total_purchased_quantity = serializers.SerializerMethodField()
    latest_purchase_date     = serializers.SerializerMethodField()

    class Meta:
        model  = ProductVendor
        fields = [
            "id",
            "product", "product_name", "product_code",
            "vendor",  "vendor_name",  "vendor_url", "vendor_detail_url",
            "supplier_product_code", "unit_price", "currency",
            "is_primary", "is_active",
            "total_purchased_quantity", "latest_purchase_date",
        ]

    def get_vendor_url(self, obj) -> str:
        return f"/admin/inventory/vendor/{obj.vendor_id}/change/"

    def get_vendor_detail_url(self, obj) -> str:
        return f"/admin/inventory/vendor/{obj.vendor_id}/detail/"

    def get_total_purchased_quantity(self, obj) -> str:
        stats = self.context.get("purchase_stats", {})
        row   = stats.get(obj.vendor_id)
        if not row:
            return "0"
        qty = row.get("total_qty")
        if qty is None:
            return "0"
        from decimal import Decimal
        try:
            s = str(Decimal(str(qty)))
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            return s
        except Exception:
            return str(qty)

    def get_latest_purchase_date(self, obj):
        stats = self.context.get("purchase_stats", {})
        row   = stats.get(obj.vendor_id)
        if not row:
            return None
        dt = row.get("latest_date")
        if dt is None:
            return None
        try:
            from django.utils import timezone as tz
            if hasattr(dt, "date"):
                # Convert to local time so the displayed date matches the user's calendar.
                local_dt = tz.localtime(dt) if tz.is_aware(dt) else dt
                return local_dt.date().isoformat()
            return str(dt)[:10]
        except Exception:
            return None


class ProductVendorSerializer(serializers.ModelSerializer):
    """Full serializer — for detail / create / update views."""

    product_name = serializers.CharField(source="product.name",  read_only=True)
    vendor_name  = serializers.CharField(source="vendor.name",   read_only=True)

    class Meta:
        model  = ProductVendor
        fields = [
            "id",
            "product", "product_name",
            "vendor",  "vendor_name",
            "supplier_product_name", "supplier_product_code",
            "unit_price", "currency", "last_price_date",
            "minimum_order_quantity", "lead_time_days",
            "is_primary", "is_active",
            "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        """Prevent exact duplicate rows; allow same product+vendor with different conditions.

        The DB-level unique_product_vendor constraint on (product, vendor) was
        removed so vendors can supply the same product at different prices or with
        different ordering conditions.  We still block rows where ALL key business
        fields are identical to an existing row.
        """
        product  = attrs.get("product",  getattr(self.instance, "product",  None))
        vendor   = attrs.get("vendor",   getattr(self.instance, "vendor",   None))

        if not (product and vendor):
            return attrs

        # Build a filter for exact duplicates across the key business fields.
        unit_price = attrs.get("unit_price",
                               getattr(self.instance, "unit_price", None))
        moq = attrs.get("minimum_order_quantity",
                        getattr(self.instance, "minimum_order_quantity", None))
        supplier_code = attrs.get("supplier_product_code",
                                  getattr(self.instance, "supplier_product_code", ""))

        qs = ProductVendor.objects.filter(
            product=product,
            vendor=vendor,
            unit_price=unit_price,
            minimum_order_quantity=moq,
            supplier_product_code=supplier_code,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "این محصول با همین شرایط قبلاً برای این تامین‌کننده ثبت شده است."
                " برای شرایط متفاوت، قیمت یا حداقل سفارش را تغییر دهید."
            )
        return attrs


# ---------------------------------------------------------------------------
# VendorPurchasedProduct serializer
# ---------------------------------------------------------------------------

class VendorPurchasedProductSerializer(serializers.ModelSerializer):
    """Read-only. Products derived from CONFIRMED purchase history for one vendor.

    All aggregate fields (purchase_count, total_quantity, last_purchase_date,
    last_unit_price) must be pre-annotated by VendorService.get_vendor_purchased_products.
    """

    product_type_display = serializers.CharField(source="get_product_type_display", read_only=True)
    current_stock        = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    purchase_count       = serializers.IntegerField(read_only=True)
    total_quantity       = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, allow_null=True)
    last_purchase_date   = serializers.DateTimeField(read_only=True, allow_null=True)
    last_unit_price      = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, allow_null=True)
    product_detail_url   = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            "id", "internal_code", "name",
            "product_type", "product_type_display",
            "unit", "current_stock", "is_active",
            "purchase_count", "total_quantity",
            "last_purchase_date", "last_unit_price",
            "product_detail_url",
        ]
        read_only_fields = fields

    def get_product_detail_url(self, obj) -> str:
        return f"/admin/inventory/product/{obj.pk}/detail/"


# ---------------------------------------------------------------------------
# StockMovement serializers
# ---------------------------------------------------------------------------

class StockMovementListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for list views."""

    product_name          = serializers.CharField(source="product.name",         read_only=True)
    product_code          = serializers.CharField(source="product.internal_code", read_only=True)
    movement_type_display = serializers.CharField(source="get_movement_type_display", read_only=True)
    source_type_display   = serializers.CharField(source="get_source_type_display",   read_only=True)

    class Meta:
        model  = StockMovement
        fields = [
            "id",
            "product", "product_name", "product_code",
            "quantity", "unit",
            "movement_type", "movement_type_display",
            "source_type", "source_type_display",
            "movement_date", "created_at",
        ]


class StockMovementSerializer(serializers.ModelSerializer):
    """Full serializer — for create / retrieve views."""

    product_name          = serializers.CharField(source="product.name",         read_only=True)
    product_code          = serializers.CharField(source="product.internal_code", read_only=True)
    movement_type_display = serializers.CharField(source="get_movement_type_display", read_only=True)
    source_type_display   = serializers.CharField(source="get_source_type_display",   read_only=True)

    class Meta:
        model  = StockMovement
        fields = [
            "id",
            "product", "product_name", "product_code",
            "quantity", "unit",
            "movement_type", "movement_type_display",
            "source_type", "source_type_display",
            "reference_id", "movement_date",
            "description",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("مقدار باید بزرگ‌تر از صفر باشد.")
        return value


# ---------------------------------------------------------------------------
# Purchase serializers
# ---------------------------------------------------------------------------

class PurchaseItemSerializer(serializers.ModelSerializer):
    """Full serializer for purchase line items."""

    product_name = serializers.CharField(source="product.name",         read_only=True)
    product_code = serializers.CharField(source="product.internal_code", read_only=True)

    class Meta:
        model  = PurchaseItem
        fields = [
            "id",
            "purchase",
            "product", "product_name", "product_code",
            "quantity", "unit", "unit_price", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["unit", "created_at", "updated_at"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("مقدار باید بزرگ‌تر از صفر باشد.")
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("قیمت واحد نمی‌تواند منفی باشد.")
        return value

    def validate(self, attrs):
        """Prevent adding items to a confirmed or cancelled purchase."""
        purchase = attrs.get("purchase", getattr(self.instance, "purchase", None))
        if purchase and purchase.status != PurchaseStatus.PENDING:
            raise serializers.ValidationError(
                "اقلام خرید تأیید شده یا لغو شده را نمی‌توان تغییر داد."
            )
        return attrs


class PurchaseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — for list view."""

    vendor_name           = serializers.CharField(source="vendor.name",        read_only=True)
    status_display        = serializers.CharField(source="get_status_display", read_only=True)
    item_count            = serializers.IntegerField(source="items.count",      read_only=True)
    total_amount          = serializers.SerializerMethodField()
    average_unit_price    = serializers.SerializerMethodField()
    product_names_display = serializers.SerializerMethodField()

    class Meta:
        model  = Purchase
        fields = [
            "id", "vendor", "vendor_name",
            "reference_number", "purchase_date",
            "status", "status_display",
            "stock_applied", "item_count",
            "average_unit_price", "total_amount",
            "product_names_display",
            "created_at",
        ]

    def get_total_amount(self, obj):
        items = list(obj.items.all())
        total = sum((item.quantity * item.unit_price for item in items), 0)
        return str(total)

    def get_average_unit_price(self, obj):
        items = list(obj.items.all())
        if not items:
            return None
        total_qty    = sum(item.quantity    for item in items)
        total_amount = sum(item.quantity * item.unit_price for item in items)
        if not total_qty:
            return None
        from decimal import Decimal
        avg = Decimal(str(total_amount)) / Decimal(str(total_qty))
        return str(avg.quantize(Decimal('1')))

    def get_product_names_display(self, obj):
        """Human-readable product summary for the list table.

        1 item  → product name
        N items → first name + «+ N-1 قلم دیگر»
        0 items → «—»
        """
        items = list(obj.items.select_related('product').all())
        if not items:
            return '—'
        if len(items) == 1:
            return items[0].product.name
        return f'{items[0].product.name} + {len(items) - 1} قلم دیگر'


class PurchaseSerializer(serializers.ModelSerializer):
    """Full serializer — for create / retrieve / update views."""

    vendor_name    = serializers.CharField(source="vendor.name",        read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items          = PurchaseItemSerializer(many=True, read_only=True)

    class Meta:
        model  = Purchase
        fields = [
            "id", "vendor", "vendor_name",
            "reference_number", "purchase_date",
            "status", "status_display",
            "notes", "stock_applied",
            "items",
            "created_at", "updated_at",
        ]
        read_only_fields = ["status", "stock_applied", "created_at", "updated_at"]


class PurchasePriceHistorySerializer(serializers.ModelSerializer):
    """Read-only serializer for CLI-17 vendor price chart.

    Serializes a PurchaseItem with denormalized purchase-level fields so the
    chart can render per-vendor price lines without extra API calls.
    """

    purchase_date = serializers.DateTimeField(source="purchase.purchase_date", read_only=True)
    vendor        = serializers.IntegerField(source="purchase.vendor.pk",      read_only=True)
    vendor_name   = serializers.CharField(source="purchase.vendor.name",       read_only=True)

    class Meta:
        model  = PurchaseItem
        fields = ["purchase_date", "vendor", "vendor_name", "unit_price", "quantity"]


class VendorPriceHistorySerializer(serializers.ModelSerializer):
    """Read-only serializer for the per-product vendor price history endpoint.

    Returns one row per PurchaseItem (confirmed purchases only), including
    all fields required for price-chart rendering and tabular display.
    total_amount is computed as quantity * unit_price with safe Decimal arithmetic.
    currency is sourced from the ProductVendor through table when available,
    falling back to the plain string stored on the purchase item (none currently).
    """

    from decimal import Decimal as _Decimal

    product_id    = serializers.IntegerField(source="product.pk",           read_only=True)
    product_name  = serializers.CharField(source="product.name",            read_only=True)
    vendor_id     = serializers.IntegerField(source="purchase.vendor.pk",   read_only=True)
    vendor_name   = serializers.CharField(source="purchase.vendor.name",    read_only=True)
    purchase_id   = serializers.IntegerField(source="purchase.pk",          read_only=True)
    reference_id  = serializers.CharField(source="purchase.reference_number", read_only=True)
    purchase_date = serializers.DateTimeField(source="purchase.purchase_date",  read_only=True)
    total_amount  = serializers.SerializerMethodField()
    currency      = serializers.SerializerMethodField()

    class Meta:
        model  = PurchaseItem
        fields = [
            "id",
            "product_id", "product_name",
            "vendor_id",  "vendor_name",
            "purchase_id", "reference_id",
            "purchase_date",
            "unit_price", "quantity", "total_amount",
            "currency",
        ]

    def get_total_amount(self, obj) -> str:
        from decimal import Decimal
        qty   = Decimal(str(obj.quantity))
        price = Decimal(str(obj.unit_price))
        return str(qty * price)

    def get_currency(self, obj) -> str:
        """Return currency from ProductVendor link if it exists, else default IRR."""
        try:
            pv = ProductVendor.objects.filter(
                product_id=obj.product_id,
                vendor_id=obj.purchase.vendor_id,
            ).values_list("currency", flat=True).first()
            return pv if pv else "IRR"
        except Exception:
            return "IRR"


# ---------------------------------------------------------------------------
# Product Cost Report serializers
# ---------------------------------------------------------------------------

class ProductCostReportSummarySerializer(serializers.Serializer):
    """Read-only metadata block for the product cost report response."""

    start_date       = serializers.DateField(allow_null=True)
    end_date         = serializers.DateField(allow_null=True)
    product_type     = serializers.CharField()
    group_by         = serializers.CharField()
    vendor_id        = serializers.IntegerField(allow_null=True)
    total_cost       = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_quantity   = serializers.DecimalField(max_digits=14, decimal_places=3)
    total_line_items = serializers.IntegerField()


class ProductCostReportRowSerializer(serializers.Serializer):
    """One row in the product cost report results list.

    Fields present depend on group_by mode:
      product        → product_id/name/code/type; no vendor fields
      vendor         → vendor_id/name; no product fields
      product_vendor → all fields (most granular)
    """

    product_id    = serializers.IntegerField(allow_null=True, required=False)
    product_name  = serializers.CharField(allow_null=True,    required=False)
    product_code  = serializers.CharField(allow_null=True,    required=False)
    product_type  = serializers.CharField(allow_null=True,    required=False)
    vendor_id     = serializers.IntegerField(allow_null=True, required=False)
    vendor_name   = serializers.CharField(allow_null=True,    required=False)
    total_quantity  = serializers.DecimalField(max_digits=14, decimal_places=3)
    total_cost      = serializers.DecimalField(max_digits=20, decimal_places=2)
    avg_unit_price  = serializers.DecimalField(max_digits=14, decimal_places=2)
    purchase_count  = serializers.IntegerField()
