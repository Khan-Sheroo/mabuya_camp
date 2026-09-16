from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from mabuya_camp import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')  # admin | manager | member
    avatar = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)

    created_projects = db.relationship('Project', backref='creator', lazy=True, foreign_keys='Project.created_by')
    memberships = db.relationship('ProjectMember', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    @property
    def is_manager(self) -> bool:
        return self.role in ('admin', 'manager')

    @property
    def initials(self) -> str:
        parts = [p for p in (self.name or '').strip().split() if p]
        if not parts:
            return '?'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def __repr__(self):
        return f'<User {self.email}>'


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='active')  # active | archived
    color = db.Column(db.String(20), nullable=True, default='teal')
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    archived_at = db.Column(db.DateTime, nullable=True)

    members = db.relationship('ProjectMember', backref='project', lazy=True, cascade='all, delete-orphan')
    todos = db.relationship('Todo', backref='project', lazy=True, cascade='all, delete-orphan', order_by='Todo.position')
    folders = db.relationship('ProjectFolder', backref='project', lazy=True, cascade='all, delete-orphan')
    documents = db.relationship('ProjectDocument', backref='project', lazy=True, cascade='all, delete-orphan')
    events = db.relationship('ProjectEvent', backref='project', lazy=True, cascade='all, delete-orphan')
    message_categories = db.relationship('MessageCategory', backref='project', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ProjectMessage', backref='project', lazy=True, cascade='all, delete-orphan')

    @property
    def is_active(self) -> bool:
        return self.status == 'active'

    @property
    def is_archived(self) -> bool:
        return self.status == 'archived'

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def open_todos_count(self) -> int:
        return sum(1 for t in self.todos if not t.completed)

    @property
    def member_users(self):
        return [m.user for m in self.members if m.user and m.user.is_active]

    def __repr__(self):
        return f'<Project {self.name}>'


class ProjectMember(db.Model):
    __tablename__ = 'project_members'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')  # project-level role
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('project_id', 'user_id', name='uq_project_member'),
    )


class Todo(db.Model):
    __tablename__ = 'todos'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    creator = db.relationship('User', foreign_keys=[created_by])
    checklist_items = db.relationship(
        'TodoChecklistItem',
        backref='todo',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='TodoChecklistItem.position',
    )

    @property
    def open_checklist_count(self) -> int:
        return sum(1 for item in self.checklist_items if not item.completed and not item.archived)

    @property
    def checklist_count(self) -> int:
        return sum(1 for item in self.checklist_items if not item.archived)

    @property
    def active_checklist_items(self):
        return [item for item in self.checklist_items if not item.archived]

    @property
    def archived_checklist_items(self):
        return [item for item in self.checklist_items if item.archived]

    def __repr__(self):
        return f'<Todo {self.title}>'


