"""Email notifications — supports Resend HTTP API (preferred on PaaS) and SMTP fallback."""
import json
import smtplib
import threading
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ── Resend (HTTP API, works on all PaaS) ─────────────────────────────────────

def _send_resend(api_key, from_addr, to_email, subject, body_text):
    """Send via Resend API. Raises on failure."""
    payload = json.dumps({
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": body_text,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors='replace')
        raise RuntimeError(f"Resend API {exc.code}: {body}") from exc


# ── SMTP ─────────────────────────────────────────────────────────────────────

def _send_smtp(server, port, username, password, sender, use_tls, use_ssl,
               to_email, subject, body_text):
    """Send via SMTP. Raises on failure."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = sender
    msg['To']      = to_email
    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

    if use_ssl:
        conn = smtplib.SMTP_SSL(server, port, timeout=10)
    else:
        conn = smtplib.SMTP(server, port, timeout=10)

    with conn:
        conn.ehlo()
        if use_tls and not use_ssl:
            conn.starttls()
            conn.ehlo()
        conn.login(username, password)
        conn.sendmail(sender, [to_email], msg.as_string())


# ── Unified send (picks method from app config) ───────────────────────────────

def _send(app, subject, body_text, to_email):
    cfg = app.config

    # Prefer Resend if API key is set
    api_key = cfg.get('RESEND_API_KEY')
    if api_key:
        from_addr = cfg.get('MAIL_SENDER') or 'Booking System <onboarding@resend.dev>'
        try:
            _send_resend(api_key, from_addr, to_email, subject, body_text)
            app.logger.info(f'Email sent via Resend → {to_email}: {subject}')
        except Exception as exc:
            app.logger.error(f'Resend send failed: {exc}')
        return

    # Fall back to SMTP
    server   = cfg.get('MAIL_SERVER')
    username = cfg.get('MAIL_USERNAME')
    password = cfg.get('MAIL_PASSWORD')
    if not server or not username or not password:
        app.logger.warning(
            'Email not configured — set RESEND_API_KEY (recommended on PaaS) '
            'or MAIL_SERVER + MAIL_USERNAME + MAIL_PASSWORD for SMTP.'
        )
        return

    port    = cfg.get('MAIL_PORT', 587)
    sender  = cfg.get('MAIL_SENDER') or username
    use_tls = cfg.get('MAIL_USE_TLS', True)
    use_ssl = cfg.get('MAIL_USE_SSL', False)
    try:
        _send_smtp(server, port, username, password, sender, use_tls, use_ssl,
                   to_email, subject, body_text)
        app.logger.info(f'Email sent via SMTP → {to_email}: {subject}')
    except Exception as exc:
        app.logger.error(f'SMTP send failed: {exc}')


def _async(app, subject, body, to_email):
    """Fire-and-forget: runs _send in a daemon thread."""
    threading.Thread(
        target=_send,
        args=(app, subject, body, to_email),
        daemon=True,
    ).start()


def test_send(app, to_email):
    """Synchronous test — returns (ok: bool, message: str)."""
    cfg = app.config

    api_key = cfg.get('RESEND_API_KEY')
    if api_key:
        from_addr = cfg.get('MAIL_SENDER') or 'Booking System <onboarding@resend.dev>'
        try:
            _send_resend(api_key, from_addr, to_email,
                         '[Test] Instrument Booking — email config check',
                         'This is a test email from your Instrument Booking system.\n'
                         'If you received this, your Resend configuration is working correctly.')
            return True, f'Test email sent via Resend to {to_email}.'
        except Exception as exc:
            return False, f'Resend send failed: {exc}'

    server   = cfg.get('MAIL_SERVER')
    username = cfg.get('MAIL_USERNAME')
    password = cfg.get('MAIL_PASSWORD')
    if not server or not username or not password:
        missing = [k for k, v in [
            ('RESEND_API_KEY', api_key),
            ('MAIL_SERVER', server),
            ('MAIL_USERNAME', username),
            ('MAIL_PASSWORD', password),
        ] if not v]
        return False, (
            f"Email not configured. Set RESEND_API_KEY (recommended) or SMTP vars. "
            f"Missing: {', '.join(missing)}"
        )

    port    = cfg.get('MAIL_PORT', 587)
    sender  = cfg.get('MAIL_SENDER') or username
    use_tls = cfg.get('MAIL_USE_TLS', True)
    use_ssl = cfg.get('MAIL_USE_SSL', False)
    try:
        _send_smtp(server, port, username, password, sender, use_tls, use_ssl,
                   to_email,
                   '[Test] Instrument Booking — email config check',
                   'This is a test email from your Instrument Booking system.\n'
                   'If you received this, your SMTP configuration is working correctly.')
        return True, f'Test email sent via SMTP to {to_email}.'
    except Exception as exc:
        return False, f'Send failed: {exc}'


def email_method(app):
    """Return which method is active: 'resend', 'smtp', or None."""
    cfg = app.config
    if cfg.get('RESEND_API_KEY'):
        return 'resend'
    if cfg.get('MAIL_SERVER') and cfg.get('MAIL_USERNAME') and cfg.get('MAIL_PASSWORD'):
        return 'smtp'
    return None


# ── Public helpers ────────────────────────────────────────────────────────────

def notify_booking_confirmed(app, booking, instrument, user):
    """Called after a booking is successfully created."""
    to = app.config.get('NOTIFY_ADMIN_EMAIL')
    if not to:
        return

    subject = f'[New Booking] {instrument.name} — {user.name}'
    body = (
        f'A new booking has been confirmed.\n'
        f'{"─" * 40}\n\n'
        f'User\n'
        f'  Name:        {user.name}\n'
        f'  Department:  {user.department}\n'
        f'  Email:       {user.email}\n'
        f'  Phone:       {user.phone or "N/A"}\n'
        f'  Supervisor:  {user.supervisor_name or "N/A"}\n\n'
        f'Booking\n'
        f'  Instrument:  {instrument.name}\n'
        f'  Date:        {booking.date.strftime("%A, %d %B %Y")}\n'
        f'  Time:        {booking.start_hour:02d}:00 – {booking.end_hour:02d}:00\n'
        f'  Duration:    {booking.duration} hour(s)\n'
        f'  Booking ID:  #{booking.id}\n'
    )
    _async(app, subject, body, to)


def notify_booking_cancelled(app, info, cancelled_by_name):
    """Called after a booking is cancelled.
    info dict must be collected BEFORE the booking row is deleted.
    """
    to = app.config.get('NOTIFY_ADMIN_EMAIL')
    if not to:
        return

    subject = f'[Booking Cancelled] {info["instrument"]} — {info["user_name"]}'
    body = (
        f'A booking has been cancelled.\n'
        f'{"─" * 40}\n\n'
        f'User\n'
        f'  Name:        {info["user_name"]}\n'
        f'  Department:  {info["department"]}\n'
        f'  Email:       {info["user_email"]}\n'
        f'  Phone:       {info.get("phone") or "N/A"}\n'
        f'  Supervisor:  {info.get("supervisor_name") or "N/A"}\n\n'
        f'Booking\n'
        f'  Instrument:  {info["instrument"]}\n'
        f'  Date:        {info["date"]}\n'
        f'  Time:        {info["time"]}\n\n'
        f'Cancelled by: {cancelled_by_name}\n'
    )
    _async(app, subject, body, to)
