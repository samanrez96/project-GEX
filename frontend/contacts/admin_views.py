import json
import mimetypes

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from contacts.models import Doctor, DoctorSpecialty

_PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def _fa_digits(n):
    return str(n).translate(_PERSIAN_DIGITS)


def _json_body(request):
    """Parse a JSON request body. Missing/empty/invalid body -> {}.

    All Specialty utility endpoints use application/json consistently
    (see static/admin/js/doctor_specialty.js) instead of mixing form-encoded
    and JSON bodies across requests.
    """
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _permission_denied_response():
    """403 JSON for a Specialty AJAX endpoint — never Django's default HTML
    permission_denied page, which fetch()'s res.json() can't parse."""
    return JsonResponse({
        'success': False,
        'code': 'permission_denied',
        'message': 'شما اجازه انجام این عملیات را ندارید.',
    }, status=403)


@staff_member_required
def doctorcontact_changelist_redirect(request):
    """Compat redirect for the pre-rename DoctorContact admin changelist URL."""
    return HttpResponseRedirect(reverse('admin:contacts_doctor_changelist'))


@staff_member_required
def doctorcontact_change_redirect(request, pk):
    """Compat redirect for the pre-rename DoctorContact admin change URL. Preserves the id."""
    get_object_or_404(Doctor, pk=pk)
    return HttpResponseRedirect(reverse('admin:contacts_doctor_change', args=[pk]))


@staff_member_required
@require_POST
def doctor_specialty_create_view(request):
    """Create a DoctorSpecialty from the Doctor add/edit form's inline modal."""
    if not request.user.has_perm('contacts.add_doctorspecialty'):
        return _permission_denied_response()

    payload = _json_body(request)
    name = ' '.join(str(payload.get('name', '')).split())
    if not name:
        return JsonResponse({
            'success': False,
            'code': 'empty_name',
            'message': 'عنوان تخصص نمی‌تواند خالی باشد.',
        }, status=400)

    try:
        specialty = DoctorSpecialty.objects.create(name=name)
    except IntegrityError:
        return JsonResponse({
            'success': False,
            'code': 'duplicate_name',
            'message': 'این تخصص قبلاً ثبت شده است.',
        }, status=400)

    return JsonResponse({
        'success': True,
        'id': specialty.id,
        'name': specialty.name,
        'message': 'تخصص با موفقیت اضافه شد.',
    })


@staff_member_required
@require_POST
def doctor_specialty_delete_view(request, pk):
    """Hard-delete a DoctorSpecialty from the Doctor form, only if unused.

    If the specialty is in use, this does NOT delete it — it reports the
    usage count so the form can offer to deactivate it instead (see
    doctor_specialty_deactivate_view).
    """
    if not request.user.has_perm('contacts.delete_doctorspecialty'):
        return _permission_denied_response()

    specialty = get_object_or_404(DoctorSpecialty, pk=pk)
    doctor_count = specialty.doctors.count()

    if doctor_count:
        return JsonResponse({
            'success': False,
            'code': 'specialty_in_use',
            'doctor_count': doctor_count,
            'message': f'این تخصص برای {_fa_digits(doctor_count)} پزشک ثبت شده است و قابل حذف نیست.',
        }, status=400)

    try:
        specialty.delete()
    except ProtectedError:
        return JsonResponse({
            'success': False,
            'code': 'specialty_in_use',
            'doctor_count': specialty.doctors.count(),
            'message': 'این تخصص برای یک یا چند پزشک ثبت شده است و قابل حذف نیست.',
        }, status=400)

    return JsonResponse({'success': True, 'message': 'تخصص با موفقیت حذف شد.'})


@staff_member_required
@require_POST
def doctor_specialty_deactivate_view(request, pk):
    """Safely deactivate a DoctorSpecialty that is currently in use.

    Never touches Doctor.specialty, never deletes the row — just flips
    is_active so it stops being offered for new assignments while every
    existing Doctor keeps its current (now-inactive) specialty.
    """
    if not request.user.has_perm('contacts.delete_doctorspecialty'):
        return _permission_denied_response()

    specialty = get_object_or_404(DoctorSpecialty, pk=pk)
    doctor_count = specialty.doctors.count()

    specialty.is_active = False
    specialty.save(update_fields=['is_active'])

    return JsonResponse({
        'success': True,
        'doctor_count': doctor_count,
        'message': 'تخصص با موفقیت غیرفعال شد.',
    })


@staff_member_required
@require_POST
def doctor_specialty_activate_view(request, pk):
    """Reactivate a previously-deactivated DoctorSpecialty.

    Makes it selectable for new Doctor assignments again. Never touches
    any Doctor row.
    """
    if not request.user.has_perm('contacts.change_doctorspecialty'):
        return _permission_denied_response()

    specialty = get_object_or_404(DoctorSpecialty, pk=pk)
    specialty.is_active = True
    specialty.save(update_fields=['is_active'])

    return JsonResponse({
        'success': True,
        'message': 'تخصص با موفقیت فعال شد.',
    })


# ---------------------------------------------------------------------------
# Protected Doctor document endpoints — medical certificate / national card.
#
# These are the ONLY way the two document images are ever served. MEDIA_URL
# is not wired into the URLconf anywhere in this project (confirmed by
# inspection), so there is no competing public path to these files — access
# is authenticated + permission-checked here, not just hidden by a missing
# public route.
# ---------------------------------------------------------------------------

def _serve_doctor_document(request, pk, field_name):
    if not request.user.has_perm('contacts.view_doctor'):
        raise PermissionDenied

    doctor = get_object_or_404(Doctor, pk=pk)
    field_file = getattr(doctor, field_name)
    if not field_file or not field_file.name:
        raise Http404('مدرکی برای این پزشک ثبت نشده است.')

    try:
        handle = field_file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('فایل مربوطه در سرور یافت نشد.')

    content_type = mimetypes.guess_type(field_file.name)[0] or 'application/octet-stream'
    response = FileResponse(handle, content_type=content_type)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline'
    return response


@staff_member_required
def doctor_medical_certificate_view(request, pk):
    return _serve_doctor_document(request, pk, 'medical_certificate_image')


@staff_member_required
def doctor_national_card_view(request, pk):
    return _serve_doctor_document(request, pk, 'national_card_image')
