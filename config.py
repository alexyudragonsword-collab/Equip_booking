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

    # ── Email notifications ──────────────────────────────────────────────────
    # Option A — SendGrid Web API (recommended for Railway: Twilio infra, not Cloudflare).
    # Sign up free at sendgrid.com (100 emails/day free forever).
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')

    # Option B — Resend HTTP API (may be blocked on Railway due to Cloudflare).
    # Sign up free at resend.com (3,000 emails/month free).
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY')

    # Option C — SMTP (blocked on most PaaS platforms).
    MAIL_SERVER   = os.environ.get('MAIL_SERVER')
    MAIL_PORT     = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS  = os.environ.get('MAIL_USE_TLS', '1') == '1'
    MAIL_USE_SSL  = os.environ.get('MAIL_USE_SSL', '0') == '1'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')          # login user
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')          # login password
    MAIL_SENDER   = os.environ.get('MAIL_SENDER') or os.environ.get('MAIL_USERNAME')
    # Email address that receives booking/cancellation notifications.
    # Defaults to ADMIN_EMAIL if not set separately.
    NOTIFY_ADMIN_EMAIL = os.environ.get('NOTIFY_ADMIN_EMAIL') or os.environ.get('ADMIN_EMAIL')
