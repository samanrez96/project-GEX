"""Kept in its own module (rather than common/apps.py) so Django's
AppConfig auto-detection never sees more than one candidate per module —
importing django.contrib.admin.apps.AdminConfig into common/apps.py's
namespace made Django's scan treat it as a second "default AppConfig"
candidate there, alongside CommonConfig.
"""

from django.contrib.admin.apps import AdminConfig


class ClinicAdminConfig(AdminConfig):
    """Points Django's built-in admin app at ClinicAdminSite instead of the
    stock AdminSite — see common/admin_site.py for why this (Django's own
    documented default_site mechanism) replaces the project's previous
    per-app admin.site.__class__ monkey-patching / admin.site reassignment.
    Used in place of 'django.contrib.admin' in INSTALLED_APPS.
    """
    default_site = 'common.admin_site.ClinicAdminSite'
