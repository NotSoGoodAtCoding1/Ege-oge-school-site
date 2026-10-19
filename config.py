import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or 'dev-insecure-change-me-in-env'

    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'mysql+pymysql://root@localhost:3306/eg_ege_school',
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Public self-registration (set ALLOW_PUBLIC_REGISTRATION=false in production if invites-only).
    ALLOW_PUBLIC_REGISTRATION = _env_bool('ALLOW_PUBLIC_REGISTRATION', True)

    # Session hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', False)

    # Upload limits (bytes)
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
