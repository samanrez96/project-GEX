from rest_framework.routers import DefaultRouter

from employees.views import EmployeePurchaseCommissionViewSet, EmployeeViewSet, JobPositionViewSet

app_name = "employees"

router = DefaultRouter()
router.register("positions",            JobPositionViewSet,               basename="position")
router.register("purchase-commissions", EmployeePurchaseCommissionViewSet, basename="purchase-commission")
router.register("",                     EmployeeViewSet,                  basename="employee")

# Registered routes:
#   /api/v2/employees/positions/                — job positions CRUD
#   /api/v2/employees/purchase-commissions/     — employee purchase commissions CRUD
#   /api/v2/employees/{id}/                     — employees CRUD

urlpatterns = router.urls
