import os
import click
from flask import Flask, render_template, jsonify
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from extensions import db, login_manager

csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if app.config['IS_PRODUCTION'] and not app.config.get('SECRET_KEY'):
        raise RuntimeError(
            'SECRET_KEY environment variable must be set in production.'
        )

    os.makedirs(app.instance_path, exist_ok=True)
    _ensure_sqlite_dir(app)

    if app.config.get('TRUST_PROXY'):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from routes.auth import auth_bp
    from routes.bookings import bookings_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(admin_bp)

    _register_health(app)
    _register_error_handlers(app)
    _register_cli(app)

    if app.config.get('AUTO_INIT_DB'):
        with app.app_context():
            _auto_init_db(app)

    return app


def _ensure_sqlite_dir(app):
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('sqlite:///'):
        path = uri.replace('sqlite:///', '', 1)
        # Absolute path starts with '/'
        if path.startswith('/'):
            db_dir = os.path.dirname(path)
        else:
            db_dir = os.path.dirname(os.path.join(app.root_path, path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)


def _auto_init_db(app):
    """On startup: create tables, seed instruments, optionally create initial admin."""
    from models import User, Instrument
    db.create_all()

    if Instrument.query.count() == 0:
        for name in ['Instrument 1', 'Instrument 2', 'Instrument 3',
                     'Instrument 4', 'Instrument 5']:
            db.session.add(Instrument(name=name))
        db.session.commit()
        app.logger.info('Seeded 5 default instruments.')

    admin_email = app.config.get('ADMIN_EMAIL')
    admin_password = app.config.get('ADMIN_PASSWORD')
    if admin_email and admin_password:
        if not User.query.filter_by(is_admin=True).first():
            admin = User(
                name='Administrator',
                department='Admin',
                email=admin_email.lower(),
                is_admin=True,
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            app.logger.info(f'Created initial admin user: {admin_email}')


def _register_health(app):
    @app.route('/healthz')
    def healthz():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'status': 'ok'}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'detail': str(e)}), 503


def _register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500


def _register_cli(app):
    @app.cli.command('init-db')
    def init_db_cmd():
        """Create tables, seed instruments, and optionally create the admin user."""
        _auto_init_db(app)
        click.echo('Database initialized.')

    @app.cli.command('create-admin')
    @click.option('--email', prompt=True)
    @click.password_option()
    def create_admin_cmd(email, password):
        """Create an admin user (interactive)."""
        from models import User
        if User.query.filter_by(email=email.lower()).first():
            click.echo('A user with this email already exists.', err=True)
            return
        admin = User(name='Administrator', department='Admin',
                     email=email.lower(), is_admin=True)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f'Created admin user: {email}')


app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
