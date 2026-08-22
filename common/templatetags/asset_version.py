import os

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def asset_version(relative_path):
    """mtime-based cache-buster for a static/ file, usable directly from any
    template (not just views that build their own context — e.g. base.html,
    which every admin page renders through Django's own machinery).

    {% asset_version 'admin/js/custom_admin.js' %} -> an int, or 0 if the
    file can't be found. Mirrors the per-app Python _asset_version() helpers
    (contacts/admin.py, employees/admin.py, surgeries/admin.py, etc.) —
    those exist for views that already build their own extra_context;
    this covers the site-wide files loaded straight from base.html.
    """
    path = os.path.join(settings.BASE_DIR, 'static', *relative_path.split('/'))
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0
