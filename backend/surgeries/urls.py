from django.urls import path
from rest_framework.routers import DefaultRouter

from surgeries.views import (
    PatientViewSet,
    SurgeryConsumptionItemViewSet,
    SurgeryHistoryViewSet,
    SurgeryProfitReportView,
    SurgeryTypeViewSet,
    SurgeryUsedItemViewSet,
    SurgeryViewSet,
)

app_name = "surgeries"

router = DefaultRouter()
router.register("patients",          PatientViewSet,               basename="patient")
router.register("surgeries",         SurgeryViewSet,               basename="surgery")
router.register("history",           SurgeryHistoryViewSet,        basename="surgery-history")
router.register("used-items",        SurgeryUsedItemViewSet,       basename="surgery-used-item")
router.register("consumption-items", SurgeryConsumptionItemViewSet, basename="consumption-item")
router.register("types",             SurgeryTypeViewSet,            basename="surgery-type")

# Registered routes:
#   GET/POST             /api/v2/surgeries/surgeries/              — list / create
#   GET/PUT/PATCH/DELETE /api/v2/surgeries/surgeries/{id}/
#   POST                 /api/v2/surgeries/surgeries/{id}/complete/ — apply stock OUT
#
#   GET/POST             /api/v2/surgeries/consumption-items/      — list / add item
#   GET/PUT/PATCH/DELETE /api/v2/surgeries/consumption-items/{id}/
#
#   GET/POST             /api/v2/surgeries/types/                  — list / create surgery types
#   GET/PUT/PATCH/DELETE /api/v2/surgeries/types/{id}/
#
#   GET  /api/v2/surgeries/reports/profit/ — surgery profit report

urlpatterns = router.urls + [
    path('reports/profit/', SurgeryProfitReportView.as_view(), name='surgery-profit-report'),
]
