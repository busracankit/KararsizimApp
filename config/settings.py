"""Django settings for the Kararsızım project.

All environment-specific values are read from environment variables
(a local `.env` file is loaded via python-dotenv).
"""
import os
import warnings
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is False.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "polls",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "polls.middleware.VoterCookieMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: Supabase Postgres when DATABASE_URL is set, otherwise local SQLite.
if os.environ.get("DATABASE_URL"):
    try:
        DATABASES = {"default": dj_database_url.config(conn_max_age=0, ssl_require=True)}
    except ValueError as error:
        # Never echo the URL itself: it contains the database password.
        raise ImproperlyConfigured(
            "DATABASE_URL geçersiz. Kontrol et: parolanın etrafında [ ] kalmamalı, adres tırnak içinde "
            "olmamalı, parolada @ : / ? # % [ ] gibi karakterler varsa URL-kodlanmalı (ör. @ -> %40)."
        ) from error
    # Required for Supabase's transaction pooler (PgBouncer, port 6543).
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

# Site login uses email + password; ModelBackend keeps username login for /admin/.
AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "/giris/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Locally WhiteNoise serves files straight from static/ (no collectstatic needed).
# On Vercel, collectstatic runs automatically at build time and /static/ is served by the CDN.
WHITENOISE_USE_FINDERS = True
# STATIC_ROOT only exists after collectstatic; silence WhiteNoise's warning when it's missing.
warnings.filterwarnings("ignore", message="No directory at", category=UserWarning)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Abuse protection: scope -> (max attempts, window in seconds, "ip" | "user").
RATE_LIMITS = {
    "vote": (60, 10 * 60, "ip"),
    "poll_create": (5, 60 * 60, "user"),
    "comment": (10, 10 * 60, "user"),
    "report": (10, 60 * 60, "ip"),
    "login": (10, 15 * 60, "ip"),
    "register": (5, 60 * 60, "ip"),
    "password_reset": (5, 60 * 60, "ip"),
    "upload": (20, 60 * 60, "user"),
}

# --- Production (DEBUG=False, e.g. on Vercel) -------------------------------
if not DEBUG:
    # Vercel terminates HTTPS and forwards the original scheme in this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    # *.vercel.app already sends HSTS; set SECURE_HSTS_SECONDS when a custom domain is added.
    SILENCED_SYSTEM_CHECKS = ["security.W004"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

# Send errors to stderr so they show up in Vercel's runtime logs.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO" if DEBUG else "WARNING", "propagate": False},
    },
}
