from django.urls import path
from rest_framework.routers import DefaultRouter

from inventory.views import (
    InventoryStockReportView,
    ProductCategoryViewSet,
    ProductCostReportView,
    ProductVendorViewSet,
    ProductViewSet,
    PurchaseItemViewSet,
    PurchaseViewSet,
    StockMovementViewSet,
    VendorViewSet,
)

app_name = "inventory"

router = DefaultRouter()
router.register("categories",      ProductCategoryViewSet, basename="category")
router.register("products",        ProductViewSet,         basename="product")
router.register("vendors",         VendorViewSet,          basename="vendor")
router.register("product-vendors", ProductVendorViewSet,   basename="product-vendor")
router.register("stock-movements", StockMovementViewSet,   basename="stock-movement")
router.register("purchases",       PurchaseViewSet,        basename="purchase")
router.register("purchase-items",  PurchaseItemViewSet,    basename="purchase-item")

# Registered routes:
#   GET      /api/v2/inventory/categories/            — flat list (filterable)
#   GET      /api/v2/inventory/categories/{id}/       — single category + children
#   GET      /api/v2/inventory/categories/tree/       — full nested tree from roots
#
#   GET/POST /api/v2/inventory/products/              — list / create
#   GET/PUT/PATCH/DELETE /api/v2/inventory/products/{id}/
#   GET      /api/v2/inventory/products/low_stock/    — products at/below threshold
#   GET      /api/v2/inventory/products/export_ids/   — filtered product IDs
#
#   GET/POST /api/v2/inventory/vendors/               — list / create
#   GET/PUT/PATCH/DELETE /api/v2/inventory/vendors/{id}/
#
#   GET/POST /api/v2/inventory/product-vendors/       — list / create links
#   GET/PUT/PATCH/DELETE /api/v2/inventory/product-vendors/{id}/
#
#   GET/POST /api/v2/inventory/stock-movements/       — list history / record movement
#   GET      /api/v2/inventory/stock-movements/{id}/  — retrieve single record
#   (PUT / PATCH / DELETE intentionally excluded — movements are append-only)
#
#   GET/POST /api/v2/inventory/purchases/             — list / create purchases
#   GET/PUT/PATCH/DELETE /api/v2/inventory/purchases/{id}/
#   POST     /api/v2/inventory/purchases/{id}/confirm/ — confirm and apply stock IN
#
#   GET/POST /api/v2/inventory/purchase-items/        — manage individual line items
#   GET/PUT/PATCH/DELETE /api/v2/inventory/purchase-items/{id}/

urlpatterns = router.urls + [
    path('reports/stock/', InventoryStockReportView.as_view(), name='inventory-stock-report'),
    path('reports/cost/',  ProductCostReportView.as_view(),   name='product-cost-report'),
]
