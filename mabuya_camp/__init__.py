from pathlib import Path
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'warning'


def create_app(config_object='config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Ensure SQLite instance folder exists
    instance_path = Path(app.root_path).parent / 'instance'
    instance_path.mkdir(parents=True, exist_ok=True)

    upload_root = Path(app.config['UPLOAD_FOLDER'])
    upload_root.mkdir(parents=True, exist_ok=True)
    (upload_root / 'checklist').mkdir(parents=True, exist_ok=True)
    (upload_root / 'projects').mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from mabuya_camp.models import (  # noqa: F401
        User, Project, ProjectMember, Todo, TodoChecklistItem, TodoChecklistImage,
        ProjectFolder, ProjectDocument, ProjectEvent, ProjectEventAssignee,
        MessageCategory, ProjectMessage, MessageComment, MessageNotifyUser,
    )

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from mabuya_camp.auth import auth_bp
    from mabuya_camp.projects import projects_bp, home_bp
    from mabuya_camp.team import team_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(team_bp)

    @app.template_filter('relative_time')
    def relative_time_filter(dt):
        if not dt:
            return ''
        from datetime import datetime
        now = datetime.utcnow()
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return 'just now'
        if seconds < 3600:
            mins = seconds // 60
            return f'{mins} minute{"s" if mins != 1 else ""} ago'
        if seconds < 86400:
            hours = seconds // 3600
            return f'{hours} hour{"s" if hours != 1 else ""} ago'
        if delta.days == 1:
            return 'yesterday'
        if delta.days < 7:
            return f'{delta.days} days ago'
        return dt.strftime('%b %d, %Y')

    with app.app_context():
        db.create_all()
        _ensure_schema()
        _seed_admin(app)

    return app


def _ensure_schema():
    """Add columns introduced after initial create_all (SQLite-friendly)."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if 'todo_checklist_items' in tables:
        cols = {c['name'] for c in inspector.get_columns('todo_checklist_items')}
        alterations = []
        if 'archived' not in cols:
            alterations.append(
                'ALTER TABLE todo_checklist_items ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0'
            )
        if 'assigned_to' not in cols:
            alterations.append(
                'ALTER TABLE todo_checklist_items ADD COLUMN assigned_to INTEGER'
            )
        if 'due_date' not in cols:
            alterations.append(
                'ALTER TABLE todo_checklist_items ADD COLUMN due_date DATE'
            )
        if 'notes' not in cols:
            alterations.append(
                'ALTER TABLE todo_checklist_items ADD COLUMN notes TEXT'
            )
        for stmt in alterations:
            db.session.execute(text(stmt))
        if alterations:
            db.session.commit()

    if 'users' in tables:
        cols = {c['name'] for c in inspector.get_columns('users')}
        if 'is_active' not in cols:
            db.session.execute(
                text('ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1')
            )
            db.session.commit()

    if 'project_messages' in tables:
        cols = {c['name'] for c in inspector.get_columns('project_messages')}
        msg_alters = []
        if 'is_draft' not in cols:
            msg_alters.append(
                'ALTER TABLE project_messages ADD COLUMN is_draft BOOLEAN NOT NULL DEFAULT 0'
            )
        if 'notify_mode' not in cols:
            msg_alters.append(
                "ALTER TABLE project_messages ADD COLUMN notify_mode VARCHAR(20) NOT NULL DEFAULT 'subscribers'"
            )
        for stmt in msg_alters:
            db.session.execute(text(stmt))
        if msg_alters:
            db.session.commit()


def _seed_admin(app):
    from mabuya_camp.models import User

    email = app.config['SEED_ADMIN_EMAIL']
    if User.query.filter_by(email=email).first():
        return

    admin = User(
        name=app.config['SEED_ADMIN_NAME'],
        email=email,
        role='admin',
    )
    admin.set_password(app.config['SEED_ADMIN_PASSWORD'])
    db.session.add(admin)
    db.session.commit()
