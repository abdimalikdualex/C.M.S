# Deployment Guide

The "Invalid details" error right after deploying the site happens because the
production database is fresh and has **no HOD/admin user yet**. The local
`db.sqlite3` file is ignored by git, so the accounts you use locally are never
copied to the host. The fix is to (1) run migrations on every deploy and
(2) seed a default admin account automatically.

Everything needed for that is already wired up in this repo:

- `main_app/management/commands/create_default_admin.py` - idempotent seeder.
- `build.sh` - build-time steps (install, collectstatic).
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
| `SITE_DOMAIN` | recommended | `abdimalikduale.com,www.abdimalikduale.com` |
| `ALLOWED_HOSTS` | optional | Full override; defaults still include `.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | recommended | `https://yourapp.onrender.com,https://yourdomain.com` |
| `DATABASE_URL` | **strongly recommended** | Full URL from Render **Connect** (set automatically when you link a database) |
| `DATABASE_EXTERNAL_URL` | optional | Use Render **External** URL if internal host `dpg-…-a` does not resolve |
| `DEFAULT_ADMIN_EMAIL` | optional | Your HOD email, e.g. `amalikduale@gmail.com` |
| `DEFAULT_ADMIN_PASSWORD` | optional | The password you want for that email |
| `DEFAULT_ADMIN_FULL_NAME` | optional | `System Administrator` |
| `RESET_DEFAULT_ADMIN_PASSWORD` | optional | `1` to force-reset on next deploy |
| `EMAIL_ADDRESS`, `EMAIL_PASSWORD` | optional | SMTP Gmail credentials |

> Render's default filesystem is **ephemeral** - if you don't set
> `DATABASE_URL`, the bundled SQLite file is wiped on every redeploy and all
> users/data are lost. Always attach a managed Postgres instance and set
> `DATABASE_URL` for real deployments.

## Render setup (recommended)

1. Create a PostgreSQL instance on Render (note the **region**, e.g. Oregon).
2. Create a **Web Service** in the **same region** as the database.
3. On the web service, use **Environment → Link Database** (preferred) or paste
   the **Internal Database URL** from the database **Connect** menu as
   `DATABASE_URL`. Do not type the hostname alone (`dpg-…-a`); use the full
   `postgresql://USER:PASSWORD@HOST:5432/DATABASE` string.
4. Set:
   - **Root Directory**: `CollegeManagement-Duale` (if the repo root is one level above)
   - **Build command**: `./build.sh`
   - **Start command**: `./start.sh` (migrates, seeds admin, then starts gunicorn)
5. Add environment variables (at minimum `SECRET_KEY`, `SITE_DOMAIN`;
   `DATABASE_URL` is set automatically when you link the database):
   - `SITE_DOMAIN=abdimalikduale.com,www.abdimalikduale.com` (your custom domain)
6. Deploy. Migrations and the default HOD account are created by the Procfile
   `release` phase (`migrate` + `create_default_admin`), not during the build.

### Troubleshooting: `could not translate host name "dpg-…-a"`

This means Django cannot resolve your Postgres hostname (DNS). Common causes:

| Cause | Fix |
| --- | --- |
| Database deleted or suspended | Render Dashboard → Postgres → confirm status is **Available**; resume or create a new DB |
| Stale `DATABASE_URL` | Re-link the database to the web service, or copy a fresh URL from **Connect** |
| Web service and DB in different regions | Move one of them so both use the same region (e.g. Oregon) |
| `DATABASE_URL` is incomplete | Must be the full connection string, not only `dpg-xxxxx-a` |
| Internal host still fails | Set `DATABASE_EXTERNAL_URL` to the **External Database URL** from Render (full host like `dpg-xxxxx-a.oregon-postgres.render.com`) |

After fixing `DATABASE_URL`, trigger a **Manual Deploy**. Check deploy logs for the
`release` step; if migrate succeeds there, the app should start normally.

### Troubleshooting: `Server Error (500)` on the live site

| Cause | Fix |
| --- | --- |
| Postgres host does not resolve | Link database or set `DATABASE_EXTERNAL_URL` (see above) |
| Custom domain not allowed | Set `SITE_DOMAIN=abdimalikduale.com,www.abdimalikduale.com` |
| Migrations never ran | Use **Start command** `./start.sh` (runs `migrate` on every boot) |
| Ephemeral SQLite (no `DATABASE_URL`) | Link Render Postgres and redeploy |

After deploy, open `https://abdimalikduale.com/health/` — you should see `ok`. If `/health/` works but `/` still 500s, the database connection or migrations still need fixing on Render.

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

## Data preservation (nothing is deleted by deploy)

- **`migrate`** only updates table structure; it does **not** delete your rows.
- **`create_default_admin`** only **adds** a HOD account if missing, or updates flags/password
  when you **explicitly** set `RESET_DEFAULT_ADMIN_PASSWORD=1`. It never deletes students,
  staff, courses, or payments.
- **`./start.sh`** runs migrate + `create_default_admin` only (no data wipe).

### Copy local data into production (additive only)

If production Postgres is missing data that still exists in your local `db.sqlite3`, merge it
**without removing** anything already on the server:

```bash
# Preview (no writes)
python manage.py merge_sqlite_data --dry-run

# Copy missing users, courses, sessions, staff, students
python manage.py merge_sqlite_data
```

Run this from **Render Shell** with `DATABASE_URL` pointing at production, after uploading
`db.sqlite3` or cloning the repo that contains it. Existing production rows are kept; only
missing records are inserted (matched by id, email, or student_id).

### Restore login only (does not touch other data)

In **Render Shell** (updates one account’s password only):

```bash
python manage.py set_user_password --email amalikduale@gmail.com --password 'YourPassword'
```

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
