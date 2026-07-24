import django_filters
from django.db.models import F, Q

from common.filters import JalaliDateFilter
from inventory.models import Product, ProductCategory, ProductType, Purchase, PurchaseStatus


class ProductFilter(django_filters.FilterSet):
    """Declarative FilterSet for the product list/search endpoint.

    All filtering logic lives here — zero manual if/else in the view.

    is_active default:
      When ?is_active is absent the qs property applies is_active=True.
      This preserves the expected behaviour (list shows active items by
      default) without hardcoding it in the view.
    """

    product_type = django_filters.ChoiceFilter(choices=ProductType.choices)

    # Exact category match (PK)
    category = django_filters.NumberFilter(field_name="category_id", lookup_expr="exact")

    # Category + all descendants — Python-side ID collection, then __in
    # Risk vs. recursive SQL: for clinic-scale data (< 100 categories,
    # max 4 levels) this is safe and avoids DB-backend-specific CTEs.
    category_tree = django_filters.NumberFilter(method="filter_category_tree")

    # is_active is handled manually in the qs property (tri-state: true / false / all)
    # Removing the BooleanFilter declaration prevents validation failure on "all".

    low_stock    = django_filters.BooleanFilter(method="filter_low_stock")
    out_of_stock = django_filters.BooleanFilter(method="filter_out_of_stock")

    price_min = django_filters.NumberFilter(field_name="purchase_price", lookup_expr="gte")
    price_max = django_filters.NumberFilter(field_name="purchase_price", lookup_expr="lte")

    has_barcode = django_filters.BooleanFilter(method="filter_has_barcode")

    # Vendor: filter products supplied by a specific vendor (via ProductVendor join)
    vendor    = django_filters.NumberFilter(method="filter_vendor")

    # Stock range: current_stock range filter
    stock_min = django_filters.NumberFilter(field_name="current_stock", lookup_expr="gte")
    stock_max = django_filters.NumberFilter(field_name="current_stock", lookup_expr="lte")

    class Meta:
        model  = Product
        fields = ["product_type", "category"]

    # ------------------------------------------------------------------
    # Default: show active products when is_active is not specified
    # ------------------------------------------------------------------

    @property
    def qs(self):
        qs = super().qs
        val = self.data.get("is_active")
        if val is None or val == "":
            qs = qs.filter(is_active=True)          # default: active only
        elif val.lower() in ("true", "1"):
            qs = qs.filter(is_active=True)
        elif val.lower() in ("false", "0"):
            qs = qs.filter(is_active=False)
        # "all" or any unrecognised value → no is_active filter (show everything)
        return qs

    # ------------------------------------------------------------------
    # Custom filter methods
    # ------------------------------------------------------------------

    def filter_category_tree(self, queryset, name, value):
        try:
            cat = ProductCategory.objects.get(pk=value)
        except ProductCategory.DoesNotExist:
            return queryset.none()
        ids = {cat.pk} | {d.pk for d in cat.get_all_descendants()}
        return queryset.filter(category__in=ids)

    def filter_low_stock(self, queryset, name, value):
        if value:
            return queryset.filter(minimum_stock__gt=0, current_stock__lte=F("minimum_stock"))
        return queryset

    def filter_out_of_stock(self, queryset, name, value):
        if value:
            return queryset.filter(current_stock__lte=0)
        return queryset

    def filter_has_barcode(self, queryset, name, value):
        if value:
            return queryset.filter(barcode__isnull=False)
        return queryset.filter(barcode__isnull=True)

    def filter_vendor(self, queryset, name, value):
        """Return products that have at least one ProductVendor record for the given vendor."""
        return queryset.filter(product_vendors__vendor_id=value).distinct()


# ---------------------------------------------------------------------------
# PurchaseFilter
# ---------------------------------------------------------------------------

class PurchaseFilter(django_filters.FilterSet):
    """FilterSet for the purchase list endpoint.

    Replaces the simple filterset_fields approach to add date range support.
    """

    status    = django_filters.ChoiceFilter(choices=PurchaseStatus.choices)
    vendor    = django_filters.NumberFilter(field_name="vendor_id", lookup_expr="exact")
    date_from = JalaliDateFilter(field_name="purchase_date", lookup_expr="gte")
    date_to   = JalaliDateFilter(field_name="purchase_date", lookup_expr="lte")

    class Meta:
        model  = Purchase
        fields = ["vendor", "status", "stock_applied"]
