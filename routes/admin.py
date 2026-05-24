import calendar
import csv
import io
from functools import wraps
from datetime import date, timedelta
from flask import Blueprint, render_template, request, jsonify, abort, current_app, Response
from flask_login import login_required, current_user
from extensions import db
from models import User, Instrument, Booking
from mailer import notify_booking_cancelled, test_send, email_method

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@login_required
@admin_required
def index():
    from flask import redirect, url_for
    return redirect(url_for('admin.bookings'))


def _parse_booking_filters(args):
    """Parse date range and user/dept filters from request args.
    Returns (query, date_from, date_to, period, year, month, user_q, dept_q).
    """
    today = date.today()
    period = args.get('period', 'month')

    if period == 'year':
        try:
            year = int(args.get('year', today.year))
        except (ValueError, TypeError):
            year = today.year
        date_from = date(year, 1, 1)
        date_to   = date(year, 12, 31)
        month = today.month
    elif period == 'range':
        try:
            date_from = date.fromisoformat(args.get('date_from', ''))
        except (ValueError, TypeError):
            date_from = today.replace(day=1)
        try:
            date_to = date.fromisoformat(args.get('date_to', ''))
        except (ValueError, TypeError):
            date_to = today
        if date_to < date_from:
            date_to = date_from
        year  = date_from.year
        month = date_from.month
    else:  # month (default)
        period = 'month'
        try:
            year = int(args.get('year', today.year))
        except (ValueError, TypeError):
            year = today.year
        try:
            month = int(args.get('month', today.month))
            if not 1 <= month <= 12:
                month = today.month
        except (ValueError, TypeError):
            month = today.month
        date_from = date(year, month, 1)
        date_to   = date(year, month, calendar.monthrange(year, month)[1])

    user_q = args.get('user_q', '').strip()
    dept_q = args.get('dept', '').strip()

    query = (
        Booking.query
        .join(User, Booking.user_id == User.id)
        .filter(Booking.date >= date_from, Booking.date <= date_to)
    )
    if user_q:
        query = query.filter(User.name.ilike(f'%{user_q}%'))
    if dept_q:
        query = query.filter(User.department == dept_q)

    query = query.order_by(Booking.date, Booking.instrument_id, Booking.start_hour)
    return query, date_from, date_to, period, year, month, user_q, dept_q


@admin_bp.route('/bookings')
@login_required
@admin_required
def bookings():
    today = date.today()
    query, date_from, date_to, period, year, month, user_q, dept_q = \
        _parse_booking_filters(request.args)

    all_bookings = query.all()
    departments = [r[0] for r in
                   db.session.query(User.department).distinct()
                   .order_by(User.department).all()]
    years = list(range(today.year - 3, today.year + 2))

    return render_template(
        'admin/bookings.html',
        bookings=all_bookings,
        departments=departments,
        years=years,
        period=period,
        year=year,
        month=month,
        date_from=date_from,
        date_to=date_to,
        user_q=user_q,
        dept_q=dept_q,
        today=today,
    )


@admin_bp.route('/bookings/export')
@login_required
@admin_required
def export_bookings():
    query, date_from, date_to, period, *_ = _parse_booking_filters(request.args)
    rows = query.all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Instrument', 'User', 'Department', 'Email',
                'Phone', 'Supervisor', 'Time', 'Duration (h)', 'Booking ID'])
    for b in rows:
        w.writerow([
            b.date.strftime('%Y-%m-%d'),
            b.instrument.name,
            b.user.name,
            b.user.department,
            b.user.email,
            b.user.phone or '',
            b.user.supervisor_name or '',
            b.time_display,
            b.duration,
            b.id,
        ])

    filename = f'bookings_{date_from}_{date_to}.csv'
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@admin_bp.route('/bookings/cancel/<int:booking_id>', methods=['POST'])
@login_required
@admin_required
def cancel_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({'success': False, 'error': 'Booking not found.'}), 404

    info = {
        'user_name':       booking.user.name,
        'department':      booking.user.department,
        'user_email':      booking.user.email,
        'phone':           booking.user.phone,
        'supervisor_name': booking.user.supervisor_name,
        'instrument':      booking.instrument.name,
        'date':            booking.date.strftime('%A, %d %B %Y'),
        'time':            booking.time_display,
    }
    cancelled_by = f'{current_user.name} (admin)'

    db.session.delete(booking)
    db.session.commit()

    notify_booking_cancelled(current_app._get_current_object(), info, cancelled_by)
    return jsonify({'success': True})


