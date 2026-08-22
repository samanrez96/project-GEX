from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User


# Unregister the default Django auth admin registrations so we can re-register
# with Persian-labelled fieldsets.
admin.site.unregister(User)


# ---------------------------------------------------------------------------
# Custom UserAdmin — Persian labels, RTL-friendly fieldsets
# ---------------------------------------------------------------------------

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Django's built-in UserAdmin with Persian verbose names.

    Inherits all default Django user management behavior:
    password hashing, permission assignment, group membership.
    Only user-facing labels are Persianised.
    """

    list_display  = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']
    list_filter   = ['is_staff', 'is_superuser', 'is_active', 'groups']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering      = ['username']

    fieldsets = (
        ('اطلاعات ورود', {
            'fields': ('username', 'password'),
        }),
        ('اطلاعات شخصی', {
            'fields': ('first_name', 'last_name', 'email'),
        }),
        ('دسترسی‌ها', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('تاریخ‌های مهم', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',),
        }),
    )

    add_fieldsets = (
        ('ایجاد کاربر جدید', {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'is_staff', 'is_active'),
        }),
    )


# Group admin — keep default but register explicitly for visibility
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display  = ['name']
    search_fields = ['name']
    ordering      = ['name']
    filter_horizontal = ['permissions']
    fieldsets = (
        ('گروه کاربری', {
            'fields': ('name', 'permissions'),
        }),
    )
