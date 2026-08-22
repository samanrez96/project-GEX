"""The project's single custom AdminSite.

Set once, project-wide, via ClinicAdminConfig.default_site (see common/apps.py
and its entry in config/settings/base.py's INSTALLED_APPS) — NOT by any app
reassigning `admin.site = SomeAdminSite()` later. That per-app-reassignment
pattern is unsafe: `@admin.register(Model)` (no explicit `site=` kwarg)
always resolves `django.contrib.admin.sites.site` fresh at decoration time
(see django.contrib.admin.decorators.register), which is Django's own
singleton — a later app doing `admin.site = SomeOtherSite()` only rebinds
the `django.contrib.admin` package's alias, not that singleton, so every
`@admin.register(...)` call across the whole project still lands on the
*original* site while the URLconf ends up serving whichever reassigned
instance came last — an instance with an empty registry. Routing through
AdminConfig.default_site instead means Django constructs this ONE instance
before any app's admin.py runs, so every registration correctly lands here
from the start.

Apps contribute their own extra URL patterns / admin-index rewrites via
register_extra_urls() / register_app_list_hook() below, called at admin.py
import time — this replaces the project's previous
admin.site.__class__.get_urls / get_app_list monkey-patch chain (which
mutated the base AdminSite *class* itself, affecting every AdminSite
instance anywhere) with the same net effect through ordinary instance
methods on one deliberately-chosen site.
"""

from django.contrib import admin


class ClinicAdminSite(admin.AdminSite):
    _extra_url_providers = []
    _app_list_hooks = []

    def get_urls(self):
        urls = super().get_urls()
        extra = []
        for provider in self._extra_url_providers:
            extra.extend(provider(self))
        return extra + urls

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label=app_label)
        for hook in self._app_list_hooks:
            app_list = hook(self, request, app_list, app_label)
        return app_list


def register_extra_urls(provider):
    """Register a callable ``provider(site) -> list[URLPattern]``, invoked
    on every ``get_urls()`` call. Call this at admin.py import time, e.g.::

        def _finance_extra_urls(site):
            return [
                path('finance/dashboard/', site.admin_view(finance_dashboard_view), name='finance_dashboard'),
            ]

        register_extra_urls(_finance_extra_urls)
    """
    ClinicAdminSite._extra_url_providers.append(provider)


def register_app_list_hook(hook):
    """Register a callable ``hook(site, request, app_list, app_label) ->
    app_list``, invoked on every ``get_app_list()`` call, in registration
    order — each hook receives the previous hook's output."""
    ClinicAdminSite._app_list_hooks.append(hook)
