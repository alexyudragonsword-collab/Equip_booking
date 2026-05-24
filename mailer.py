"""Email notifications — supports SendGrid, Resend, and SMTP."""
import json
import re
import smtplib
import threading
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ── SendGrid Web API v3 ───────────────────────────────────────────────────────

def _parse_address(addr):
    """Split 'Name <email>' into (name_or_None, email)."""
    m = re.match(r'^(.*)<(.+)>$', addr.strip())
    if m:
        return m.group(1).strip() or None, m.group(2).strip()
    return None, addr.strip()


def _send_sendgrid(api_key, from_addr, to_email, subject, body_text):
    """Send via SendGrid Web API. Raises on failure."""
    from_name, from_email = _parse_address(from_addr)
    from_obj = {"email": from_email}
    if from_name:
        from_obj["name"] = from_name

    payload = json.dumps({
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": from_obj,
        "subject": subject,
        "content": [{"type": "text/plain", "value": body_text}],
    }).encode()
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()  # 202 empty body on success
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors='replace')
        raise RuntimeError(f"SendGrid API {exc.code}: {body}") from exc


# ── Resend HTTP API ───────────────────────────────────────────────────────────

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


# ── Unified send ──────────────────────────────────────────────────────────────

def _send(app, subject, body_text, to_email):
    cfg = app.config
    default_sender = cfg.get('MAIL_SENDER') or 'Booking System <noreply@example.com>'

    # Priority 1: SendGrid
    sg_key = cfg.get('SENDGRID_API_KEY')
    if sg_key:
        try:
            _send_sendgrid(sg_key, default_sender, to_email, subject, body_text)
            app.logger.info(f'Email sent via SendGrid → {to_email}: {subject}')
        except Exception as exc:
            app.logger.error(f'SendGrid send failed: {exc}')
        return

    # Priority 2: Resend
    resend_key = cfg.get('RESEND_API_KEY')
    if resend_key:
        from_addr = cfg.get('MAIL_SENDER') or 'Booking System <onboarding@resend.dev>'
        try:
            _send_resend(resend_key, from_addr, to_email, subject, body_text)
            app.logger.info(f'Email sent via Resend → {to_email}: {subject}')
        except Exception as exc:
            app.logger.error(f'Resend send failed: {exc}')
        return

    # Priority 3: SMTP
    server   = cfg.get('MAIL_SERVER')
    username = cfg.get('MAIL_USERNAME')
    password = cfg.get('MAIL_PASSWORD')
    if not server or not username or not password:
        app.logger.warning(
            'Email not configured — set SENDGRID_API_KEY, RESEND_API_KEY, '
            'or MAIL_SERVER + MAIL_USERNAME + MAIL_PASSWORD.'
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
    threading.Thread(target=_send, args=(app, subject, body, to_email), daemon=True).start()


def email_method(app):
    """Return active method: 'sendgrid', 'resend', 'smtp', or None."""
    cfg = app.config
    if cfg.get('SENDGRID_API_KEY'):
        return 'sendgrid'
    if cfg.get('RESEND_API_KEY'):
        return 'resend'
    if cfg.get('MAIL_SERVER') and cfg.get('MAIL_USERNAME') and cfg.get('MAIL_PASSWORD'):
        return 'smtp'
    return None


def test_send(app, to_email):
    """Synchronous test — returns (ok: bool, message: str)."""
    cfg = app.config
    subject  = '[Test] Instrument Booking — email config check'
    body     = ('This is a test email from your Instrument Booking system.\n'
                'If you received this, your email configuration is working correctly.')
    default_sender = cfg.get('MAIL_SENDER') or 'Booking System <noreply@example.com>'

    sg_key = cfg.get('SENDGRID_API_KEY')
    if sg_key:
        try:
            _send_sendgrid(sg_key, default_sender, to_email, subject, body)
            return True, f'Test email sent via SendGrid to {to_email}.'
        except Exception as exc:
            return False, f'SendGrid send failed: {exc}'

    resend_key = cfg.get('RESEND_API_KEY')
    if resend_key:
        from_addr = cfg.get('MAIL_SENDER') or 'Booking System <onboarding@resend.dev>'
        try:
            _send_resend(resend_key, from_addr, to_email, subject, body)
            return True, f'Test email sent via Resend to {to_email}.'
        except Exception as exc:
            return False, f'Resend send failed: {exc}'

    server   = cfg.get('MAIL_SERVER')
    username = cfg.get('MAIL_USERNAME')
    password = cfg.get('MAIL_PASSWORD')
    if not server or not username or not password:
        return False, (
            'Email not configured. Set SENDGRID_API_KEY (recommended for Railway), '
            'RESEND_API_KEY, or SMTP variables.'
        )

    port    = cfg.get('MAIL_PORT', 587)
    sender  = cfg.get('MAIL_SENDER') or username
    use_tls = cfg.get('MAIL_USE_TLS', True)
    use_ssl = cfg.get('MAIL_USE_SSL', False)
    try:
        _send_smtp(server, port, username, password, sender, use_tls, use_ssl,
                   to_email, subject, body)
        return True, f'Test email sent via SMTP to {to_email}.'
    except Exception as exc:
        return False, f'SMTP send failed: {exc}'


# ── Public helpers ────────────────────────────────────────────────────────────

def notify_booking_confirmed(app, booking, instrument, user):
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
