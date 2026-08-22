from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Avg, Count, DecimalField as DBDecimalField, ExpressionWrapper, F, FloatField, Max, Prefetch, Q, Sum
from django.db.models.functions import Length
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from common.pagination import StandardPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from accounts.permissions import IsAdminOrFinanceUser
from common.excel import (
    EXCEL_MAX_ROWS,
    ExcelColumn,
    ExcelExportMixin,
    ExcelSheet,
    build_excel,
    build_workbook,
    describe_ordering,
    excel_file_response,
    get_display_name,
)
from inventory.filters import ProductFilter, PurchaseFilter
from inventory.models import (
    Product,
    ProductCategory,
    ProductType,
    ProductVendor,
    Purchase,
    PurchaseItem,
    PurchaseStatus,
    StockMovement,
    Vendor,
)
from inventory.pagination import ProductListPagination, ProductPagination
from inventory.serializers import (
    InventoryStockProductSerializer,
    InventoryStockReportSummarySerializer,
    ProductCategorySerializer,
    ProductCategoryTreeSerializer,
    ProductCostReportRowSerializer,
    ProductCostReportSummarySerializer,
    ProductListSerializer,
    ProductSerializer,
    ProductStockSerializer,
    ProductVendorListSerializer,
    ProductVendorSerializer,
    PurchaseItemSerializer,
    PurchaseListSerializer,
    PurchasePriceHistorySerializer,
    PurchaseSerializer,
    StockMovementListSerializer,
    StockMovementSerializer,
    VendorListSerializer,
    VendorPurchasedProductSerializer,
    VendorSerializer,
    VendorPriceHistorySerializer,
)

# Actions that use the lightweight list serializer + only() queryset
_LIST_ACTIONS = frozenset({"list", "low_stock", "export_ids"})


# ---------------------------------------------------------------------------
# ProductCategory viewset
# ---------------------------------------------------------------------------

