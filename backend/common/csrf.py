from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure


def csrf_failure(request, reason=""):
    """CSRF_FAILURE_VIEW: JSON for AJAX/fetch callers, Django's default
    HTML page for everything else (normal admin form POSTs).

    Widgets like static/admin/js/doctor_specialty.js and
    anesthesia_type.js always parse the response as JSON — Django's default
    csrf_failure() returns an HTML page, which fetch()'s res.json() can't
    parse, surfacing as a generic connection error instead of the real
    "session expired" message.
    """
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
    )
    if is_ajax:
        return JsonResponse({
            'success': False,
            'code': 'csrf_failed',
            'message': 'نشست شما منقضی شده است. صفحه را تازه‌سازی کنید.',
        }, status=403)
    return django_csrf_failure(request, reason=reason)
