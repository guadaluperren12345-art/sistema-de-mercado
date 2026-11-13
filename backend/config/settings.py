"""
Configuración de Django para el Sistema de Mercado.

Los valores sensibles (contraseñas, clave secreta) se leen de variables de
entorno, que Docker Compose carga desde el archivo .env de la raíz.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(nombre, por_defecto=""):
    """Convierte 'a,b,c' en ['a', 'b', 'c']."""
    return [v.strip() for v in os.environ.get(nombre, por_defecto).split(",") if v.strip()]


# --- Seguridad ---
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")


# --- Aplicaciones ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "corsheaders",
    # Propias
    "core",
    "usuarios",
    "productos",
    "turnos",
    "ventas",
    "clientes",
    "gastos",
    "compras",
]

# Modelo de usuario propio con rol (documentación 7.1)
AUTH_USER_MODEL = "usuarios.Usuario"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # debe ir primero
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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


# --- Base de datos: SQL Server ---
DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": os.environ.get("DB_NAME", "sistema_mercado"),
        "USER": os.environ.get("DB_USER", "sa"),
        "PASSWORD": os.environ["MSSQL_SA_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "db"),
        "PORT": os.environ.get("DB_PORT", "1433"),
        "OPTIONS": {
            "driver": "ODBC Driver 18 for SQL Server",
            # En desarrollo el certificado de SQL Server es autofirmado
            "extra_params": "TrustServerCertificate=yes",
        },
    }
}


# --- Contraseñas (RN-06: mínimo 8 caracteres) ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "usuarios.validadores.LetraYNumeroValidator"},
]


# --- Idioma y zona horaria (Argentina) ---
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True


# --- Archivos estáticos ---
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- API (Django REST Framework + JWT) ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # JWT + turno abierto: a empleados y encargados se les corta la sesión cuando termina su turno
        "turnos.autenticacion.AutenticacionConTurno",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "usuarios.permisos.PasswordAlDia",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),  # RNF-02
    # RF-06: si pasan 30 minutos sin usar el sistema, la sesión vence.
    # Cada renovación entrega un token nuevo de 30 minutos e invalida el anterior.
    "REFRESH_TOKEN_LIFETIME": timedelta(minutes=30),
    # La invalidación de tokens usada se hace con la tabla propia `token_invalidado`
    # (la app token_blacklist de simplejwt no es compatible con SQL Server).
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "TOKEN_REFRESH_SERIALIZER": "usuarios.serializers.RenovarTokenSerializer",
    "USER_ID_FIELD": "id",
}


# --- CORS: qué páginas pueden llamar a la API ---
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
