from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('bookings.index'))

    if request.method == 'POST':
        name            = request.form.get('name', '').strip()
        department      = request.form.get('department', '').strip()
        email           = request.form.get('email', '').strip().lower()
        phone           = request.form.get('phone', '').strip()
        supervisor_name = request.form.get('supervisor_name', '').strip()
        password        = request.form.get('password', '')
        confirm         = request.form.get('confirm_password', '')

        errors = []
        if not name:
            errors.append('Full name is required.')
        if not department:
            errors.append('Department is required.')
        if not email:
            errors.append('Email is required.')
        if not phone:
            errors.append('Phone number is required.')
        if not supervisor_name:
            errors.append('Supervisor name is required.')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        if User.query.filter_by(email=email).first():
            errors.append('An account with this email already exists.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html',
                                   name=name, department=department, email=email,
                                   phone=phone, supervisor_name=supervisor_name)

        user = User(name=name, department=department, email=email,
                    phone=phone or None, supervisor_name=supervisor_name or None)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('bookings.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('bookings.index'))

        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