@admin_bp.route('/instruments')
@login_required
@admin_required
def instruments():
    all_instruments = Instrument.query.order_by(Instrument.id).all()
    return render_template('admin/instruments.html', instruments=all_instruments)


@admin_bp.route('/instruments/add', methods=['POST'])
@login_required
@admin_required
def add_instrument():
    data = request.get_json()
    name = (data or {}).get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required.'}), 400
    if Instrument.query.filter_by(name=name).first():
        return jsonify({'success': False, 'error': 'An instrument with this name already exists.'}), 409
    instr = Instrument(name=name)
    db.session.add(instr)
    db.session.commit()
    return jsonify({'success': True, 'id': instr.id, 'name': instr.name})


@admin_bp.route('/instruments/rename/<int:instrument_id>', methods=['POST'])
@login_required
@admin_required
def rename_instrument(instrument_id):
    instr = db.session.get(Instrument, instrument_id)
    if not instr:
        return jsonify({'success': False, 'error': 'Instrument not found.'}), 404
    data = request.get_json()
    name = (data or {}).get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required.'}), 400
    existing = Instrument.query.filter_by(name=name).first()
    if existing and existing.id != instrument_id:
        return jsonify({'success': False, 'error': 'An instrument with this name already exists.'}), 409
    instr.name = name
    db.session.commit()
    return jsonify({'success': True, 'name': instr.name})


@admin_bp.route('/instruments/toggle/<int:instrument_id>', methods=['POST'])
@login_required
@admin_required
def toggle_instrument(instrument_id):
    instr = db.session.get(Instrument, instrument_id)
    if not instr:
        return jsonify({'success': False, 'error': 'Instrument not found.'}), 404
    instr.is_active = not instr.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': instr.is_active})


DEPARTMENTS = ['SHARE', 'CREATE-others']


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    dept_q = request.args.get('dept', '').strip()
    query = User.query
    if dept_q:
        query = query.filter(User.department == dept_q)
    all_users = query.order_by(User.created_at).all()
    return render_template('admin/users.html', users=all_users,
                           departments=DEPARTMENTS, dept_q=dept_q)


@admin_bp.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request.'}), 400

    name            = data.get('name', '').strip()
    department      = data.get('department', '').strip()
    email           = data.get('email', '').strip().lower()
    phone           = data.get('phone', '').strip()
    supervisor_name = data.get('supervisor_name', '').strip()
    password        = data.get('password', '')
    is_admin        = bool(data.get('is_admin', False))

    if not name or not department or not email or not phone or not supervisor_name or not password:
        return jsonify({'success': False, 'error': 'All fields except admin flag are required.'}), 400
    if department not in DEPARTMENTS:
        return jsonify({'success': False, 'error': 'Invalid department.'}), 400
    if len(password) < 8:
        return jsonify({'success': False, 'error': 'Password must be at least 8 characters.'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email already in use.'}), 409

    user = User(name=name, department=department, email=email,
                phone=phone or None, supervisor_name=supervisor_name or None,
                is_admin=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'name': user.name,
            'department': user.department,
            'email': user.email,
            'phone': user.phone or '',
            'supervisor_name': user.supervisor_name or '',
            'is_admin': user.is_admin,
            'created_at': user.created_at.strftime('%Y-%m-%d'),
        }
    })


@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'You cannot delete your own account.'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found.'}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    cfg = current_app.config
    method = email_method(current_app._get_current_object())
    notify_to     = cfg.get('NOTIFY_ADMIN_EMAIL') or '(not set)'
    mail_server   = cfg.get('MAIL_SERVER') or '(not set)'
    mail_username = cfg.get('MAIL_USERNAME') or '(not set)'
    return render_template(
        'admin/settings.html',
        email_method=method,
        notify_to=notify_to,
        mail_server=mail_server,
        mail_username=mail_username,
    )


@admin_bp.route('/settings/test-email', methods=['POST'])
@login_required
@admin_required
def test_email():
    to = current_app.config.get('NOTIFY_ADMIN_EMAIL') or current_app.config.get('ADMIN_EMAIL')
    if not to:
        return jsonify({'success': False, 'error': 'NOTIFY_ADMIN_EMAIL is not configured.'}), 400
    ok, message = test_send(current_app._get_current_object(), to)
    return jsonify({'success': ok, 'message': message})
