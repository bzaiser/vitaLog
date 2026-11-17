"""
Django settings for config project.
"""

import importlib.util
import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-7mlsq0st)28=_g5k(tz#$=&$y3b^&xf)khp46r!i6p%b32uxl1",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "design_studio",
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if importlib.util.find_spec("whitenoise") is not None:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "design_studio.context_processors.theme_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def _database_from_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme in ("postgres", "postgresql"):
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
        }
    if parsed.scheme == "sqlite":
        db_path = parsed.path
        if db_path.startswith("/") and not db_path.startswith("//"):
            db_path = db_path.lstrip("/")
            return {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / db_path,
            }
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_path.lstrip("/") if os.name == "nt" else db_path,
        }
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATABASES = {
    "default": _database_from_url(DATABASE_URL)
    if DATABASE_URL
    else {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "tracker:login"
LOGIN_REDIRECT_URL = "tracker:dashboard"
LOGOUT_REDIRECT_URL = "tracker:login"

# Design Studio Konfiguration
DESIGN_STUDIO_APP_NAME = "Kalorien & Gewicht"
DESIGN_STUDIO_MENU_ITEMS = [
    {
        "id": "dashboard",
        "url_name": "tracker:dashboard",
        "match_urls": ["dashboard"],
        "default_label": "Dashboard",
        "icon": "bi-speedometer2",
        "zone": "main",
        "display": "icon_text",
        "order": 1,
    },
    {
        "id": "meals",
        "url_name": "tracker:meals_list",
        "match_urls": ["meals_list"],
        "default_label": "Mahlzeiten",
        "icon": "bi-egg-fried",
        "zone": "main",
        "display": "icon_text",
        "order": 2,
    },
    {
        "id": "meal_templates",
        "url_name": "tracker:meal_templates_list",
        "match_urls": ["meal_templates_list"],
        "default_label": "Vorlagen",
        "icon": "bi-bookmark-star",
        "zone": "main",
        "display": "icon_text",
        "order": 3,
    },
    {
        "id": "weights",
        "url_name": "tracker:weights_list",
        "match_urls": ["weights_list"],
        "default_label": "Gewicht",
        "icon": "bi-activity",
        "zone": "main",
        "display": "icon_text",
        "order": 4,
    },
    {
        "id": "water",
        "url_name": "tracker:water_list",
        "match_urls": ["water_list"],
        "default_label": "Wasser",
        "icon": "bi-droplet",
        "zone": "main",
        "display": "icon_text",
        "order": 5,
    },
    {
        "id": "analytics",
        "url_name": "tracker:analytics",
        "match_urls": ["analytics"],
        "default_label": "Auswertungen",
        "icon": "bi-pie-chart",
        "zone": "main",
        "display": "icon_text",
        "order": 6,
    },
    {
        "id": "profile",
        "url_name": "tracker:profile",
        "match_urls": ["profile"],
        "default_label": "Profil",
        "icon": "bi-gear",
        "zone": "utility",
        "display": "icon_text",
        "order": 1,
    },
    {
        "id": "design_studio",
        "url_name": "design_studio:studio",
        "match_urls": ["studio"],
        "default_label": "Design Studio",
        "icon": "bi-palette",
        "zone": "utility",
        "display": "icon_only",
        "order": 2,
        "locked": True,
    },
    {
        "id": "night_mode",
        "url_name": "design_studio:toggle_night",
        "match_urls": [],
        "default_label": "Tag / Nacht",
        "icon": "bi-moon-stars",
        "zone": "utility",
        "display": "icon_only",
        "order": 3,
    },
    {
        "id": "admin",
        "url_name": "admin:index",
        "match_urls": [],
        "default_label": "Admin",
        "icon": "bi-shield-lock",
        "zone": "utility",
        "display": "icon_only",
        "order": 4,
        "staff_only": True,
    },
]
