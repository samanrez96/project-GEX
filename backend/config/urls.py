"""
Root URL configuration for the surgery-clinic project.

All API routes are versioned under /api/v1/.
Each business domain is delegated to its own app-level urls.py.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentication (JWT login, refresh, logout, me)
    path("api/v1/auth/", include("accounts.urls")),

    path("api/v1/inventory/", include("inventory.urls")),
    path("api/v1/employees/", include("employees.urls")),
    path("api/v1/finance/", include("finance.urls")),
    path("api/v1/surgeries/", include("surgeries.urls")),
    path("api/v1/payroll/",   include("payroll.urls")),
    path("api/v1/contacts/", include("contacts.urls")),
]
