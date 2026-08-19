"""Shared image-upload validation and safe upload_to path generation.

Used by any model ImageField that must verify uploaded content is a real,
supported image — not just checked by filename extension or the browser
-supplied MIME type. Currently: Doctor.medical_certificate_image and
Doctor.national_card_image.

One validation function is reused by the model field's ``validators``
(which DRF's ModelSerializer automatically inherits for its auto-generated
serializer field) and by the custom admin form field (see contacts/forms.py)
so there is exactly one place that decides what counts as a valid image.
"""
import datetime
import uuid

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB

# Decoded-format whitelist (Pillow's Image.format after actually opening the
# file) — deliberately narrower than "whatever Pillow can open".
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
_FORMAT_TO_EXTENSION = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
ALLOWED_UPLOAD_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

OVERSIZE_MESSAGE = 'حجم فایل نباید بیشتر از ۵ مگابایت باشد.'
INVALID_IMAGE_MESSAGE = 'فایل انتخاب‌شده یک تصویر معتبر نیست.'
UNSUPPORTED_FORMAT_MESSAGE = 'فرمت تصویر باید JPG، JPEG، PNG یا WEBP باشد.'

# Exceptions Pillow raises for content that isn't decodable as a real image.
# DecompressionBombError is a plain Exception subclass (not OSError), so it
# needs its own branch even though the handling is identical.
_UNREADABLE_IMAGE_EXCEPTIONS = (UnidentifiedImageError, OSError, ValueError, SyntaxError, IndexError, TypeError)


def _decoded_format(file):
    """Return the Pillow-decoded format name for `file`, or raise a
    ValidationError with a controlled Persian message.

    Opens the file twice: once for `verify()` (structural check — Pillow's
    own docs say the Image object is unusable for anything else afterwards),
    and once more to fully `load()` the pixel data, which catches truncated
    files that verify() alone can miss. Never lets a raw Pillow exception
    escape to the caller.
    """
    try:
        file.seek(0)
        with Image.open(file) as probe:
            probe.verify()

        file.seek(0)
        with Image.open(file) as decoded:
            fmt = decoded.format
            decoded.load()
        return fmt
    except Image.DecompressionBombError:
        raise ValidationError(INVALID_IMAGE_MESSAGE, code='invalid_image')
    except _UNREADABLE_IMAGE_EXCEPTIONS:
        raise ValidationError(INVALID_IMAGE_MESSAGE, code='invalid_image')
    finally:
        file.seek(0)


def validate_image_upload(file):
    """Validate an uploaded image: size limit, then real decoded content
    against the JPEG/PNG/WEBP whitelist. Raises django.core.exceptions
    .ValidationError with a Persian message; never raises a raw Pillow
    exception. Resets the file pointer to 0 before returning."""
    if file is None:
        return
    if file.size > MAX_IMAGE_UPLOAD_SIZE:
        raise ValidationError(OVERSIZE_MESSAGE, code='file_too_large')

    fmt = _decoded_format(file)
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(UNSUPPORTED_FORMAT_MESSAGE, code='unsupported_format')


def _build_upload_path(subdir, filename):
    """doctors/<subdir>/<year>/<month>/<uuid>.<ext> — never uses the Doctor's
    pk (not yet assigned on first save), name, national id, phone number, or
    the raw uploaded filename beyond a whitelisted extension. By the time
    this runs (Model.save(), during FileField.pre_save()), the content has
    already passed validate_image_upload() via form/serializer validation,
    so deriving the extension from the original filename here is purely
    cosmetic, not a security decision.
    """
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        ext = 'jpg'
    today = datetime.date.today()
    return f'doctors/{subdir}/{today.year}/{today.month:02d}/{uuid.uuid4().hex}.{ext}'


def doctor_medical_certificate_upload_path(instance, filename):
    """upload_to for Doctor.medical_certificate_image — a stable, importable
    module-level function (not a closure) so Django can serialize it into
    migrations."""
    return _build_upload_path('medical-certificates', filename)


def doctor_national_card_upload_path(instance, filename):
    """upload_to for Doctor.national_card_image — logically separate path
    from the medical certificate (also guarantees the two fields can never
    collide on the same storage name, since the subdir differs)."""
    return _build_upload_path('national-cards', filename)


def _build_employee_upload_path(subdir, filename):
    """employees/<subdir>/<year>/<month>/<uuid>.<ext> — mirrors
    _build_upload_path but under a separate 'employees/' root so employee
    and doctor uploads can never collide on the same storage path."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        ext = 'jpg'
    today = datetime.date.today()
    return f'employees/{subdir}/{today.year}/{today.month:02d}/{uuid.uuid4().hex}.{ext}'


def employee_credential_image_1_upload_path(instance, filename):
    """upload_to referenced by employees/migrations/0005 (legacy fixed
    credential_image_1 field, removed from the model by migration 0008).
    Kept importable so that historical migration keeps working when
    replayed from scratch — not used by any current model field."""
    return _build_employee_upload_path('credential-1', filename)


def employee_credential_image_2_upload_path(instance, filename):
    """upload_to referenced by employees/migrations/0005 (legacy fixed
    credential_image_2 field, since removed). Kept importable for the same
    reason as employee_credential_image_1_upload_path above."""
    return _build_employee_upload_path('credential-2', filename)


def employee_document_upload_path(instance, filename):
    """upload_to for EmployeeDocument.file — the canonical repeatable
    document model that superseded the two fixed credential_image fields."""
    return _build_employee_upload_path('documents', filename)
