import os
import sys
from app import create_app
from extensions import db
from models import User, Instrument


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        if Instrument.query.count() == 0:
            default_names = [
                'Instrument 1',
                'Instrument 2',
                'Instrument 3',
                'Instrument 4',
                'Instrument 5',
            ]
            for name in default_names:
                db.session.add(Instrument(name=name))
            db.session.commit()
            print(f'Created {len(default_names)} default instruments.')
        else:
            print('Instruments already exist, skipping.')

        if not User.query.filter_by(is_admin=True).first():
            email = os.environ.get('ADMIN_EMAIL')
            password = os.environ.get('ADMIN_PASSWORD')

            if not email or not password:
                print('\nNo admin user found. Create one now:')
                email = input('Admin email: ').strip()
                password = input('Admin password: ').strip()

            if not email or not password:
                print('Email and password are required. Aborting.')
                sys.exit(1)

            admin = User(
                name='Administrator',
                department='Admin',
                email=email,
                is_admin=True,
            )
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            print(f'Created admin user: {email}')
        else:
            print('Admin user already exists, skipping.')

        print('Seed complete.')


if __name__ == '__main__':
    seed()
