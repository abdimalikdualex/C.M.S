# Single-stack deployment (app + database together)

No separate PostgreSQL service. The database is **SQLite** (`db.sqlite3`) stored next to the app.

## Run locally (one command)

**Windows:** double-click `run.bat` or:

```powershell
cd CollegeManagement-Duale
.\run.bat
```

**Mac/Linux:**

```bash
chmod +x run.sh
./run.sh
```

Open http://127.0.0.1:8000/ — your data stays in `db.sqlite3`.

## Deploy on Render (one web service only)

1. **Delete or do not create** a separate Render PostgreSQL instance.
2. In your **Web Service → Environment**, **remove** `DATABASE_URL` and `DATABASE_EXTERNAL_URL` if they exist.
3. Add:

| Variable | Value |
|----------|--------|
| `USE_SQLITE` | `1` |
| `SQLITE_PATH` | `/var/data/db.sqlite3` |
| `RENDER_DISK_PATH` | `/var/data` |
| `MEDIA_ROOT` | `/var/data/media` |

4. **Disks** → Add disk, mount path `/var/data`, size 1 GB (keeps data across redeploys).
   The disk is only writable when the app **runs**, not during the build — that is expected.
5. **Build:** `./build.sh` — **Start:** `./start.sh`
6. Deploy from `render.yaml` in this repo (Blueprint) or set the values manually.

### First deploy with your existing local data

Upload a copy of your local `db.sqlite3` to `/var/data/db.sqlite3` using Render Shell, **or** run after deploy:

```bash
python manage.py merge_sqlite_data
```

(requires `db.sqlite3` in the project directory during Shell upload)

## Optional: external Postgres

Only if you later want a managed database:

- Set `USE_POSTGRES=1` and `DATABASE_URL=postgresql://...`
- Do **not** set `USE_SQLITE=1`

Default behaviour without any env vars is SQLite in the project folder.
