"""
Imkon — Django sozlamalari.

Barcha sirlar `.env` da. Kodda hech qanday parol/kalit yo'q.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
    ACCESS_TOKEN_LIFETIME_MIN=(int, 30),
    REFRESH_TOKEN_LIFETIME_DAYS=(int, 30),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")


# ---------------------------------------------------------------- ilovalar

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

LOCAL_APPS = [
    # `common` — abstrakt modellar va `seed` buyrug'i uchun
    "apps.common",
    "apps.accounts",
    "apps.artisans",
    "apps.catalog",
    "apps.auctions",
    "apps.orders",
    "apps.administration",
    "apps.notifications",
    "apps.payments",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise — Django admin statikasini o'zi beradi. Nginx ham bera
    # oladi, lekin bu bilan konteyner yolg'iz o'zi ham to'g'ri ishlaydi
    # (masalan `docker compose` ni nginxsiz sinab ko'rganda).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # CORS CommonMiddleware'dan OLDIN turishi shart
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
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


# ---------------------------------------------------------------- baza

if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
    # Ulanishlarni qayta ishlatish — har so'rovda yangi ulanish ochilmasin
    DATABASES["default"]["CONN_MAX_AGE"] = 60
else:
    # Faqat local development uchun
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ---------------------------------------------------------------- auth

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------- DRF

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Zo'ravonlikdan himoya: OTP so'rovlarini cheklash
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "otp_send": "5/hour",
        "otp_verify": "10/hour",
        "telegram_verify": "10/hour",
        "password_login": "10/hour",
        "bid": "60/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("ACCESS_TOKEN_LIFETIME_MIN")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("REFRESH_TOKEN_LIFETIME_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Imkon API",
    "DESCRIPTION": "Hunarmandchilik auksioni va savdo platformasi",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# ---------------------------------------------------------------- CORS

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS


# ---------------------------------------------------------------- til

LANGUAGE_CODE = "uz"

# Platforma 3 tilli. Tarjima maydonlari model darajasida (title_uz/ru/en),
# so'rov tili `Accept-Language` sarlavhasidan olinadi.
LANGUAGES = [
    ("uz", "O'zbekcha"),
    ("ru", "Русский"),
    ("en", "English"),
]
MODELTRANSLATION_LANGUAGES = ("uz", "ru", "en")
LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------- statik / media

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Production'da statika siqiladi va nomiga hash qo'shiladi (keshni
# yangilash uchun). Development'da bu kerak emas — hash'lash `collectstatic`
# talab qiladi, ya'ni har o'zgarishdan keyin qayta yig'ish kerak bo'lardi.
if not DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------- SMS

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")

ESKIZ_EMAIL = env("ESKIZ_EMAIL", default="")
ESKIZ_PASSWORD = env("ESKIZ_PASSWORD", default="")
ESKIZ_FROM = env("ESKIZ_FROM", default="4546")

OTP_TTL_SECONDS = 120
OTP_MAX_ATTEMPTS = 5


# ---------------------------------------------------------------- Telegram

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_CODE_TTL_SECONDS = 300

# Botning @nomi — saytdan "To'lov qilish" bosilganda shu manzilga o'tiladi
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", default="")


# ---------------------------------------------------------------- to'lov

# Sotuvdan platformaga qoladigan ulush. Qolgani sotuvchi balansiga o'tadi.
PLATFORM_COMMISSION_PERCENT = env("PLATFORM_COMMISSION_PERCENT", default=5)

# Bot backendga shu maxfiy kalit bilan murojaat qiladi. Bo'sh bo'lsa
# `/api/bot/` butunlay yopiq — sozlanmagan kalit "hammaga ruxsat"ga
# aylanib qolmasligi kerak.
BOT_API_SECRET = env("BOT_API_SECRET", default="")

# Chek tushadigan maxfiy kanal va u yerda tugma bosa oladigan Telegram ID'lar.
# Akkaunti saytga bog'lanmagan admin ham tasdiqlay olishi uchun kerak —
# aks holda birinchi to'lovni hech kim tasdiqlay olmaydi.
PAYMENT_CHANNEL_ID = env("PAYMENT_CHANNEL_ID", default="")
TELEGRAM_ADMIN_IDS = env.list("TELEGRAM_ADMIN_IDS", default=[])


# ---------------------------------------------------------------- xavfsizlik

if not DEBUG:
    # HTTP -> HTTPS yo'naltirishni nginx qiladi, Django EMAS. Django'ga bot
    # va Next ichki tarmoqdan `http://backend:8000` orqali murojaat qiladi —
    # `True` bo'lsa ularni `https://backend:8000` ga yo'naltirib, butun
    # bot va sayt API'sini ishdan chiqarardi (Django tashqariga ochiq emas).
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    X_FRAME_OPTIONS = "DENY"
