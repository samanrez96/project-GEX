from django.contrib import admin
from django.urls import path


def _get_custom_admin_urls():
    """URLهای سفارشی ادمین را برمی‌گرداند."""
    # ایمپورت‌های معوق (deferred) برای جلوگیری از AppRegistryNotReady
    from finance.admin import finance_dashboard_view, finance_transactions_view
    from inventory.admin_views import product_purge_view
    from inventory.admin import product_detail_view, vendor_detail_view
    from misc_expenses.admin import (
        misc_expenses_list_view,
        misc_expenses_add_view,
        misc_expenses_change_view,
        misc_expenses_delete_view,
    )
    from payroll.admin import payroll_page_view
    from surgeries.admin import surgery_history_detail_view
    from surgeries.admin_views import (
        anesthesia_type_create_view,
        anesthesia_type_delete_view,
        anesthesia_type_deactivate_view,
        anesthesia_type_activate_view,
    )
    from contacts.admin_views import (
        doctorcontact_changelist_redirect,
        doctorcontact_change_redirect,
        doctor_specialty_create_view,
        doctor_specialty_delete_view,
        doctor_specialty_deactivate_view,
        doctor_specialty_activate_view,
        doctor_medical_certificate_view,
        doctor_national_card_view,
    )

    return [
        # ---------- Finance ----------
        path(
            "finance/dashboard/",
            admin.site.admin_view(finance_dashboard_view),
            name="finance_dashboard",
        ),
        path(
            "finance/transactions/",
            admin.site.admin_view(finance_transactions_view),
            name="finance_transactions",
        ),
        # ---------- Inventory ----------
        path(
            "inventory/product/<int:product_id>/detail/",
            admin.site.admin_view(product_detail_view),
            name="inventory_product_detail",
        ),
        path(
            "inventory/product/<int:product_id>/purge/",
            admin.site.admin_view(product_purge_view),
            name="inventory_product_purge",
        ),
        path(
            "inventory/vendor/<int:vendor_id>/detail/",
            admin.site.admin_view(vendor_detail_view),
            name="inventory_vendor_detail",
        ),
        # ---------- Misc Expenses ----------
        path(
            "misc-expenses/",
            admin.site.admin_view(misc_expenses_list_view),
            name="misc_expenses_list",
        ),
        path(
            "misc-expenses/add/",
            admin.site.admin_view(misc_expenses_add_view),
            name="misc_expenses_add",
        ),
        path(
            "misc-expenses/<int:pk>/change/",
            admin.site.admin_view(misc_expenses_change_view),
            name="misc_expenses_change",
        ),
        path(
            "misc-expenses/<int:pk>/delete/",
            admin.site.admin_view(misc_expenses_delete_view),
            name="misc_expenses_delete",
        ),
        # ---------- Payroll ----------
        path(
            "payroll/payroll-page/",
            admin.site.admin_view(payroll_page_view),
            name="payroll_page",
        ),
        # ---------- Surgeries ----------
        path(
            "surgeryhistory/<int:surgery_id>/detail/",
            admin.site.admin_view(surgery_history_detail_view),
            name="surgeries_surgeryhistory_detail",
        ),
        path(
            "anesthesia-type/create/",
            admin.site.admin_view(anesthesia_type_create_view),
            name="surgeries_anesthesia_type_create",
        ),
        path(
            "anesthesia-type/<int:pk>/delete/",
            admin.site.admin_view(anesthesia_type_delete_view),
            name="surgeries_anesthesia_type_delete",
        ),
        path(
            "anesthesia-type/<int:pk>/deactivate/",
            admin.site.admin_view(anesthesia_type_deactivate_view),
            name="surgeries_anesthesia_type_deactivate",
        ),
        path(
            "anesthesia-type/<int:pk>/activate/",
            admin.site.admin_view(anesthesia_type_activate_view),
            name="surgeries_anesthesia_type_activate",
        ),
        # ---------- Contacts ----------
        path(
            "contacts/doctorcontact/",
            admin.site.admin_view(doctorcontact_changelist_redirect),
            name="contacts_doctorcontact_changelist_redirect",
        ),
        path(
            "contacts/doctorcontact/<int:pk>/change/",
            admin.site.admin_view(doctorcontact_change_redirect),
            name="contacts_doctorcontact_change_redirect",
        ),
        path(
            "contacts/doctor-specialties/create/",
            admin.site.admin_view(doctor_specialty_create_view),
            name="contacts_doctor_specialty_create",
        ),
        path(
            "contacts/doctor-specialties/<int:pk>/delete/",
            admin.site.admin_view(doctor_specialty_delete_view),
            name="contacts_doctor_specialty_delete",
        ),
        path(
            "contacts/doctor-specialties/<int:pk>/deactivate/",
            admin.site.admin_view(doctor_specialty_deactivate_view),
            name="contacts_doctor_specialty_deactivate",
        ),
        path(
            "contacts/doctor-specialties/<int:pk>/activate/",
            admin.site.admin_view(doctor_specialty_activate_view),
            name="contacts_doctor_specialty_activate",
        ),
        path(
            "contacts/doctor/<int:pk>/documents/medical-certificate/",
            admin.site.admin_view(doctor_medical_certificate_view),
            name="contacts_doctor_medical_certificate",
        ),
        path(
            "contacts/doctor/<int:pk>/documents/national-card/",
            admin.site.admin_view(doctor_national_card_view),
            name="contacts_doctor_national_card",
        ),
    ]


# وصله‌ی متد get_urls در admin.site پیش‌فرض
_original_get_urls = admin.site.get_urls


def _patched_get_urls():
    custom_urls = _get_custom_admin_urls()
    return custom_urls + _original_get_urls()


admin.site.get_urls = _patched_get_urls