class TodoChecklistItem(db.Model):
    __tablename__ = 'todo_checklist_items'

    id = db.Column(db.Integer, primary_key=True)
    todo_id = db.Column(db.Integer, db.ForeignKey('todos.id'), nullable=False, index=True)
    text = db.Column(db.String(500), nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    archived = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assignee = db.relationship('User', foreign_keys=[assigned_to])
    images = db.relationship(
        'TodoChecklistImage',
        backref='checklist_item',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='TodoChecklistImage.uploaded_at',
    )

    def __repr__(self):
        return f'<TodoChecklistItem {self.text}>'


class TodoChecklistImage(db.Model):
    __tablename__ = 'todo_checklist_images'

    id = db.Column(db.Integer, primary_key=True)
    checklist_item_id = db.Column(
        db.Integer, db.ForeignKey('todo_checklist_items.id'), nullable=False, index=True
    )
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def __repr__(self):
        return f'<TodoChecklistImage {self.original_filename}>'


class ProjectFolder(db.Model):
    __tablename__ = 'project_folders'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    documents = db.relationship('ProjectDocument', backref='folder', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('project_id', 'name', name='uq_project_folder_name'),
    )

    def to_dict(self, document_count=None):
        data = {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if document_count is not None:
            data['document_count'] = document_count
        return data


class ProjectDocument(db.Model):
    __tablename__ = 'project_documents'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    folder_id = db.Column(db.Integer, db.ForeignKey('project_folders.id'), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    label = db.Column(db.String(200), nullable=True)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def is_image(self) -> bool:
        ct = (self.content_type or '').lower()
        if ct.startswith('image/'):
            return True
        name = (self.original_filename or '').lower()
        return name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))

    def is_pdf(self) -> bool:
        ct = (self.content_type or '').lower()
        if ct == 'application/pdf':
            return True
        name = (self.original_filename or '').lower()
        return name.endswith('.pdf')

    def can_preview(self) -> bool:
        return self.is_image() or self.is_pdf()

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'folder_id': self.folder_id,
            'folder_name': self.folder.name if self.folder else '',
            'original_filename': self.original_filename,
            'content_type': self.content_type,
            'label': self.label or '',
            'file_size': self.file_size,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'is_image': self.is_image(),
            'is_pdf': self.is_pdf(),
            'can_preview': self.can_preview(),
        }


class ProjectEvent(db.Model):
    __tablename__ = 'project_events'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    subtitle = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    event_date = db.Column(db.Date, nullable=False, index=True)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    creator = db.relationship('User', foreign_keys=[created_by])
    assignees = db.relationship(
        'User',
        secondary='project_event_assignees',
        lazy='joined',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'title': self.title,
            'subtitle': self.subtitle or '',
            'notes': self.notes or '',
            'event_date': self.event_date.isoformat() if self.event_date else None,
            'completed': self.completed,
            'has_notes': bool((self.notes or '').strip()),
            'assignees': [
                {
                    'id': u.id,
                    'name': u.name,
                    'initials': u.initials,
                }
                for u in (self.assignees or [])
            ],
            'kind': 'event',
        }


class ProjectEventAssignee(db.Model):
    __tablename__ = 'project_event_assignees'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('project_events.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint('event_id', 'user_id', name='uq_event_assignee'),
    )


class MessageCategory(db.Model):
    __tablename__ = 'message_categories'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    messages = db.relationship('ProjectMessage', backref='category', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('project_id', 'name', name='uq_message_category_name'),
    )

    def to_dict(self, message_count=None):
        data = {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
        }
        if message_count is not None:
            data['message_count'] = message_count
        return data


class ProjectMessage(db.Model):
    __tablename__ = 'project_messages'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('message_categories.id'), nullable=True)
    title = db.Column(db.String(300), nullable=False)
    body = db.Column(db.Text, nullable=False, default='')
    is_draft = db.Column(db.Boolean, default=False, nullable=False)
    notify_mode = db.Column(db.String(20), nullable=False, default='subscribers')  # subscribers | select | none
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    creator = db.relationship('User', foreign_keys=[created_by])
    comments = db.relationship(
        'MessageComment',
        backref='message',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='MessageComment.created_at',
    )
    notify_users = db.relationship(
        'User',
        secondary='message_notify_users',
        lazy='joined',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else '',
            'title': self.title,
            'body': self.body or '',
            'is_draft': self.is_draft,
            'notify_mode': self.notify_mode,
            'created_by': self.created_by,
            'author_name': self.creator.name if self.creator else '',
            'author_initials': self.creator.initials if self.creator else '?',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'comment_count': len(self.comments or []),
        }


class MessageNotifyUser(db.Model):
    __tablename__ = 'message_notify_users'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('project_messages.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint('message_id', 'user_id', name='uq_message_notify_user'),
    )


class MessageComment(db.Model):
    __tablename__ = 'message_comments'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('project_messages.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    creator = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'body': self.body or '',
            'created_by': self.created_by,
            'author_name': self.creator.name if self.creator else '',
            'author_initials': self.creator.initials if self.creator else '?',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