class ProductCategoryViewSet(ReadOnlyModelViewSet):
    """Read-only viewset for product categories.

    list     GET  /api/v1/inventory/categories/
    retrieve GET  /api/v1/inventory/categories/{id}/
    tree     GET  /api/v1/inventory/categories/tree/
    """

    permission_classes = [IsAuthenticated]
    serializer_class   = ProductCategorySerializer

    def get_queryset(self):
        qs = ProductCategory.objects.select_related("parent")

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")

        parent = self.request.query_params.get("parent")
        if parent is not None:
            if parent.lower() == "null":
                qs = qs.filter(parent__isnull=True)
            else:
                qs = qs.filter(parent_id=parent)

        return qs

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        data["children"] = ProductCategorySerializer(
            instance.get_children(), many=True
        ).data
        return Response(data)

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        roots = (
            ProductCategory.objects
            .filter(parent__isnull=True, is_active=True)
            .select_related("parent")
        )
        return Response(
            ProductCategoryTreeSerializer(roots, many=True).data,
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Product viewset
# ---------------------------------------------------------------------------

class ProductOrderingFilter(OrderingFilter):
    """OrderingFilter with NATURAL ordering for internal_code (CLI-68).

    Product.internal_code is a free-form CharField that, in real data, holds a
    mix of bare integers ('1', '2', '24') and prefixed codes ('DEMO-EQP-002').
    A plain text sort interleaves the bare integers lexically → 1, 2, 24, 25, 3
    (because the string "24" < "3").  Sorting by (LENGTH, value) restores
    natural numeric order for the bare-integer codes (1, 2, 3, 24, 25) while
    keeping the longer prefixed codes grouped together and stable.

    Only internal_code is rewritten; every other ordering field (name, price,
    stock, …) passes through unchanged.  LENGTH() works on both SQLite and
    PostgreSQL, so behaviour is identical in dev and production.
    """

    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if not ordering:
            return ordering
        expanded = []
        for term in ordering:
            if term == "internal_code":
                expanded += [Length("internal_code").asc(), "internal_code"]
            elif term == "-internal_code":
                expanded += [Length("internal_code").desc(), "-internal_code"]
            else:
                expanded.append(term)
        return expanded


class ProductViewSet(ExcelExportMixin, viewsets.ModelViewSet):
    """Production-grade product search, filter, and CRUD viewset.

    GET/POST  /api/v1/inventory/products/
    GET/PUT/PATCH/DELETE  /api/v1/inventory/products/{id}/
    GET  /api/v1/inventory/products/low_stock/
    GET  /api/v1/inventory/products/export_ids/

    Search (single ?search= param):
      name, internal_code, barcode, category__name
      (vendor name: stubbed — activate in CLI-13 when ProductVendor exists)

    Filters (via ProductFilter):
      product_type, category, category_tree, is_active (default True),
      low_stock, out_of_stock, price_min, price_max, has_barcode

    Ordering:
      name, internal_code, purchase_price, sale_price, current_stock,
      category__name, created_at  (default: internal_code ascending — CLI-68)
    """

    permission_classes = [IsAuthenticated]
    pagination_class   = ProductListPagination
    filterset_class    = ProductFilter
    filter_backends    = [
        __import__(
            "django_filters.rest_framework",
            fromlist=["DjangoFilterBackend"],
        ).DjangoFilterBackend,
        SearchFilter,
        ProductOrderingFilter,   # CLI-68: natural sort for internal_code
    ]
    search_fields  = [
        "name",
        "internal_code",
        "barcode",
        "category__name",
        "product_vendors__vendor__name",  # activated in CLI-13
    ]
    ordering_fields = [
        "name", "internal_code", "purchase_price", "sale_price",
        "current_stock", "category__name", "created_at",
    ]
    # CLI-68: default product listing is ascending by internal_code.
    # internal_code is unique & non-null; "id" is a stable tie-breaker.
    # Scoped to this viewset only — Product.Meta.ordering stays ["-created_at"].
    ordering        = ["internal_code", "id"]

    def get_serializer_class(self):
        if self.action in _LIST_ACTIONS:
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        """Return an optimized queryset based on the current action.

        List actions: select_related(category) + only() — one JOIN, minimal columns.
        Detail/write actions: full select_related for nested serializer fields.

        The select_related('category') + only('category__id') pattern is critical:
        PrimaryKeyRelatedField calls instance.category (not instance.category_id),
        so without select_related the field fires a per-row query.
        """
        if self.action in _LIST_ACTIONS:
            qs = (
                Product.objects
                .select_related("category")
                .only(
                    "id", "name", "internal_code", "product_type",
                    "category_id", "category__id", "category__name",
                    "unit", "purchase_price", "sale_price", "barcode",
                    "current_stock", "minimum_stock", "is_active", "created_at",
                )
            )
        else:
            qs = Product.objects.select_related("category", "category__parent")

        # Prefetch vendor links added in CLI-13 (ProductVendor through table)
        if hasattr(Product, "product_vendors"):
            qs = qs.prefetch_related("product_vendors__vendor")

        return qs

    # ------------------------------------------------------------------
    # Deletion — ordinary destroy is always blocked; permanent removal
    # only exists through the superuser-only purge actions below.
    # ------------------------------------------------------------------

    def get_permissions(self):
        if self.action in ("purge_preview", "purge"):
            from accounts.permissions import IsMainAdministrator
            return [IsAuthenticated(), IsMainAdministrator()]
        return super().get_permissions()

    def destroy(self, request, *args, **kwargs):
        """Ordinary DELETE is always blocked.

        Product has PROTECT relations (StockMovement, PurchaseItem,
        SurgeryUsedItem, SurgeryConsumptionItem) that make a plain delete
        fail outright — and even for a superuser, silently cascading here
        would be exactly the unreviewed global cascade the purge feature
        exists to avoid. Use is_active=False to deactivate, or the
        dedicated purge action (superuser-only, requires confirmation) to
        permanently remove a Product and its dependent history.
        """
        raise DRFValidationError(
            "حذف مستقیم محصول از این مسیر امکان‌پذیر نیست. "
            "برای غیرفعال‌سازی، فیلد is_active را خاموش کنید؛ "
            "برای حذف کامل و دائمی از عملیات purge (مخصوص مدیر اصلی) استفاده کنید."
        )

    @action(detail=True, methods=["get"], url_path="purge-preview")
    def purge_preview(self, request, pk=None):
        """GET /api/v1/inventory/products/{id}/purge-preview/

        Superuser-only. Read-only dependency-graph preview — see
        ProductPurgeService.preview(). Recomputed fresh on every call, so
        the numbers are always current even if called repeatedly.
        """
        from inventory.services import ProductPurgeService

        product = self.get_object()
        return Response(ProductPurgeService.preview(product), status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="purge")
    def purge(self, request, pk=None):
        """POST /api/v1/inventory/products/{id}/purge/

        Superuser-only permanent deletion. Body must include
        {"confirmation_code": "<product.internal_code>"} — a client-supplied
        dependency count is never trusted; ProductPurgeService.purge()
        recomputes the whole graph itself, inside its own atomic
        transaction, immediately before deleting anything.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        from inventory.services import ProductPurgeService

        product = self.get_object()
        confirmation = str(request.data.get("confirmation_code", "")).strip()
        if confirmation != product.internal_code:
            raise DRFValidationError(
                "کد داخلی وارد شده مطابقت ندارد. "
                "برای حذف کامل، کد داخلی محصول را دقیقاً ارسال کنید."
            )

        try:
            summary = ProductPurgeService.purge(product, request.user)
        except DjangoValidationError as exc:
            detail = exc.messages if hasattr(exc, "messages") else str(exc)
            raise DRFValidationError(detail)

        return Response(summary, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="low_stock")
    def low_stock(self, request):
        """Products at or below their minimum stock threshold.
        Ordered by current_stock ascending — most critical first."""
        from django.db.models import F
        # order_by("current_stock") must come AFTER filter_queryset: the
        # OrderingFilter applies the viewset's default ordering and would
        # otherwise overwrite this action's intended "most critical first"
        # sort.  (CLI-68 changed the default to internal_code, exposing this.)
        qs = self.filter_queryset(
            self.get_queryset().filter(
                minimum_stock__gt=0, current_stock__lte=F("minimum_stock")
            )
        ).order_by("current_stock")
        serializer = ProductListSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="vendor-price-history")
    def vendor_price_history(self, request, pk=None):
        """Per-product vendor price history derived from confirmed purchase items.

        GET /api/v1/inventory/products/{id}/vendor-price-history/

        Optional query parameters:
          vendor_id  — filter to a single vendor (integer PK)
          date_from  — ISO date (YYYY-MM-DD), inclusive lower bound on purchase_date
          date_to    — ISO date (YYYY-MM-DD), inclusive upper bound on purchase_date
          currency   — filter by currency code (e.g. IRR, USD)

        Returns all matching PurchaseItem rows (no pagination — chart needs all points).
        Results are sorted by purchase_date ascending so charts plot left-to-right.
        """
        from datetime import datetime
        from inventory.models import ProductVendor as _PV

        # Validate product exists (get_object handles 404)
        product = self.get_object()

        qs = (
            PurchaseItem.objects
            .filter(
                product=product,
                purchase__status=PurchaseStatus.CONFIRMED,
            )
            .select_related("purchase", "purchase__vendor", "product")
        )

        # Optional: filter by vendor
        vendor_id = request.query_params.get("vendor_id")
        if vendor_id is not None:
            try:
                vendor_id_int = int(vendor_id)
            except ValueError:
                return Response(
                    {"error": "vendor_id باید یک عدد صحیح باشد."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(purchase__vendor_id=vendor_id_int)

        # Optional: date range filter
        date_from = request.query_params.get("date_from")
        if date_from:
            try:
                dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            except ValueError:
                return Response(
                    {"error": "date_from باید به فرمت YYYY-MM-DD باشد."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(purchase__purchase_date__date__gte=dt_from.date())

        date_to = request.query_params.get("date_to")
        if date_to:
            try:
                dt_to = datetime.strptime(date_to, "%Y-%m-%d")
            except ValueError:
                return Response(
                    {"error": "date_to باید به فرمت YYYY-MM-DD باشد."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(purchase__purchase_date__date__lte=dt_to.date())

        # Optional: currency filter (via ProductVendor through table)
        currency = request.query_params.get("currency")
        if currency:
            vendor_ids_with_currency = (
                _PV.objects
                .filter(product=product, currency__iexact=currency)
                .values_list("vendor_id", flat=True)
            )
            qs = qs.filter(purchase__vendor_id__in=vendor_ids_with_currency)

        qs = qs.order_by("purchase__purchase_date")

        serializer = VendorPriceHistorySerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="export_ids")
    def export_ids(self, request):
        """Return the IDs of all products matching current filters (no pagination).
        Capped at 1000; returns an error with the actual count if exceeded.
        Used for bulk operations — does not load model instances into Python.
        """
        qs = self.filter_queryset(self.get_queryset())
        count = qs.count()
        if count > 1000:
            return Response(
                {
                    "error": (
                        f"نتایج خیلی زیاد است ({count} مورد). "
                        "فیلترهای خود را محدودتر کنید."
                    ),
                    "count": count,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        ids = list(qs.values_list("id", flat=True))
        return Response({"count": len(ids), "ids": ids}, status=status.HTTP_200_OK)

    # ── Excel export ──────────────────────────────────────────────────────────

    excel_filename_prefix = 'product-list'
    excel_sheet_title      = 'محصولات'
    excel_report_title     = 'گزارش فهرست محصولات'

    _ORDERING_LABELS = {
        'name':           'نام محصول',
        'internal_code':  'کد داخلی',
        'purchase_price': 'قیمت خرید',
        'sale_price':     'قیمت فروش',
        'current_stock':  'موجودی فعلی',
        'category__name': 'دسته‌بندی',
        'created_at':      'تاریخ ثبت',
    }

    def get_export_queryset(self):
        primary_vendor_qs = ProductVendor.objects.filter(is_primary=True).select_related('vendor')
        return (
            Product.objects
            .select_related('category')
            .prefetch_related(
                Prefetch('product_vendors', queryset=primary_vendor_qs, to_attr='primary_vendor_list'),
            )
            .order_by('internal_code')
        )

    def get_excel_meta_rows(self, request):
        params = request.query_params
        meta = []

        product_type_val = params.get('product_type')
        if product_type_val:
            meta.append(('نوع محصول', dict(ProductType.choices).get(product_type_val, product_type_val)))

        category_id = params.get('category')
        if category_id:
            cat = ProductCategory.objects.filter(pk=category_id).first()
            meta.append(('دسته‌بندی', cat.name if cat else category_id))

        is_active_val = params.get('is_active')
        if is_active_val:
            meta.append(('وضعیت', {'true': 'فعال', 'false': 'غیرفعال', 'all': 'همه'}.get(is_active_val, is_active_val)))

        if params.get('low_stock') in ('true', '1'):
            meta.append(('وضعیت موجودی', 'کم‌موجودی'))
        if params.get('out_of_stock') in ('true', '1'):
            meta.append(('وضعیت موجودی', 'ناموجود'))

        price_min = params.get('price_min')
        price_max = params.get('price_max')
        if price_min or price_max:
            meta.append(('بازه قیمت خرید', f"{price_min or '—'} تا {price_max or '—'}"))

        search_val = params.get('search')
        if search_val:
            meta.append(('جستجو', search_val))

        ordering_desc = describe_ordering(params.get('ordering'), self._ORDERING_LABELS)
        if ordering_desc:
            meta.append(('مرتب‌سازی', ordering_desc))

        return meta

    def get_excel_columns(self, request):
        return [
            ExcelColumn(key='row_number',     label='ردیف',                 data_type='integer', width=6),
            ExcelColumn(key='internal_code',  label='کد داخلی',             data_type='text',   width=14),
            ExcelColumn(key='name',           label='نام محصول',            data_type='text',   width=26),
            ExcelColumn(key='product_type',   label='نوع محصول',            data_type='text',   width=12),
            ExcelColumn(key='category_name',  label='دسته‌بندی',            data_type='text',   width=18),
            ExcelColumn(key='unit',           label='واحد',                 data_type='text',   width=10),
            ExcelColumn(key='purchase_price', label='قیمت خرید (تومان)',    data_type='money',  width=16),
            ExcelColumn(key='sale_price',     label='قیمت فروش (تومان)',    data_type='money',  width=16),
            ExcelColumn(key='current_stock',  label='موجودی فعلی',          data_type='number', width=12),
            ExcelColumn(key='minimum_stock',  label='حداقل موجودی',         data_type='number', width=12),
            ExcelColumn(key='stock_status',   label='وضعیت موجودی',         data_type='text',   width=12),
            ExcelColumn(key='last_vendor',    label='آخرین تامین‌کننده',    data_type='text',   width=20),
            ExcelColumn(key='barcode',        label='بارکد',                data_type='text',   width=16),
            ExcelColumn(key='is_active_display', label='فعال / غیرفعال',    data_type='text',   width=12),
            ExcelColumn(key='description',    label='توضیحات',              data_type='text',   width=28, wrap=True),
        ]

    @staticmethod
    def _stock_status(obj):
        if obj.is_out_of_stock:
            return 'ناموجود'
        if obj.is_low_stock:
            return 'کم‌موجودی'
        return 'موجود'

    @staticmethod
    def _last_vendor_name(obj):
        primary = getattr(obj, 'primary_vendor_list', None) or []
        return primary[0].vendor.name if primary else None

    def queryset_to_excel_rows(self, queryset):
        for idx, obj in enumerate(queryset, start=1):
            yield {
                'row_number':       idx,
                'internal_code':    obj.internal_code,
                'name':             obj.name,
                'product_type':     obj.get_product_type_display(),
                'category_name':    obj.category.name if obj.category else None,
                'unit':             obj.unit,
                'purchase_price':   obj.purchase_price,
                'sale_price':       obj.sale_price,
                'current_stock':    obj.current_stock,
                'minimum_stock':    obj.minimum_stock,
                'stock_status':     self._stock_status(obj),
                'last_vendor':      self._last_vendor_name(obj),
                'barcode':          obj.barcode,
                'is_active_display': 'فعال' if obj.is_active else 'غیرفعال',
                'description':      obj.internal_notes,
            }

    def get_excel_summary(self, request, queryset):
        products = list(queryset)
        total     = len(products)
        medicine  = sum(1 for p in products if p.product_type == ProductType.MEDICINE)
        equipment = sum(1 for p in products if p.product_type == ProductType.EQUIPMENT)
        in_stock  = sum(1 for p in products if not p.is_out_of_stock and not p.is_low_stock)
        low_stock = sum(1 for p in products if p.is_low_stock and not p.is_out_of_stock)
        out_of_stock = sum(1 for p in products if p.is_out_of_stock)
        # Same rule the project already trusts elsewhere (PriceService /
        # cost reports): stock value = current_stock × purchase_price.
        inventory_value = sum((p.current_stock * p.purchase_price for p in products), Decimal('0'))
        return [
            ('تعداد کل محصولات',    total),
            ('تعداد داروها',        medicine),
            ('تعداد تجهیزات',       equipment),
            ('تعداد محصولات موجود', in_stock),
            ('تعداد محصولات کم‌موجود', low_stock),
            ('تعداد محصولات ناموجود', out_of_stock),
            ('ارزش تقریبی موجودی (تومان)', inventory_value),
        ]


# ---------------------------------------------------------------------------
# Vendor viewset
# ---------------------------------------------------------------------------

class VendorViewSet(viewsets.ModelViewSet):
    """CRUD viewset for vendors / suppliers.

    GET/POST             /api/v1/inventory/vendors/
    GET/PUT/PATCH/DELETE /api/v1/inventory/vendors/{id}/

    Search (?search=):
      name, phone_number, email, tax_id

    Filters (?is_active=true/false):
      is_active

    Ordering (?ordering=):
      name, current_balance, created_at  (default: name)
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_fields  = ["is_active"]
    search_fields     = ["name", "phone_number", "email", "tax_id", "additional_phones__phone"]
    ordering_fields   = ["name", "current_balance", "created_at"]
    ordering          = ["name"]

    def get_serializer_class(self):
        if self.action == "list":
            return VendorListSerializer
        return VendorSerializer

    def get_queryset(self):
        return Vendor.objects.prefetch_related("additional_phones").distinct()

    @action(detail=True, methods=["get"], url_path="purchased-products")
    def purchased_products(self, request, pk=None):
        """GET /api/v1/inventory/vendors/{id}/purchased-products/

        Products purchased from this vendor based on CONFIRMED purchase history.
        Each product appears once regardless of how many confirmed purchases it
        appears in.  Aggregate annotations: purchase_count, total_quantity,
        last_purchase_date, last_unit_price.

        Optional ?search= filters by name or internal_code (case-insensitive).
        """
        vendor = self.get_object()
        from inventory.services import VendorService
        qs = VendorService.get_vendor_purchased_products(vendor.pk)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(internal_code__icontains=search)
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = VendorPurchasedProductSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = VendorPurchasedProductSerializer(qs, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# ProductVendor viewset
# ---------------------------------------------------------------------------

class ProductVendorViewSet(viewsets.ModelViewSet):
    """CRUD viewset for product–vendor relationships (through table).

    GET/POST             /api/v1/inventory/product-vendors/
    GET/PUT/PATCH/DELETE /api/v1/inventory/product-vendors/{id}/

    Filters (?product=&vendor=&is_active=&is_primary=):
      product, vendor, is_active, is_primary

    Search (?search=):
      product name/code, vendor name,
      supplier_product_name, supplier_product_code

    Ordering (?ordering=):
      unit_price, lead_time_days, last_price_date, created_at
      (default: vendor__name, product__name)
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_fields  = ["product", "vendor", "is_active", "is_primary"]
    search_fields     = [
        "product__name",
        "product__internal_code",
        "vendor__name",
        "supplier_product_name",
        "supplier_product_code",
    ]
    ordering_fields   = ["unit_price", "lead_time_days", "last_price_date", "created_at"]
    ordering          = ["vendor__name", "product__name"]

    def get_serializer_class(self):
        if self.action == "list":
            return ProductVendorListSerializer
        return ProductVendorSerializer

    def get_queryset(self):
        return (
            ProductVendor.objects
            .select_related("product", "vendor")
        )

    def list(self, request, *args, **kwargs):
        """Override list to inject per-vendor purchase stats without N+1 queries.

        When ?product=<id> is present, a single grouped aggregate query computes
        total confirmed-purchase quantity and latest confirmed-purchase date for
        every vendor that has sold that product.  The result is passed to the
        serializer via context so each row can look up its stats in O(1).
        """
        queryset = self.filter_queryset(self.get_queryset())

        purchase_stats: dict = {}
        product_id_raw = request.query_params.get("product")
        if product_id_raw:
            try:
                product_id_int = int(product_id_raw)
                rows = (
                    PurchaseItem.objects
                    .filter(
                        product_id=product_id_int,
                        purchase__status=PurchaseStatus.CONFIRMED,
                    )
                    .values("purchase__vendor_id")
                    .annotate(
                        total_qty=Sum("quantity"),
                        latest_date=Max("purchase__purchase_date"),
                    )
                )
                for row in rows:
                    purchase_stats[row["purchase__vendor_id"]] = {
                        "total_qty":   row["total_qty"],
                        "latest_date": row["latest_date"],
                    }
            except (ValueError, TypeError):
                pass

        extra_ctx = {"purchase_stats": purchase_stats}

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(
                page, many=True,
                context={**self.get_serializer_context(), **extra_ctx},
            )
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(
            queryset, many=True,
            context={**self.get_serializer_context(), **extra_ctx},
        )
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# StockMovement viewset
# ---------------------------------------------------------------------------

class StockMovementViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Append-only viewset for stock/inventory movements.

    POST   /api/v1/inventory/stock-movements/         — record a movement
    GET    /api/v1/inventory/stock-movements/         — paginated history
    GET    /api/v1/inventory/stock-movements/{id}/    — single record

    PUT / PATCH / DELETE are intentionally excluded — the movement log is
    the audit trail and must not be altered after creation.

    Filters (?product=&movement_type=&source_type=):
      product, movement_type, source_type

    Search (?search=):
      product name, internal code, description, reference_id

    Ordering (?ordering=):
      movement_date, quantity, created_at  (default: -movement_date)
    """

    permission_classes = [IsAuthenticated]
    pagination_class   = ProductPagination
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields   = ["product", "movement_type", "source_type"]
    search_fields      = [
        "product__name",
        "product__internal_code",
        "description",
        "reference_id",
    ]
    ordering_fields    = ["movement_date", "quantity", "created_at"]
    ordering           = ["-movement_date", "-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return StockMovementListSerializer
        return StockMovementSerializer

    def get_queryset(self):
        return StockMovement.objects.select_related("product")

    def perform_create(self, serializer):
        """Convert Django ValidationError (from _apply_stock_delta) to HTTP 400."""
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)


# ---------------------------------------------------------------------------
# Purchase viewset
# ---------------------------------------------------------------------------

class PurchaseViewSet(ExcelExportMixin, viewsets.ModelViewSet):
    """CRUD viewset for purchase orders with a confirm action.

    GET/POST             /api/v1/inventory/purchases/
    GET/PUT/PATCH/DELETE /api/v1/inventory/purchases/{id}/
    POST                 /api/v1/inventory/purchases/{id}/confirm/

    confirm/ — transitions status to CONFIRMED and creates IN StockMovements
    for every PurchaseItem.  The operation is idempotent: confirming an
    already-confirmed purchase does not create duplicate movements.

    Filters (?vendor=&status=&stock_applied=):
      vendor, status, stock_applied

    Search (?search=):
      reference_number, vendor name, notes

    Ordering (?ordering=):
      purchase_date, created_at, status  (default: -purchase_date)
    """

    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class    = PurchaseFilter
    search_fields      = ["reference_number", "vendor__name", "notes"]
    ordering_fields    = ["purchase_date", "vendor__name", "status", "created_at"]
    ordering           = ["-purchase_date", "-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return PurchaseListSerializer
        return PurchaseSerializer

    def get_queryset(self):
        if self.action == "list":
            return Purchase.objects.select_related("vendor").prefetch_related("items")
        return (
            Purchase.objects
            .select_related("vendor")
            .prefetch_related("items__product")
        )

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        """Confirm the purchase: create IN stock movements for all items."""
        purchase = self.get_object()
        try:
            purchase.confirm()
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)
        serializer = PurchaseSerializer(purchase)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel the purchase, creating reverse OUT movements if confirmed."""
        purchase = self.get_object()
        try:
            purchase.cancel()
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages)
        serializer = PurchaseSerializer(purchase)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """Block deletion of purchases that have already affected inventory.

        A purchase with stock_applied=True has IN StockMovements tied to it
        via reference_id.  Deleting the purchase would orphan those audit
        records.  The correct remediation is to cancel the purchase first
        (which creates balancing OUT movements) and then, if needed, archive
        or hide the record at the application level.

        Raises DRFValidationError (HTTP 400) when:
          - stock_applied is True  (stock movements were ever created)
          - status is CONFIRMED    (belt-and-suspenders: confirm() always sets
                                    stock_applied, but guard both conditions)
        """
        purchase = self.get_object()
        if purchase.stock_applied or purchase.status == PurchaseStatus.CONFIRMED:
            raise DRFValidationError(
                "خریدی که موجودی آن اعمال شده یا در وضعیت تأیید شده است را نمی‌توان "
                "حذف کرد. ابتدا خرید را از طریق عملیات لغو، برگشت بزنید."
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="price_history")
    def price_history(self, request):
        """Purchase price history for a product — used by CLI-17 vendor price chart.

        Required: ?product={id}
        Returns all CONFIRMED purchase items for the product ordered by
        purchase_date ascending.  No pagination — chart needs all data points.
        """
        product_id = request.query_params.get("product")
        if not product_id:
            return Response(
                {"error": "پارامتر product الزامی است."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        items = (
            PurchaseItem.objects
            .filter(
                product_id=product_id,
                purchase__status=PurchaseStatus.CONFIRMED,
            )
            .select_related("purchase", "purchase__vendor")
            .order_by("purchase__purchase_date")
        )
        serializer = PurchasePriceHistorySerializer(items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # ── Excel export ──────────────────────────────────────────────────────────
    # Two-sheet workbook: "خلاصه خریدها" (one row per Purchase) and
    # "اقلام خرید" (one row per PurchaseItem) — both built from the same
    # filtered Purchase queryset, so search/filters/ordering are applied once.

    excel_filename_prefix = 'purchase-list'
    excel_report_title     = 'گزارش خریدها'

    _ORDERING_LABELS = {
        'purchase_date': 'تاریخ خرید',
        'vendor__name':  'تامین‌کننده',
        'status':        'وضعیت خرید',
        'created_at':     'تاریخ ثبت',
    }

    def get_excel_meta_rows(self, request):
        params = request.query_params
        meta = []

        vendor_id = params.get('vendor')
        if vendor_id:
            vendor = Vendor.objects.filter(pk=vendor_id).first()
            meta.append(('تامین‌کننده', vendor.name if vendor else vendor_id))

        status_val = params.get('status')
        if status_val:
            meta.append(('وضعیت خرید', dict(PurchaseStatus.choices).get(status_val, status_val)))

        date_from = params.get('date_from')
        date_to   = params.get('date_to')
        if date_from or date_to:
            meta.append(('بازه تاریخ خرید', f"{date_from or '—'} تا {date_to or '—'}"))

        search_val = params.get('search')
        if search_val:
            meta.append(('جستجو', search_val))

        ordering_desc = describe_ordering(params.get('ordering'), self._ORDERING_LABELS)
        if ordering_desc:
            meta.append(('مرتب‌سازی', ordering_desc))

        return meta

    @staticmethod
    def _purchase_summary_columns():
        return [
            ExcelColumn(key='row_number',  label='ردیف',                    data_type='integer', width=6),
            ExcelColumn(key='reference',   label='شماره خرید/فاکتور',       data_type='text',   width=18),
            ExcelColumn(key='vendor_name', label='تامین‌کننده',             data_type='text',   width=20),
            ExcelColumn(key='purchase_date', label='تاریخ خرید',            data_type='date',   width=13),
            ExcelColumn(key='item_count',  label='تعداد اقلام',             data_type='integer', width=10),
            ExcelColumn(key='total_amount', label='مبلغ کل (تومان)',        data_type='money',  width=16),
            ExcelColumn(key='status_display', label='وضعیت خرید',          data_type='text',   width=14),
        ]

    @staticmethod
    def _purchase_summary_rows(purchases):
        for idx, purchase in enumerate(purchases, start=1):
            items = list(purchase.items.all())
            yield {
                'row_number':    idx,
                'reference':     purchase.reference_number or f'#{purchase.pk}',
                'vendor_name':   purchase.vendor.name,
                'purchase_date': purchase.purchase_date,
                'item_count':    len(items),
                'total_amount':  sum((item.effective_total for item in items), Decimal('0')),
                'status_display': purchase.get_status_display(),
            }

    @staticmethod
    def _purchase_item_columns():
        return [
            ExcelColumn(key='reference',    label='شماره خرید/فاکتور', data_type='text',  width=16),
            ExcelColumn(key='product_name', label='محصول',              data_type='text',  width=22),
            ExcelColumn(key='vendor_name',  label='تامین‌کننده',        data_type='text',  width=18),
            ExcelColumn(key='quantity',     label='تعداد',              data_type='number', width=10),
            ExcelColumn(key='unit_price',   label='قیمت واحد (تومان)',  data_type='money', width=16),
            ExcelColumn(key='total_price',  label='مبلغ کل (تومان)',    data_type='money', width=16),
            ExcelColumn(key='purchase_date', label='تاریخ خرید',        data_type='date',  width=13),
            ExcelColumn(key='status_display', label='وضعیت خرید',      data_type='text',  width=14),
        ]

    @staticmethod
    def _purchase_item_rows(purchases):
        for purchase in purchases:
            for item in purchase.items.all():
                yield {
                    'reference':     purchase.reference_number or f'#{purchase.pk}',
                    'product_name':  item.product.name,
                    'vendor_name':   purchase.vendor.name,
                    'quantity':      item.quantity,
                    'unit_price':    item.unit_price,
                    'total_price':   item.effective_total,
                    'purchase_date': purchase.purchase_date,
                    'status_display': purchase.get_status_display(),
                }

    def get_excel_summary(self, request, purchases):
        total = len(purchases)
        confirmed = sum(1 for p in purchases if p.status == PurchaseStatus.CONFIRMED)
        pending   = sum(1 for p in purchases if p.status == PurchaseStatus.PENDING)
        cancelled = sum(1 for p in purchases if p.status == PurchaseStatus.CANCELLED)
        total_amount = sum(
            (sum((i.effective_total for i in p.items.all()), Decimal('0')) for p in purchases),
            Decimal('0'),
        )
        return [
            ('تعداد کل خریدها',   total),
            ('مجموع مبلغ خریدها', total_amount),
            ('تعداد تأییدشده',    confirmed),
            ('تعداد در انتظار تأیید', pending),
            ('تعداد لغوشده',      cancelled),
        ]

    def _handle_excel_export(self, request):
        purchase_qs = self.filter_queryset(Purchase.objects.select_related('vendor').prefetch_related('items__product'))
        count = purchase_qs.count()
        if count > EXCEL_MAX_ROWS:
            return Response(
                {
                    'detail': (
                        f'تعداد نتایج ({count:,}) بیشتر از حد مجاز ({EXCEL_MAX_ROWS:,}) است. '
                        'لطفاً فیلترها را محدودتر کنید.'
                    ),
                    'count': count,
                    'max':   EXCEL_MAX_ROWS,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        purchases = list(purchase_qs)

        summary_sheet = ExcelSheet(
            name='خلاصه خریدها',
            columns=self._purchase_summary_columns(),
            rows=list(self._purchase_summary_rows(purchases)),
            summary=self.get_excel_summary(request, purchases),
        )
        items_sheet = ExcelSheet(
            name='اقلام خرید',
            columns=self._purchase_item_columns(),
            rows=list(self._purchase_item_rows(purchases)),
            empty_message='برای خریدهای این گزارش هیچ قلمی ثبت نشده است.',
        )
        content = build_workbook(
            [summary_sheet, items_sheet],
            report_title=self.excel_report_title,
            meta_rows=self.get_excel_meta_rows(request),
            generated_by=get_display_name(request.user),
        )
        return excel_file_response(content, filename=self.get_excel_filename())

    def perform_update(self, serializer):
        """After updating a purchase, recalculate all product prices.

        purchase_date changes alter which PurchaseItem is 'latest' for every
        product in the purchase.  Signals only fire on item saves; they do not
        cover purchase-header-only edits.
        """
        instance = serializer.save()
        from inventory.services import PriceService
        product_ids = set(instance.items.values_list("product_id", flat=True))
        for product_id in product_ids:
            PriceService.recalculate_product_price(product_id)

    def queryset_to_excel_rows(self, queryset):   # pragma: no cover
        pass   # not called — _handle_excel_export is overridden


# ---------------------------------------------------------------------------
# PurchaseItem viewset
# ---------------------------------------------------------------------------

class PurchaseItemViewSet(viewsets.ModelViewSet):
    """CRUD viewset for purchase line items.

    GET/POST             /api/v1/inventory/purchase-items/
    GET/PUT/PATCH/DELETE /api/v1/inventory/purchase-items/{id}/

    Items can only be created/modified while the parent Purchase is PENDING.
    The serializer enforces this rule via validate().

    Filters (?purchase=&product=):
      purchase, product

    Ordering (?ordering=):
      created_at  (default: purchase, product name)
    """

    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ["purchase", "product"]
    ordering_fields    = ["created_at"]
    ordering           = ["purchase", "product__name"]
    serializer_class   = PurchaseItemSerializer

    def get_queryset(self):
        return PurchaseItem.objects.select_related("purchase", "product")

    def perform_update(self, serializer):
        """After updating a purchase item, recalculate the old product's price
        if the product FK was changed.

        The post_save signal handles the new product_id; this covers the old one.
        """
        old_product_id = serializer.instance.product_id
        instance = serializer.save()
        if old_product_id != instance.product_id:
            from inventory.services import PriceService
            PriceService.recalculate_product_price(old_product_id)

    def perform_destroy(self, instance):
        """Block item deletion for non-PENDING purchases.

        Confirmed and cancelled purchases are immutable to protect stock
        history integrity.  Deleting items from a confirmed purchase would
        create a zero-item confirmed purchase — an invalid state.
        """
        from inventory.models import PurchaseStatus
        from rest_framework.exceptions import ValidationError as DRFValidationError
        if instance.purchase.status != PurchaseStatus.PENDING:
            raise DRFValidationError(
                "اقلام خرید تأیید شده یا لغو شده را نمی‌توان حذف کرد."
            )
        instance.delete()


# ---------------------------------------------------------------------------
# Inventory Stock Report
# ---------------------------------------------------------------------------

class InventoryStockReportView(APIView):
    """Inventory stock-level report for all products.

    GET /api/v1/inventory/reports/stock/

    Query parameters:
      product_type  — 'medicine' or 'equipment'
      category      — ProductCategory PK
      low_stock     — 'true' to return only low-stock products
      out_of_stock  — 'true' to return only out-of-stock products
      page / page_size — standard pagination

    Response:
      {
        summary: {
          total_products, low_stock_count, out_of_stock_count,
          total_inventory_value
        },
        count: N,
        next: "...",
        previous: "...",
        results: [ { product fields + inventory_value }, ... ]
      }

    Inventory value = current_stock × purchase_price (decimal-safe).
    low_stock  = current_stock <= minimum_stock AND minimum_stock > 0.
    out_of_stock = current_stock <= 0.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params

        # Apply type / category filters to a base queryset used for both
        # the summary counts and the paginated product list.
        base_qs = Product.objects.select_related('category')

        product_type     = params.get('product_type')
        category         = params.get('category')
        low_stock_only   = params.get('low_stock',    '').lower() == 'true'
        out_of_stock_only = params.get('out_of_stock', '').lower() == 'true'

        if product_type:
            base_qs = base_qs.filter(product_type=product_type)
        if category:
            base_qs = base_qs.filter(category_id=category)

        # Summary counts are always over the type/category filtered set
        low_stock_qs    = base_qs.filter(minimum_stock__gt=0, current_stock__lte=F('minimum_stock'))
        out_of_stock_qs = base_qs.filter(current_stock__lte=0)

        total_products     = base_qs.count()
        low_stock_count    = low_stock_qs.count()
        out_of_stock_count = out_of_stock_qs.count()

        # Total inventory value (decimal-safe via Python aggregation fallback)
        value_rows = base_qs.values('current_stock', 'purchase_price')
        total_inventory_value = sum(
            (Decimal(str(r['current_stock'])) * Decimal(str(r['purchase_price'])))
            for r in value_rows
        )

        summary = {
            'total_products':        total_products,
            'low_stock_count':       low_stock_count,
            'out_of_stock_count':    out_of_stock_count,
            'total_inventory_value': total_inventory_value,
        }

        # Apply stock-level filters for the product list
        list_qs = base_qs
        if low_stock_only:
            list_qs = list_qs.filter(minimum_stock__gt=0, current_stock__lte=F('minimum_stock'))
        elif out_of_stock_only:
            list_qs = list_qs.filter(current_stock__lte=0)

        list_qs = list_qs.order_by('name')

        # Paginate
        paginator = ProductPagination()
        page      = paginator.paginate_queryset(list_qs, request)
        products  = InventoryStockProductSerializer(
            page if page is not None else list_qs, many=True
        ).data

        summary_data = InventoryStockReportSummarySerializer(summary).data

        if page is not None:
            paginated = paginator.get_paginated_response(products)
            paginated.data['summary'] = summary_data
            return paginated

        return Response({'summary': summary_data, 'results': products})


# ---------------------------------------------------------------------------
# Product Cost Report
# ---------------------------------------------------------------------------

class ProductCostReportView(APIView):
    """Purchase cost report — aggregates confirmed PurchaseItem totals.

    GET /api/v1/inventory/reports/cost/

    Query parameters:
        start_date   — YYYY-MM-DD (optional)
        end_date     — YYYY-MM-DD (optional)
        product_type — 'medicine' | 'equipment'  (default: all)
        group_by     — 'product' (default) | 'vendor' | 'product_vendor'
        vendor_id    — integer PK (optional, limits to one vendor)
        page         — page number, default 1
        page_size    — items per page, 1–100, default 50

    Only purchases with status=CONFIRMED are included.
    Results ordered by total_cost descending (highest spend first).

    Response shape:
        {
            "metadata": { start_date, end_date, product_type, group_by,
                          vendor_id, total_cost, total_quantity, total_line_items },
            "count": N,
            "next": "...",
            "previous": "...",
            "results": [ { product_id?, product_name?, product_code?,
                           product_type?, vendor_id?, vendor_name?,
                           total_quantity, total_cost, avg_unit_price,
                           purchase_count }, ... ]
        }
    """

    permission_classes = [IsAdminOrFinanceUser]

    _VALID_GROUP_BY = frozenset({'product', 'vendor', 'product_vendor'})

    # Reusable ORM expression: cost of one purchase item line = qty × unit_price
    @staticmethod
    def _cost_expr():
        return ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DBDecimalField(max_digits=20, decimal_places=2),
        )

    def get(self, request):
        params = request.query_params

        start_date   = params.get('start_date')
        end_date     = params.get('end_date')
        product_type = params.get('product_type', '').strip().lower()
        group_by     = params.get('group_by', 'product').strip().lower()
        vendor_id    = params.get('vendor_id')

        if group_by not in self._VALID_GROUP_BY:
            group_by = 'product'

        # Base queryset — confirmed purchases only
        qs = PurchaseItem.objects.filter(purchase__status=PurchaseStatus.CONFIRMED)

        # Date range — purchase_date is a DateTimeField so use __date for day precision
        if start_date:
            try:
                qs = qs.filter(purchase__purchase_date__date__gte=start_date)
            except (ValueError, TypeError):
                pass
        if end_date:
            try:
                qs = qs.filter(purchase__purchase_date__date__lte=end_date)
            except (ValueError, TypeError):
                pass

        # Product type
        if product_type in ('medicine', 'equipment'):
            qs = qs.filter(product__product_type=product_type)

        # Single-vendor filter
        if vendor_id:
            try:
                qs = qs.filter(purchase__vendor_id=int(vendor_id))
            except (ValueError, TypeError):
                pass

        # Grand-total summary (computed before pagination)
        agg = qs.aggregate(
            grand_total_cost=Sum(self._cost_expr()),
            grand_total_qty=Sum('quantity'),
            total_items=Count('id'),
        )

        metadata = {
            'start_date':       start_date,
            'end_date':         end_date,
            'product_type':     product_type or 'all',
            'group_by':         group_by,
            'vendor_id':        int(vendor_id) if vendor_id else None,
            'total_cost':       Decimal(str(agg['grand_total_cost'] or '0')),
            'total_quantity':   Decimal(str(agg['grand_total_qty']  or '0')),
            'total_line_items': agg['total_items'] or 0,
        }

        # Build grouped queryset ordered by highest cost first
        rows_qs = self._grouped_qs(qs, group_by)

        # ── Excel export (no pagination) ──────────────────────────────────────
        if params.get('export') == 'excel':
            total_count = rows_qs.count()
            if total_count > EXCEL_MAX_ROWS:
                return Response(
                    {'detail': f'تعداد نتایج ({total_count:,}) بیشتر از حد مجاز است.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            all_rows = self._serialize_rows(list(rows_qs), group_by)
            columns  = self._excel_columns(group_by)
            meta_rows = [
                ('از تاریخ',   start_date or ''),
                ('تا تاریخ',   end_date   or ''),
                ('نوع محصول',  product_type or 'همه'),
                ('گروه‌بندی',  group_by),
            ]
            content = build_excel(columns=columns, rows=all_rows,
                                   sheet_title='هزینه خرید', meta_rows=meta_rows)
            return excel_file_response(content, filename='product_cost_report.xlsx')

        # Pagination
        try:
            page      = max(1, int(params.get('page', 1)))
            page_size = min(max(1, int(params.get('page_size', 50))), 100)
        except (ValueError, TypeError):
            page, page_size = 1, 50

        total_count = rows_qs.count()
        offset      = (page - 1) * page_size
        page_rows   = list(rows_qs[offset:offset + page_size])

        results = self._serialize_rows(page_rows, group_by)

        # Build next/previous URLs
        def _page_url(p):
            params_copy = dict(params)
            params_copy['page']      = str(p)
            params_copy['page_size'] = str(page_size)
            return (
                request.build_absolute_uri(request.path)
                + '?' + '&'.join(f'{k}={v}' for k, v in params_copy.items())
            )

        next_url = _page_url(page + 1) if offset + page_size < total_count else None
        prev_url = _page_url(page - 1) if page > 1 else None

        return Response({
            'metadata': ProductCostReportSummarySerializer(metadata).data,
            'count':    total_count,
            'next':     next_url,
            'previous': prev_url,
            'results':  results,
        })

    def _grouped_qs(self, qs, group_by):
        """Return the fully-annotated, ordered queryset for the requested grouping."""
        cost_expr = self._cost_expr()
        common_annotations = dict(
            total_quantity=Sum('quantity'),
            total_cost=Sum(cost_expr),
            avg_unit_price=Avg('unit_price'),
            purchase_count=Count('id'),
        )

        if group_by == 'vendor':
            return (
                qs
                .values('purchase__vendor_id', 'purchase__vendor__name')
                .annotate(**common_annotations)
                .order_by('-total_cost')
            )

        if group_by == 'product_vendor':
            return (
                qs
                .values(
                    'product_id',
                    'product__name',
                    'product__internal_code',
                    'product__product_type',
                    'purchase__vendor_id',
                    'purchase__vendor__name',
                )
                .annotate(**common_annotations)
                .order_by('-total_cost')
            )

        # Default: group by product
        return (
            qs
            .values(
                'product_id',
                'product__name',
                'product__internal_code',
                'product__product_type',
            )
            .annotate(**common_annotations)
            .order_by('-total_cost')
        )

    @staticmethod
    def _serialize_rows(rows, group_by):
        """Normalise ORM ValuesQuerySet rows to clean API field names."""
        result = []
        for row in rows:
            item = {
                'total_quantity': str(row.get('total_quantity')  or '0'),
                'total_cost':     str(row.get('total_cost')      or '0'),
                'avg_unit_price': str(row.get('avg_unit_price')  or '0'),
                'purchase_count': row.get('purchase_count', 0),
            }
            if group_by in ('product', 'product_vendor'):
                item['product_id']   = row.get('product_id')
                item['product_name'] = row.get('product__name')
                item['product_code'] = row.get('product__internal_code')
                item['product_type'] = row.get('product__product_type')
            if group_by in ('vendor', 'product_vendor'):
                item['vendor_id']   = row.get('purchase__vendor_id')
                item['vendor_name'] = row.get('purchase__vendor__name')
            result.append(item)
        return result

    @staticmethod
    def _excel_columns(group_by):
        """Return Persian column list for the given group_by mode."""
        base = [
            ('تعداد خرید',        'purchase_count'),
            ('مجموع تعداد',       'total_quantity'),
            ('میانگین قیمت واحد', 'avg_unit_price'),
            ('مجموع هزینه',       'total_cost'),
        ]
        if group_by == 'vendor':
            return [('تامین‌کننده', 'vendor_name')] + base
        if group_by == 'product_vendor':
            return [
                ('محصول',          'product_name'),
                ('تامین‌کننده',    'vendor_name'),
            ] + base
        # Default: product
        return [
            ('محصول',      'product_name'),
            ('نوع محصول',  'product_type'),
        ] + base
