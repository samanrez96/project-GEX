from .base import *  # noqa: F401, F403

# Override DEBUG explicitly for clarity
DEBUG = True

# In development allow all CORS origins so the front-end dev server can call
# the API without configuring individual origins.
CORS_ALLOW_ALL_ORIGINS = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "surgary_clinic",
        "USER": "postgres",
        "PASSWORD": "yasaman.jd",
        "HOST": "localhost",
        "PORT": "5432",
    }
}