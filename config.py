import os
from pathlib import Path


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mabuya-camp-dev-secret-change-me')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Prefer DATABASE_URL (e.g. postgresql://...); fall back to SQLite for local dev
    _db_path = Path(__file__).resolve().parent / 'instance' / 'mabuya_camp.db'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///' + _db_path.as_posix())

    # Default admin seeded on first run (change in production)
    SEED_ADMIN_EMAIL = os.environ.get('SEED_ADMIN_EMAIL', 'admin@mabuya.local')
    SEED_ADMIN_PASSWORD = os.environ.get('SEED_ADMIN_PASSWORD', 'admin123')
    SEED_ADMIN_NAME = os.environ.get('SEED_ADMIN_NAME', 'Admin')

    _upload_root = Path(__file__).resolve().parent / 'uploads'
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', str(_upload_root))
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB


# Eight secondary palette colours for project cards
PROJECT_COLORS = {
    'coral': '#E07A5F',
    'teal': '#2A9D8F',
    'violet': '#7B6CF6',
    'amber': '#E9A319',
    'rose': '#E85D75',
    'sage': '#84A98C',
    'indigo': '#5C6BC0',
    'cyan': '#4ECDC4',
}

DEFAULT_PROJECT_COLOR = 'teal'
