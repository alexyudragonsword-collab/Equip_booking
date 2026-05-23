import os
import secrets


def _normalize_db_url(url: str) -> str:
    # Some PaaS expose Postgres as 'postgres://'; SQLAlchemy needs 'postgresql://'
    if url and url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    ENV = os.environ.get('FLASK_ENV', 'production')
    IS_PRODUCTION = ENV == 'production'

    # SECRET_KEY: required in production. Falls back to a random key in dev
    # (sessions reset on each restart, but the app still runs).
    SECRET_KEY = os.environ.get('SECRET_KEY') or (
        secrets.token_hex(32) if not IS_PRODUCTION else None
    )

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get('DATABASE_URL')
        or 'sqlite:///' + os.path.join(
            os.path.abspath(os.path.dirname(__file__)), 'instance', 'booking.db'
        )
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }

    WTF_CSRF_TIME_LIMIT = 3600

    # Cookie security — only marked Secure when running behind HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = IS_PRODUCTION and os.environ.get('FORCE_HTTPS', '0') == '1'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    # Trust X-Forwarded-* headers when behind a reverse proxy (PaaS, nginx)
    TRUST_PROXY = os.environ.get('TRUST_PROXY', '1') == '1'

    # Auto-create tables + seed default instruments on first startup
    AUTO_INIT_DB = os.environ.get('AUTO_INIT_DB', '1') == '1'

    # If ADMIN_EMAIL / ADMIN_PASSWORD env vars are set and no admin exists yet,
    # create one automatically on startup. Useful for PaaS first deploy.
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
