import json

from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from surgeries.models import AnesthesiaType

_PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _fa_digits(n):
    return str(n).translate(_PERSIAN_DIGITS)


def _json_body(request):
    """Parse a JSON request body. Missing/empty/invalid body -> {}."""
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _permission_denied_response():
    """403 JSON for an AnesthesiaType AJAX endpoint — never Django's default
    HTML permission_denied page, which fetch()'s res.json() can't parse."""
    return JsonResponse({
        'success': False,
        'code': 'permission_denied',
        'message': 'شما اجازه انجام این عملیات را ندارید.',
    }, status=403)


# ---------------------------------------------------------------------------
# AnesthesiaType utility endpoints — managed exclusively from the
# SurgeryHistory add/edit form's inline modal (mirrors DoctorSpecialty in
# contacts/admin_views.py). No standalone AnesthesiaType admin page exists.
# ---------------------------------------------------------------------------

@staff_member_required
@require_POST
def anesthesia_type_create_view(request):
    """Create an AnesthesiaType from the SurgeryHistory form's inline modal."""
    if not request.user.has_perm('surgeries.add_anesthesiatype'):
        return _permission_denied_response()

    payload = _json_body(request)
    name = ' '.join(str(payload.get('name', '')).split())
    if not name:
        return JsonResponse({
            'success': False,
            'code': 'empty_name',
            'message': 'نام نوع بیهوشی نمی‌تواند خالی باشد.',
        }, status=400)

    try:
        anesthesia_type = AnesthesiaType.objects.create(name=name)
    except IntegrityError:
        return JsonResponse({
            'success': False,
            'code': 'duplicate_name',
            'message': 'این نوع بیهوشی قبلاً ثبت شده است.',
        }, status=400)

    return JsonResponse({
        'success': True,
        'id': anesthesia_type.id,
        'name': anesthesia_type.name,
        'message': 'نوع بیهوشی با موفقیت اضافه شد.',
    })


@staff_member_required
@require_POST
def anesthesia_type_delete_view(request, pk):
    """Hard-delete an AnesthesiaType from the SurgeryHistory form, only if unused.

    If it is in use, this does NOT delete it — it reports the usage count so
    the form can offer to deactivate it instead (see the deactivate view).
    """
    if not request.user.has_perm('surgeries.delete_anesthesiatype'):
        return _permission_denied_response()

    anesthesia_type = get_object_or_404(AnesthesiaType, pk=pk)
    surgery_count = anesthesia_type.surgery_histories.count()

    if surgery_count:
        return JsonResponse({
            'success': False,
            'code': 'anesthesia_type_in_use',
            'surgery_count': surgery_count,
            'message': f'این نوع بیهوشی برای {_fa_digits(surgery_count)} عمل جراحی ثبت شده است و قابل حذف نیست.',
        }, status=400)

    try:
        anesthesia_type.delete()
    except ProtectedError:
        return JsonResponse({
            'success': False,
            'code': 'anesthesia_type_in_use',
            'surgery_count': anesthesia_type.surgery_histories.count(),
            'message': 'این نوع بیهوشی برای یک یا چند عمل جراحی ثبت شده است و قابل حذف نیست.',
        }, status=400)

    return JsonResponse({'success': True, 'message': 'نوع بیهوشی با موفقیت حذف شد.'})


@staff_member_required
@require_POST
def anesthesia_type_deactivate_view(request, pk):
    """Safely deactivate an AnesthesiaType that is currently in use.

    Never touches SurgeryHistory.anesthesia_type, never deletes the row —
    just flips is_active so it stops being offered for new assignments while
    every existing surgery record keeps its current (now-inactive) type.
    """
    if not request.user.has_perm('surgeries.delete_anesthesiatype'):
        return _permission_denied_response()

    anesthesia_type = get_object_or_404(AnesthesiaType, pk=pk)
    surgery_count = anesthesia_type.surgery_histories.count()

    anesthesia_type.is_active = False
    anesthesia_type.save(update_fields=['is_active'])

    return JsonResponse({
        'success': True,
        'surgery_count': surgery_count,
        'message': 'نوع بیهوشی با موفقیت غیرفعال شد.',
    })


@staff_member_required
@require_POST
def anesthesia_type_activate_view(request, pk):
    """Reactivate a previously-deactivated AnesthesiaType.

    Makes it selectable for new SurgeryHistory assignments again. Never
    touches any SurgeryHistory row.
    """
    if not request.user.has_perm('surgeries.change_anesthesiatype'):
        return _permission_denied_response()

    anesthesia_type = get_object_or_404(AnesthesiaType, pk=pk)
    anesthesia_type.is_active = True
    anesthesia_type.save(update_fields=['is_active'])

    return JsonResponse({
        'success': True,
        'message': 'نوع بیهوشی با موفقیت فعال شد.',
    })
