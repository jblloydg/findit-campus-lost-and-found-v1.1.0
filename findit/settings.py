"""Settings for local development and a future hosted deployment."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-only-findit-change-before-deployment")
DEBUG = os.getenv("DJANGO_DEBUG", "1").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [host.strip() for host in os.getenv(
    "DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost"
).split(",") if host.strip()]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "captcha",
    "core.apps.CoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.idempotency.IdempotencyMiddleware",
    "core.middleware.StudentIdRequiredMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.FriendlyErrorMiddleware",
]
if not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "findit.urls"
ASGI_APPLICATION = "findit.asgi.application"
WSGI_APPLICATION = "findit.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_context",
            ],
        },
    },
]

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    try:
        import dj_database_url
        DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True)}
    except ImportError as exc:
        raise RuntimeError("Install the production requirements to use DATABASE_URL.") from exc
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # Wait up to 20 s for a lock instead of failing when the website and the
            # timer runner write at the same moment.
            "OPTIONS": {
                "timeout": 20,
                # PERF-002: WAL lets pages be read while chat messages are written, and
                # IMMEDIATE transactions avoid "database is locked" when two programs write.
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
                "transaction_mode": "IMMEDIATE",
            },
        }
    }

# Each web request runs in one transaction: if any database step fails, everything that
# request wrote is rolled back, so records are never left half-saved.
DATABASES["default"]["ATOMIC_REQUESTS"] = True

REDIS_URL = os.getenv("REDIS_URL", "").strip()
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    # Local single-process development only. Set REDIS_URL when hosting or
    # running more than one application process.
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Report attachments: outside MEDIA_ROOT, served only by a permission-checked view.
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True

# Logging: warnings and errors (with tracebacks) go to the console and to a rotating
# file in LOG_DIR. Request bodies and passwords are never logged.
LOG_DIR = Path(os.getenv("FINDIT_LOG_DIR", str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "findit.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
            "encoding": "utf-8",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "WARNING"},
    "loggers": {
        "django.request": {"handlers": ["console", "file"], "level": "ERROR", "propagate": False},
        "findit": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}

# v1.1.1: students sign in with email (or a verified Student ID); staff with a username.
AUTHENTICATION_BACKENDS = ["core.auth.FindItBackend"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "landing"
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# Email: printed to the console locally. Set DJANGO_EMAIL_HOST (and the related variables)
# on the server to send real password-reset emails. Credentials stay in environment variables.
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "").strip()
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "1").lower() in {"1", "true", "yes"}
    EMAIL_TIMEOUT = 15
else:
    # Local PC: emails are printed in the Find-IT window and copied to the Test inbox page.
    EMAIL_BACKEND = "core.mail.ConsoleAndTestInboxBackend"
# Test inbox (each person sees only their own emails). Only on a local, non-hosted site
# without a real mail server; it can never be on while DEBUG is off.
FINDIT_TEST_INBOX = (
    DEBUG and not EMAIL_HOST and os.getenv("FINDIT_TEST_INBOX", "1").lower() in {"1", "true", "yes"}
)
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "Find-IT <no-reply@localhost>")
PASSWORD_RESET_TIMEOUT = 60 * 60  # reset links expire after 1 hour

# Sign-in throttling (core/security.py)
LOGIN_FAILURE_LIMIT = int(os.getenv("FINDIT_LOGIN_FAILURE_LIMIT", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("FINDIT_LOGIN_LOCKOUT_SECONDS", "900"))

if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "findit"}}

# Captcha (django-simple-captcha) for posts with more than 10 photos.
CAPTCHA_CHALLENGE_FUNCT = "core.captcha_challenges.random_challenge"
CAPTCHA_LENGTH = 5
CAPTCHA_TIMEOUT = 10  # minutes
CAPTCHA_IMAGE_SIZE = (150, 50)
CAPTCHA_FONT_SIZE = 30

# Address put inside turn-in QR codes, e.g. http://192.168.1.20:8000 on a campus Wi-Fi demo
# or https://findit.example.edu when hosted. Blank = the address the finder's browser used.
FINDIT_SITE_URL = os.getenv("FINDIT_SITE_URL", "").rstrip("/")

# App version shown at the bottom of every page (CHG-007). Change it ONLY in the VERSION file.
try:
    FINDIT_VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
except OSError:
    FINDIT_VERSION = "unknown"

# Backups (session 4 engine, core/backups.py). Never inside STATIC_ROOT or MEDIA_ROOT.
# FINDIT_BACKUP_RETENTION_DAYS (session 1's name) is accepted as an alias.
BACKUP_DIR = Path(os.getenv("FINDIT_BACKUP_DIR", str(BASE_DIR / "backups")))
BACKUP_KEEP_DAYS = int(os.getenv("FINDIT_BACKUP_KEEP_DAYS", os.getenv("FINDIT_BACKUP_RETENTION_DAYS", "14")))

# Session 1 location field: dormant future feature (campus map segments). While False,
# location is not shown, collected or filtered anywhere.
FINDIT_LOCATION_ENABLED = os.getenv("FINDIT_LOCATION_ENABLED", "0").lower() in {"1", "true", "yes"}

if not DEBUG:
    if SECRET_KEY == "local-only-findit-change-before-deployment":
        raise RuntimeError("Set DJANGO_SECRET_KEY before running outside local development.")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_REFERRER_POLICY = "same-origin"
    # HSTS tells browsers to use HTTPS only. Start small, then raise (e.g. 31536000) once HTTPS works.
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_HSTS_INCLUDE_SUBDOMAINS", "0").lower() in {"1", "true", "yes"}
    SECURE_HSTS_PRELOAD = False
    # Set DJANGO_BEHIND_PROXY=1 only when a trusted proxy (e.g. Nginx, a PaaS router) terminates HTTPS.
    if os.getenv("DJANGO_BEHIND_PROXY", "0").lower() in {"1", "true", "yes"}:
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SSL_REDIRECT", "1").lower() in {"1", "true", "yes"}
    CSRF_TRUSTED_ORIGINS = [
        origin.strip() for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
    ]
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
