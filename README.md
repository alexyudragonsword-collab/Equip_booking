# Equip Booking — Instrument Booking System

A self-contained web application for managing time-slot bookings on shared
laboratory instruments.

## Features

- 5 instruments out of the box; admin can rename, add, or deactivate
- Visual weekly timeline with click/drag selection (1–4 hour slots)
- Form-based booking as an alternative input method
- Weekday-only booking (Mon–Fri) from 09:00 to 17:00
- Per-user weekly limit (max 3 bookings)
- User registration with name, department, and email
- Admin panel: user management, instrument management, view/cancel any booking
- CSRF protection, hashed passwords, session-based auth

## Tech Stack

Flask · SQLAlchemy · SQLite · Gunicorn · vanilla HTML/CSS/JS

---

## Local Development

```bash
pip install -r requirements.txt
ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=admin1234 python seed.py
flask --app app run
```

Open <http://127.0.0.1:5000>.

---

## Production Deployment

The app is packaged for any platform that runs a Dockerfile or a Procfile.

### Required Environment Variables

| Variable          | Required | Description |
|---|---|---|
| `SECRET_KEY`      | yes | Random 32+ byte hex string for session signing |
| `DATABASE_URL`    | recommended | e.g. `sqlite:////data/booking.db` on a mounted volume |
| `ADMIN_EMAIL`     | first deploy | Bootstrap admin user; ignored once an admin exists |
| `ADMIN_PASSWORD`  | first deploy | Bootstrap admin password |
| `FORCE_HTTPS`     | optional | Set to `1` when serving over HTTPS (Secure cookies) |
| `FLASK_ENV`       | optional | Defaults to `production` |

Generate a SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> **SQLite persistence note**: SQLite stores everything in a single file.
> Mount a **persistent volume** at the directory containing that file
> (default `/data`) on whichever platform you deploy to, or every redeploy
> will wipe the database.

---

### Deploy to Fly.io

```bash
# One-time: install flyctl and log in
brew install flyctl   # or: curl -L https://fly.io/install.sh | sh
fly auth login

# From the project root:
fly launch --no-deploy --copy-config
fly volumes create booking_data --region <region> --size 1
fly secrets set \
  SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  ADMIN_EMAIL=you@example.com \
  ADMIN_PASSWORD=change-me
fly deploy
```

The provided `fly.toml` mounts the volume at `/data`, forces HTTPS, and
configures `/healthz` for health checks.

### Deploy to Railway

```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

In the Railway dashboard:
1. **Variables** → add `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
   `DATABASE_URL=sqlite:////data/booking.db`, `FORCE_HTTPS=1`.
2. **Volumes** → add a volume mounted at `/data`.
3. Re-deploy.

The provided `railway.json` declares the Dockerfile build and the
`/healthz` health-check path.

### Deploy to Render

1. Push your repo to GitHub.
2. In the Render dashboard, click **New → Blueprint** and select the repo —
   Render reads `render.yaml` automatically.
3. Set the `ADMIN_EMAIL` and `ADMIN_PASSWORD` env vars in the dashboard
   (marked `sync: false` so they aren't committed).
4. Click **Apply**.

The blueprint provisions a 1 GB persistent disk at `/data` for the SQLite
database. **Persistent disks require a paid plan**; on the free tier the
database resets on every deploy.

### Deploy with Docker (any host)

```bash
docker build -t equip-booking .
docker run -d \
  -p 80:8000 \
  -v equip_data:/data \
  -e SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  -e ADMIN_EMAIL=admin@example.com \
  -e ADMIN_PASSWORD=change-me \
  -e FORCE_HTTPS=1 \
  --name equip-booking \
  equip-booking
```

Put nginx, Caddy, or Cloudflare in front for TLS termination.
A sample nginx config is provided in `nginx.conf.example`.

### Deploy on a bare Linux VPS (no Docker)

```bash
git clone <your-repo> /srv/equip_booking
cd /srv/equip_booking
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Environment
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export DATABASE_URL=sqlite:////srv/equip_booking/data/booking.db
export ADMIN_EMAIL=admin@example.com
export ADMIN_PASSWORD=change-me

# Run
gunicorn -c gunicorn.conf.py app:app
```

Wire this into a `systemd` service and front it with `nginx.conf.example`.

---

## First-deploy Admin Bootstrap

If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set as env vars on first
deploy, the app creates an admin user automatically (only if no admin
exists yet). You can also create one interactively after the fact:

```bash
flask --app app create-admin
```

---

## Health Check

`GET /healthz` returns `{"status":"ok"}` and verifies DB connectivity.
All PaaS configs already point at this path.

---

## Backups

The entire dataset is a single SQLite file. Back it up by copying
`/data/booking.db`:

```bash
# Fly.io
fly ssh sftp shell -a equip-booking
get /data/booking.db ./booking.db.backup

# Docker
docker cp equip-booking:/data/booking.db ./booking.db.backup
```

---

## Project Layout

```
.
├── app.py                  Flask app factory, health check, error handlers, CLI
├── config.py               Environment-driven config
├── extensions.py           SQLAlchemy / Flask-Login singletons
├── models.py               User, Instrument, Booking models
├── seed.py                 Standalone seed script (also runs on startup automatically)
├── routes/
│   ├── auth.py             Register / login / logout
│   ├── bookings.py         Main grid, /book, /cancel, /my-bookings
│   └── admin.py            /admin/* — users, instruments, all bookings
├── templates/              Jinja2 templates
├── static/
│   ├── css/                main, timeline, admin styles
│   └── js/                 timeline grid + form interactions
│
├── Dockerfile              Production container image
├── Procfile                For Heroku-style platforms
├── gunicorn.conf.py        WSGI server config
├── fly.toml                Fly.io deploy config
├── railway.json            Railway deploy config
├── render.yaml             Render blueprint
├── nginx.conf.example      Sample reverse-proxy config
└── .env.example            Environment variable template
```
