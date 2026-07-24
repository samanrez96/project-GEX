from .base import *  # noqa: F401, F403

DEBUG = False

# -----------------------------------------------------------------------
# Hosts / CORS / CSRF
# -----------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[],
)

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[],
)

# -----------------------------------------------------------------------
# Security hardening
# -----------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

# Secure/CSRF cookie flags are only meaningful over HTTPS — a browser
# silently refuses to store or send a Secure cookie over plain HTTP, which
# breaks session auth and CSRF validation entirely on an IP/HTTP-only
# deployment. Gated on the same flag as SECURE_SSL_REDIRECT so both flip on
# together once real HTTPS (domain + cert) is in front of this deployment.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)

SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
# Must stay readable by JS: the Doctor Specialty / Anesthesia Type modal
# widgets (static/admin/js/doctor_specialty.js, anesthesia_type.js) read this
# cookie via document.cookie and send it back as the X-CSRFToken header —
# Django's own documented AJAX CSRF pattern. HttpOnly here would silently
# blank that header on every request, failing CSRF for those endpoints only
# (normal admin form POSTs still work since they use the server-rendered
# hidden {% csrf_token %} field, not this cookie).
CSRF_COOKIE_HTTPONLY = False

X_FRAME_OPTIONS = "DENY"

# Needed when Django is behind Nginx/SSL reverse proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True