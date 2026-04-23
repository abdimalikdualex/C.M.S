# Deployment Guide

The "Invalid details" error right after deploying the site happens because the
production database is fresh and has **no HOD/admin user yet**. The local
`db.sqlite3` file is ignored by git, so the accounts you use locally are never
copied to the host. The fix is to (1) run migrations on every deploy and
(2) seed a default admin account automatically.

Everything needed for that is already wired up in this repo:

- `main_app/management/commands/create_default_admin.py` - idempotent seeder.
- `build.sh` - build-time steps (install, collectstatic, migrate, seed admin).
- `Procfile` - `release` phase runs migrations + seeder on every deploy; `web`
  launches gunicorn.
- `college_management_system/settings.py` - respects `DATABASE_URL`,
  `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` env vars
  and trusts Render/Heroku's `X-Forwarded-Proto` header.

## Required environment variables

Set these on the host (Render dashboard > Environment, or `heroku config:set`):

| Variable | Required | Example / Default |
| --- | --- | --- |
| `SECRET_KEY` | yes (production) | any long random string |
| `DEBUG` | no | `False` (default) |
| `ALLOWED_HOSTS` | recommended | `yourapp.onrender.com,yourdomain.com` |
| `CSRF_TRUSTED_ORIGINS` | recommended | `https://yourapp.onrender.com,https://yourdomain.com` |
| `DATABASE_URL` | **strongly recommended** | `postgres://user:pass@host:5432/db` |
| `DEFAULT_ADMIN_EMAIL` | optional | `admin@elevate.college` |
| `DEFAULT_ADMIN_PASSWORD` | optional | `ElevateAdmin@2026` |
| `DEFAULT_ADMIN_FULL_NAME` | optional | `System Administrator` |
| `RESET_DEFAULT_ADMIN_PASSWORD` | optional | `1` to force-reset on next deploy |
| `EMAIL_ADDRESS`, `EMAIL_PASSWORD` | optional | SMTP Gmail credentials |

> Render's default filesystem is **ephemeral** - if you don't set
> `DATABASE_URL`, the bundled SQLite file is wiped on every redeploy and all
> users/data are lost. Always attach a managed Postgres instance and set
> `DATABASE_URL` for real deployments.

## Render setup (recommended)

1. Create a PostgreSQL instance on Render and copy its Internal Database URL.
2. Create a **Web Service** from this repo with:
   - **Build command**: `./build.sh`
   - **Start command**: `gunicorn college_management_system.wsgi --log-file -`
3. Add the environment variables from the table above (at minimum
   `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`).
4. Deploy. The build script will run migrations and create the default HOD
   account automatically.

## Heroku setup

```bash
heroku create your-app-name
heroku addons:create heroku-postgresql:mini
heroku config:set SECRET_KEY="..." ALLOWED_HOSTS="your-app-name.herokuapp.com"
git push heroku main
```

Heroku picks up the `Procfile` automatically, so the `release` phase will
migrate and seed the admin on every deploy.

## Logging in for the first time

After the first successful deploy, sign in with:

- **Email**: value of `DEFAULT_ADMIN_EMAIL` (default `admin@elevate.college`)
- **Password**: value of `DEFAULT_ADMIN_PASSWORD` (default `ElevateAdmin@2026`)

**Change the password immediately** from the HOD profile page. The seeder will
never overwrite an existing password unless you explicitly set
`RESET_DEFAULT_ADMIN_PASSWORD=1`.

## Rotating or resetting the default admin password

If you ever get locked out:

1. Set `RESET_DEFAULT_ADMIN_PASSWORD=1` and update `DEFAULT_ADMIN_PASSWORD` in
   your host's environment variables.
2. Trigger a redeploy (or run `python manage.py create_default_admin
   --reset-password` from a one-off shell).
3. **Remove `RESET_DEFAULT_ADMIN_PASSWORD`** afterwards so future deploys stop
   overwriting the password.

## Running the seeder manually

```bash
python manage.py create_default_admin
python manage.py create_default_admin --reset-password \
    --email admin@yourdomain.com --password 'Str0ngPass!' --full-name 'Admin'
```
