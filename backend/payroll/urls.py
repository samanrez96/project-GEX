from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CommissionRuleViewSet,
    CommissionTransactionViewSet,
    EmployeeCostReportView,
    HourlyRateViewSet,
    HourlyWorkEntryViewSet,
    MonthlyWageViewSet,
    PayrollPeriodViewSet,
    PayrollReportView,
    PayrollTypeConfigViewSet,
)

app_name = 'payroll'

router = DefaultRouter()
router.register('periods',                 PayrollPeriodViewSet,         basename='period')
router.register('configs',                 PayrollTypeConfigViewSet,      basename='config')
router.register('wages',                   MonthlyWageViewSet,            basename='wage')
router.register('hourly-rates',            HourlyRateViewSet,             basename='hourly-rate')
router.register('hourly-work-entries',     HourlyWorkEntryViewSet,        basename='hourly-work-entry')
router.register('commission-rules',        CommissionRuleViewSet,         basename='commission-rule')
router.register('commission-transactions', CommissionTransactionViewSet,  basename='commission-transaction')

# Registered routes:
#   GET/POST   /api/v1/payroll/periods/            — list / create periods
#   GET/PATCH  /api/v1/payroll/periods/{id}/       — retrieve / update period
#   POST       /api/v1/payroll/periods/{id}/close/ — close a period
#
#   GET        /api/v1/payroll/configs/                         — list configs
#   GET/PATCH  /api/v1/payroll/configs/{id}/                   — retrieve / update config
#   GET        /api/v1/payroll/configs/by_employee/?employee={id}

urlpatterns = router.urls + [
    path('report/',                    PayrollReportView.as_view(),         name='payroll-report'),
    path('reports/employee-cost/',     EmployeeCostReportView.as_view(),    name='employee-cost-report'),
]
