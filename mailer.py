"""Async email notifications via stdlib smtplib — no extra dependencies."""
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _send(app, subject, body_text, to_email):
    cfg = app.config
    server   = cfg.get('MAIL_SERVER')
    port     = cfg.get('MAIL_PORT', 587)
    username = cfg.get('MAIL_USERNAME')
    password = cfg.get('MAIL_PASSWORD')
    sender   = cfg.get('MAIL_SENDER') or username
    use_tls  = cfg.get('MAIL_USE_TLS', True)
    use_ssl  = cfg.get('MAIL_USE_SSL', False)

    if not server or not username or not password:
        app.logger.debug('Email not configured — skipping notification.')
        return

    try:
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

        app.logger.info(f'Email sent → {to_email}: {subject}')
    except Exception as exc:
        app.logger.error(f'Email send failed: {exc}')


def _async(app, subject, body, to_email):
    """Fire-and-forget: runs _send in a daemon thread."""
    threading.Thread(
        target=_send,
        args=(app, subject, body, to_email),
        daemon=True,
    ).start()


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
