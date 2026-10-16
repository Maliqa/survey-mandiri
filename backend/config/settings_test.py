"""Test settings: sqlite (or DATABASE_URL in CI), eager Celery, temp media."""
import os
import tempfile

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DJANGO_DEBUG", "0")
os.environ.setdefault("DJANGO_SECURE_SSL_REDIRECT", "0")

from .settings import *  # noqa: E402,F401,F403

CELERY_TASK_ALWAYS_EAGER = True
MEDIA_ROOT = tempfile.mkdtemp(prefix="sm-test-media-")
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"auth": "1000/min", "upload": "1000/min"}}  # noqa: F405
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}  # noqa: F405
