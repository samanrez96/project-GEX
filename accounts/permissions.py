"""
Reusable role-based permission classes for the surgery-clinic API.

Usage in any view:
    from accounts.permissions import IsAdminOrFinanceUser

    class MyView(APIView):
        permission_classes = [IsAdminOrFinanceUser]

Role hierarchy:
    - Superusers bypass all role checks.
    - admin group has access to everything.
    - Finance data  → admin | finance_user
    - Inventory data → admin | inventory_user
    - Employee data  → admin | employee_manager
"""

from rest_framework.permissions import BasePermission

# ---------------------------------------------------------------------------
# Role name constants — use these everywhere to avoid string typos
# ---------------------------------------------------------------------------
ADMIN = "admin"
FINANCE_USER = "finance_user"
INVENTORY_USER = "inventory_user"
EMPLOYEE_MANAGER = "employee_manager"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def user_has_role(user, role_name: str) -> bool:
    """Return True if the authenticated user belongs to the named group."""
    return user.is_authenticated and user.groups.filter(name=role_name).exists()


def is_main_administrator(user) -> bool:
    """The single source of truth for "main administrator" status.

    Currently Django's own ``is_superuser`` flag — the project has no more
    explicit root-admin role (the ``admin`` group above is a broad business
    role for finance/inventory/employee data, not equivalent to "the main
    system administrator" for sensitive privacy features like hidden
    Patients). Centralized here so every sensitive-visibility check enforces
    the same rule; do not duplicate a raw ``user.is_superuser`` check
    elsewhere — import and call this instead.
    """
    return bool(user and getattr(user, 'is_authenticated', False) and user.is_superuser)


# ---------------------------------------------------------------------------
# Single-role permission classes
# ---------------------------------------------------------------------------

class IsAdminRole(BasePermission):
    """Grants access only to users in the 'admin' group (or superusers)."""

    message = "You must be an administrator to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN)


class IsFinanceUser(BasePermission):
    """Grants access only to users in the 'finance_user' group (or superusers)."""

    message = "You must be a finance user to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, FINANCE_USER)


class IsInventoryUser(BasePermission):
    """Grants access only to users in the 'inventory_user' group (or superusers)."""

    message = "You must be an inventory user to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, INVENTORY_USER)


class IsEmployeeManager(BasePermission):
    """Grants access only to users in the 'employee_manager' group (or superusers)."""

    message = "You must be an employee manager to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, EMPLOYEE_MANAGER)


# ---------------------------------------------------------------------------
# Combined permission classes (admin always included)
# ---------------------------------------------------------------------------

class IsAdminOrFinanceUser(BasePermission):
    """
    Grants access to:
        - Superusers
        - Users in the 'admin' group
        - Users in the 'finance_user' group

    Use this on all finance/payroll-related views.
    """

    message = "Access restricted to admin or finance users."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN) or user_has_role(request.user, FINANCE_USER)


class IsAdminOrInventoryUser(BasePermission):
    """
    Grants access to:
        - Superusers
        - Users in the 'admin' group
        - Users in the 'inventory_user' group

    Use this on all inventory-related views.
    """

    message = "Access restricted to admin or inventory users."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN) or user_has_role(request.user, INVENTORY_USER)


class IsMainAdministrator(BasePermission):
    """Grants access only to the main administrator (is_superuser).

    Stricter than every other class in this module — the broad 'admin'
    business role does NOT bypass this the way it bypasses IsAdminRole and
    friends. Reserved for irreversible, destructive operations (e.g. the
    Product purge endpoints) where ordinary admin staff must not have
    access. Backed by is_main_administrator() so the rule lives in one
    place.
    """

    message = "فقط مدیر اصلی سامانه مجاز به انجام این عملیات است."

    def has_permission(self, request, view):
        return is_main_administrator(request.user)


class IsAdminOrEmployeeManager(BasePermission):
    """
    Grants access to:
        - Superusers
        - Users in the 'admin' group
        - Users in the 'employee_manager' group

    Use this on all employee-related views.
    """

    message = "Access restricted to admin or employee managers."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN) or user_has_role(request.user, EMPLOYEE_MANAGER)
