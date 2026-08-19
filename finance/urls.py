from django.urls import path
from rest_framework.routers import DefaultRouter

from finance.views import (
    BalanceReportView,
    FinanceCategoryViewSet,
    FinanceTrendView,
    TransactionViewSet,
)

app_name = 'finance'

router = DefaultRouter()
router.register('categories', FinanceCategoryViewSet, basename='finance-category')
router.register('transactions', TransactionViewSet, basename='transaction')

urlpatterns = router.urls + [
    path('reports/balance/', BalanceReportView.as_view(), name='balance-report'),
    path('reports/trend/', FinanceTrendView.as_view(), name='finance-trend'),
]