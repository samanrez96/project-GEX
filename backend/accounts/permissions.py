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

__all__ = [
    'ADMIN',
    'FINANCE_USER',
    'INVENTORY_USER',
    'EMPLOYEE_MANAGER',
    'IsAdminRole',
    'IsFinanceUser',
    'IsInventoryUser',
    'IsEmployeeManager',
    'IsAdminOrFinanceUser',
    'IsAdminOrInventoryUser',
    'IsAdminOrEmployeeManager',
    'IsMainAdministrator',
    'user_has_role',
    'is_main_administrator',
]

# ---------------------------------------------------------------------------
# Role name constants
# ---------------------------------------------------------------------------
ADMIN = "admin"
FINANCE_USER = "finance_user"
INVENTORY_USER = "inventory_user"
EMPLOYEE_MANAGER = "employee_manager"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def user_has_role(user, role_name: str) -> bool:
    """Return True if the authenticated user belongs to the named group."""
    return user.is_authenticated and user.groups.filter(name=role_name).exists()


def is_main_administrator(user) -> bool:
    """Centralised check for the main administrator (superuser)."""
    return bool(user and getattr(user, 'is_authenticated', False) and user.is_superuser)


# ---------------------------------------------------------------------------
# Permission classes
# ---------------------------------------------------------------------------

class IsAdminRole(BasePermission):
    message = "You must be an administrator to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN)


class IsFinanceUser(BasePermission):
    message = "You must be a finance user to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, FINANCE_USER)


class IsInventoryUser(BasePermission):
    message = "You must be an inventory user to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, INVENTORY_USER)


class IsEmployeeManager(BasePermission):
    message = "You must be an employee manager to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, EMPLOYEE_MANAGER)


class IsAdminOrFinanceUser(BasePermission):
    message = "Access restricted to admin or finance users."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN) or user_has_role(request.user, FINANCE_USER)


class IsAdminOrInventoryUser(BasePermission):
    message = "Access restricted to admin or inventory users."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN) or user_has_role(request.user, INVENTORY_USER)


class IsAdminOrEmployeeManager(BasePermission):
    message = "Access restricted to admin or employee managers."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return user_has_role(request.user, ADMIN) or user_has_role(request.user, EMPLOYEE_MANAGER)


class IsMainAdministrator(BasePermission):
    message = "فقط مدیر اصلی سامانه مجاز به انجام این عملیات است."

    def has_permission(self, request, view):
        return is_main_administrator(request.user)