"""
Жоба баптаулары.

Құпия мәндер (SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASE_URL) `.env` файлынан алынады.
Үлгісі — `.env.example`.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# .env файлын оқу (файл болмаса — қате емес, әдепкі мәндер қолданылады)
load_dotenv(BASE_DIR / ".env")

DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Тек жергілікті әзірлеуге арналған кілт
        SECRET_KEY = "django-insecure-local-development-only"
    else:
        raise ImproperlyConfigured("SECRET_KEY .env файлында көрсетілуі керек.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Жобаның өз қосымшалары
    "apps.accounts",
    "apps.quiz",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Тілді cookie-ден (немесе браузерден) анықтайды
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
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
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Деректер қоры: DATABASE_URL берілсе — PostgreSQL, әйтпесе жергілікті SQLite
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {
    "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600),
}


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Тілдер: негізгі тіл — қазақша, екінші — орысша
LANGUAGE_CODE = "kk"
LANGUAGES = [
    ("kk", _("Қазақша")),
    ("ru", _("Орысша")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True

# Таңдалған тіл cookie-де бір жыл сақталады
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365

TIME_ZONE = "Asia/Almaty"
USE_TZ = True


# Статика (CSS, JS) және жүктелген суреттер
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
