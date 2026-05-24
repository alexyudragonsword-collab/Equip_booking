import json
from datetime import date, timedelta
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user
from extensions import db
from models import Instrument, Booking
from mailer import notify_booking_confirmed, notify_booking_cancelled

bookings_bp = Blueprint('bookings', __name__)

HOURS = list(range(9, 17))  # 9..16 start hours; end hours 10..17


def get_week_dates(iso_week_str=None):
    """Return (monday, [date Mon..Fri]) for the given ISO week string 'YYYY-WW' or current week."""
    today = date.today()
    if iso_week_str:
        try:
            year, week = iso_week_str.split('-W')
            monday = date.fromisocalendar(int(year), int(week), 1)
        except Exception:
            monday = today - timedelta(days=today.weekday())
    else:
        monday = today - timedelta(days=today.weekday())
    weekdays = [monday + timedelta(days=i) for i in range(5)]
    return monday, weekdays


def build_bookings_data(instruments, weekdays):
    """Build nested dict {instrument_id: {date_str: [booking_dicts]}} for JS consumption."""
    data = {}
    for instr in instruments:
        data[str(instr.id)] = {}
        for d in weekdays:
            data[str(instr.id)][d.isoformat()] = []

    bookings = Booking.query.filter(
        Booking.instrument_id.in_([i.id for i in instruments]),
        Booking.date >= weekdays[0],
        Booking.date <= weekdays[-1],
    ).all()

    for b in bookings:
        iid = str(b.instrument_id)
        ds = b.date.isoformat()
        if iid in data and ds in data[iid]:
            data[iid][ds].append({
                'booking_id': b.id,
                'user_id': b.user_id,
                'user_name': b.user.name,
                'user_email': b.user.email,
                'user_phone': b.user.phone or '',
                'start_hour': b.start_hour,
                'end_hour': b.end_hour,
                'is_mine': b.user_id == current_user.id,
            })
    return data


@bookings_bp.route('/')
@login_required
def index():
    week_param = request.args.get('week', '')
    instr_filter = request.args.get('instr', '')
    monday, weekdays = get_week_dates(week_param or None)

    iso_year, iso_week, _ = monday.isocalendar()
    current_week_str = f'{iso_year}-W{iso_week:02d}'

    prev_monday = monday - timedelta(weeks=1)
    next_monday = monday + timedelta(weeks=1)
    py, pw, _ = prev_monday.isocalendar()
    ny, nw, _ = next_monday.isocalendar()
    prev_week_str = f'{py}-W{pw:02d}'
    next_week_str = f'{ny}-W{nw:02d}'

    instruments = Instrument.query.filter_by(is_active=True).order_by(Instrument.id).all()
    bookings_data = build_bookings_data(instruments, weekdays)

    today = date.today()
    today_str = today.isoformat()
    max_booking_date_str = (today + timedelta(days=7)).isoformat()

    return render_template(
        'bookings/index.html',
        instruments=instruments,
        weekdays=weekdays,
        hours=HOURS,
        bookings_json=json.dumps(bookings_data),
        week_dates_json=json.dumps([d.isoformat() for d in weekdays]),
        current_week_str=current_week_str,
        prev_week_str=prev_week_str,
        next_week_str=next_week_str,
        today_str=today_str,
        monday=monday,
        max_booking_date_str=max_booking_date_str,
        instr_filter=instr_filter,
    )


@bookings_bp.route('/book', methods=['POST'])
@login_required
def book():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request.'}), 400

    try:
        instrument_id = int(data['instrument_id'])
        booking_date = date.fromisoformat(data['date'])
        start_hour = int(data['start_hour'])
        end_hour = int(data['end_hour'])
    except (KeyError, ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid parameters.'}), 400

    # Rule 1: no weekends
    if booking_date.weekday() >= 5:
        return jsonify({'success': False, 'error': 'Bookings are only allowed Monday to Friday.'}), 400

    # Rule 2 & 3: valid hours and duration
    if not (9 <= start_hour < end_hour <= 17):
        return jsonify({'success': False, 'error': 'Invalid time range.'}), 400
    duration = end_hour - start_hour
    if not (1 <= duration <= 4):
        return jsonify({'success': False, 'error': 'Booking duration must be between 1 and 4 hours.'}), 400

    # Rule 4: no past dates
    if booking_date < date.today():
        return jsonify({'success': False, 'error': 'Cannot book a date in the past.'}), 400

    # Rule 4b: regular users can only book within 7 days from today
    if not current_user.is_admin and booking_date > date.today() + timedelta(days=7):
        return jsonify({'success': False, 'error': 'You can only book slots within the next 7 days.'}), 400

    # Rule 5: instrument exists
    instrument = Instrument.query.filter_by(id=instrument_id, is_active=True).first()
    if not instrument:
        return jsonify({'success': False, 'error': 'Instrument not found.'}), 404

    # Rule 6: no overlap
    overlap = Booking.query.filter(
        Booking.instrument_id == instrument_id,
        Booking.date == booking_date,
        Booking.start_hour < end_hour,
        Booking.end_hour > start_hour,
    ).first()
    if overlap:
        return jsonify({'success': False, 'error': 'This time slot is already booked.'}), 409

    # Rule 7: max 3 slots per user per week
    week_start = booking_date - timedelta(days=booking_date.weekday())
    week_end = week_start + timedelta(days=6)
    existing_count = Booking.query.filter(
        Booking.user_id == current_user.id,
        Booking.date >= week_start,
        Booking.date <= week_end,
    ).count()
    if existing_count >= 3:
        return jsonify({'success': False, 'error': 'You have reached the maximum of 3 bookings for this week.'}), 409

    booking = Booking(
        user_id=current_user.id,
        instrument_id=instrument_id,
        date=booking_date,
        start_hour=start_hour,
        end_hour=end_hour,
    )
    db.session.add(booking)
    db.session.commit()

    notify_booking_confirmed(current_app._get_current_object(), booking, instrument, current_user)

    return jsonify({
        'success': True,
        'booking': {
            'booking_id': booking.id,
            'user_id': current_user.id,
            'user_name': current_user.name,
            'user_email': current_user.email,
            'user_phone': current_user.phone or '',
            'start_hour': start_hour,
            'end_hour': end_hour,
            'is_mine': True,
        }
    })


@bookings_bp.route('/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({'success': False, 'error': 'Booking not found.'}), 404
    if booking.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Not authorized.'}), 403

    # Capture info before delete
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
    cancelled_by = current_user.name

    db.session.delete(booking)
    db.session.commit()

    notify_booking_cancelled(current_app._get_current_object(), info, cancelled_by)
    return jsonify({'success': True})


@bookings_bp.route('/my-bookings')
@login_required
def my_bookings():
    today = date.today()
    upcoming = Booking.query.filter(
        Booking.user_id == current_user.id,
        Booking.date >= today,
    ).order_by(Booking.date, Booking.start_hour).all()

    past = Booking.query.filter(
        Booking.user_id == current_user.id,
        Booking.date < today,
    ).order_by(Booking.date.desc(), Booking.start_hour).limit(20).all()

    return render_template('bookings/my_bookings.html', upcoming=upcoming, past=past)
