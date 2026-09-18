from django.contrib import admin
from django.urls import path, include

import config.admin 

urlpatterns = [
    path("admin/", admin.site.urls),  

    path("api/v2/auth/", include("accounts.urls")),
    path("api/v2/inventory/", include("inventory.urls")),
    path("api/v2/employees/", include("employees.urls")),
    path("api/v2/finance/", include("finance.urls")),
    path("api/v2/surgeries/", include("surgeries.urls")),
    path("api/v2/payroll/", include("payroll.urls")),
    path("api/v2/contacts/", include("contacts.urls")),
]