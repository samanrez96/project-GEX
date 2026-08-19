from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['username']

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


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'permission_count']
    search_fields = ['name']
    ordering = ['name']
    filter_horizontal = ['permissions']
    fieldsets = (
        ('گروه کاربری', {
            'fields': ('name', 'permissions'),
        }),
    )

    @admin.display(description='تعداد دسترسی‌ها')
    def permission_count(self, obj):
        return obj.permissions.count()