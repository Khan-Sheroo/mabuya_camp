# Mabuya Camp

Internal project-management app for Mabuya Restaurant (Phase 1: Home & Projects).

## Stack

- Flask + SQLAlchemy
- SQLite by default (set `DATABASE_URL` for PostgreSQL)
- Jinja2 + Bootstrap 5

## Run

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5001

### Default login

- Email: `admin@mabuya.local`
- Password: `admin123`

Change these via `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, and `SEED_ADMIN_NAME` env vars before first run.

### PostgreSQL

Install a PostgreSQL driver separately, then set `DATABASE_URL`:

```bash
pip install psycopg[binary]
set DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/mabuya_camp
python run.py
```

## Phase 1 features

- Login / logout
- Home dashboard with active project cards
- Create, view, edit projects
- Archive / restore / delete archived projects
- Project overview with module placeholders (To-dos, Messages, Schedule, Files, People)
