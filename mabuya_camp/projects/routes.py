import re
import calendar
from datetime import datetime, date, timedelta
from flask import (
    render_template, redirect, url_for, flash, request, abort, jsonify,
    current_app, send_from_directory,
)
from flask_login import login_required, current_user
from mabuya_camp import db
from mabuya_camp.projects import projects_bp, home_bp
from mabuya_camp.models import (
    Project, ProjectMember, Todo, TodoChecklistItem, TodoChecklistImage, User,
    ProjectMessage, ProjectFolder, ProjectDocument, ProjectEvent,
)
from config import PROJECT_COLORS, DEFAULT_PROJECT_COLOR
from pathlib import Path
from uuid import uuid4
from werkzeug.utils import secure_filename
import mimetypes


ALLOWED_CHECKLIST_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}


def _slugify(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return slug or 'project'


def _unique_slug(name: str, exclude_id=None) -> str:
    base = _slugify(name)
    slug = base
    n = 2
    while True:
        q = Project.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(Project.id != exclude_id)
        if not q.first():
            return slug
        slug = f'{base}-{n}'
        n += 1


def _parse_date(value: str):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _accessible_projects_query():
    """Admins see all projects; others see projects they belong to."""
    q = Project.query
    if not current_user.is_admin:
        q = q.join(ProjectMember).filter(ProjectMember.user_id == current_user.id)
    return q


def _get_accessible_project(project_id: int) -> Project:
    project = Project.query.get_or_404(project_id)
    if current_user.is_admin:
        return project
    membership = ProjectMember.query.filter_by(
        project_id=project.id, user_id=current_user.id
    ).first()
    if not membership:
        abort(403)
    return project


def _can_manage_project(project: Project) -> bool:
    if current_user.is_admin:
        return True
    if current_user.role == 'manager':
        return ProjectMember.query.filter_by(
            project_id=project.id, user_id=current_user.id
        ).first() is not None
    return False


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return 'Good morning'
    if hour < 17:
        return 'Good afternoon'
    return 'Good evening'


# ── Home ──────────────────────────────────────────────────────────────

@home_bp.route('/')
@login_required
def index():
    projects = (
        _accessible_projects_query()
        .filter(Project.status == 'active')
        .order_by(Project.updated_at.desc())
        .all()
    )
    archived_count = (
        _accessible_projects_query()
        .filter(Project.status == 'archived')
        .count()
    )
    # Stand-in until a full activity feed exists
    recent_activity = []
    for project in projects[:8]:
        if project.created_at and project.updated_at and project.created_at == project.updated_at:
            text = 'Project created'
        else:
            text = 'Project updated'
        recent_activity.append({
            'project': project,
            'text': text,
            'at': project.updated_at,
        })
    return render_template(
        'home.html',
        projects=projects,
        archived_count=archived_count,
        greeting=_greeting(),
        colors=PROJECT_COLORS,
        recent_activity=recent_activity,
        manageable_ids={p.id for p in projects if _can_manage_project(p)},
    )


# ── Projects directory ────────────────────────────────────────────────

@projects_bp.route('/')
@login_required
def index():
    projects = (
        _accessible_projects_query()
        .filter(Project.status == 'active')
        .order_by(Project.updated_at.desc())
        .all()
    )
    return render_template(
        'projects/index.html',
        projects=projects,
        colors=PROJECT_COLORS,
        manageable_ids={p.id for p in projects if _can_manage_project(p)},
    )


@projects_bp.route('/archived')
@login_required
def archived():
    projects = (
        _accessible_projects_query()
        .filter(Project.status == 'archived')
        .order_by(Project.archived_at.desc())
        .all()
    )
    return render_template(
        'projects/archived.html',
        projects=projects,
        colors=PROJECT_COLORS,
    )


# ── Create ────────────────────────────────────────────────────────────

@projects_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role == 'member':
        flash('You do not have permission to create projects.', 'error')
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip() or None
        color = request.form.get('color') or DEFAULT_PROJECT_COLOR
        if color not in PROJECT_COLORS:
            color = DEFAULT_PROJECT_COLOR
        start_date = _parse_date(request.form.get('start_date'))
        end_date = _parse_date(request.form.get('end_date'))

        if not name:
            flash('Project name is required.', 'error')
            return render_template(
                'projects/create.html',
                colors=PROJECT_COLORS,
                form=request.form,
            )

        project = Project(
            name=name,
            description=description,
            slug=_unique_slug(name),
            status='active',
            color=color,
            start_date=start_date,
            end_date=end_date,
            created_by=current_user.id,
        )
        db.session.add(project)
        db.session.flush()
        db.session.add(ProjectMember(
            project_id=project.id,
            user_id=current_user.id,
            role='owner',
        ))
        db.session.commit()
        flash(f'Project "{project.name}" created.', 'success')
        return redirect(url_for('projects.dashboard', project_id=project.id))

    return render_template('projects/create.html', colors=PROJECT_COLORS, form={})


# ── Dashboard ─────────────────────────────────────────────────────────

def _plain_text_excerpt(html: str, limit: int = 72) -> str:
    text = re.sub(r'<[^>]+>', ' ', html or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '…'


def _dashboard_previews(project):
    """Gather compact live previews for each project module tile."""
    today = date.today()

    # Messages — recent published posts
    recent_messages = (
        ProjectMessage.query
        .filter_by(project_id=project.id, is_draft=False)
        .order_by(ProjectMessage.created_at.desc(), ProjectMessage.id.desc())
        .limit(4)
        .all()
    )
    message_previews = [
        {
            'title': msg.title,
            'excerpt': _plain_text_excerpt(msg.body),
            'initials': msg.creator.initials if msg.creator else '?',
            'author': msg.creator.name if msg.creator else '',
        }
        for msg in recent_messages
    ]

    # To-dos — open lists with a few open checklist items each
    open_lists = (
        Todo.query
        .filter_by(project_id=project.id, completed=False)
        .order_by(Todo.position.asc(), Todo.created_at.desc())
        .all()
    )
    todo_previews = []
    rows_budget = 10
    for todo in open_lists:
        if rows_budget <= 0:
            break
        open_items = [
            item for item in todo.active_checklist_items if not item.completed
        ][: max(1, min(4, rows_budget - 1))]
        todo_previews.append({
            'title': todo.title,
            'tasks': [{'text': item.text, 'completed': item.completed} for item in open_items],
        })
        rows_budget -= 1 + len(open_items)

    # Docs & files — folders with item counts
    folders = (
        ProjectFolder.query
        .filter_by(project_id=project.id)
        .order_by(ProjectFolder.name.asc())
        .limit(6)
        .all()
    )
    folder_previews = []
    for folder in folders:
        count = ProjectDocument.query.filter_by(
            project_id=project.id, folder_id=folder.id
        ).count()
        folder_previews.append({'name': folder.name, 'count': count})
    unfiled_count = ProjectDocument.query.filter_by(
        project_id=project.id, folder_id=None
    ).count()
    if not folder_previews and unfiled_count:
        folder_previews.append({'name': 'Unfiled', 'count': unfiled_count})

    # Schedule — mini month + upcoming events / due items
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    month_events = (
        ProjectEvent.query
        .filter(
            ProjectEvent.project_id == project.id,
            ProjectEvent.event_date >= month_start,
            ProjectEvent.event_date <= month_end,
        )
        .all()
    )
    month_dues = (
        TodoChecklistItem.query
        .join(Todo)
        .filter(
            Todo.project_id == project.id,
            TodoChecklistItem.archived.is_(False),
            TodoChecklistItem.due_date.isnot(None),
            TodoChecklistItem.due_date >= month_start,
            TodoChecklistItem.due_date <= month_end,
        )
        .all()
    )
    marked_days = {e.event_date.day for e in month_events} | {
        d.due_date.day for d in month_dues if d.due_date
    }

    upcoming_events = (
        ProjectEvent.query
        .filter(
            ProjectEvent.project_id == project.id,
            ProjectEvent.event_date >= today,
        )
        .order_by(ProjectEvent.event_date.asc(), ProjectEvent.id.asc())
        .limit(4)
        .all()
    )
    upcoming_dues = (
        TodoChecklistItem.query
        .join(Todo)
        .filter(
            Todo.project_id == project.id,
            TodoChecklistItem.archived.is_(False),
            TodoChecklistItem.completed.is_(False),
            TodoChecklistItem.due_date.isnot(None),
            TodoChecklistItem.due_date >= today,
        )
        .order_by(TodoChecklistItem.due_date.asc(), TodoChecklistItem.id.asc())
        .limit(4)
        .all()
    )
    upcoming = []
    for ev in upcoming_events:
        upcoming.append({
            'title': ev.title,
            'date': ev.event_date,
            'completed': ev.completed,
            'kind': 'event',
        })
    for item in upcoming_dues:
        upcoming.append({
            'title': item.text,
            'date': item.due_date,
            'completed': item.completed,
            'kind': 'todo',
        })
    upcoming.sort(key=lambda x: (x['date'], 0 if x['kind'] == 'event' else 1))
    upcoming = upcoming[:4]

    cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
    return {
        'messages': message_previews,
        'todos': todo_previews,
        'folders': folder_previews,
        'schedule': {
            'year': today.year,
            'month': today.month,
            'month_name': calendar.month_name[today.month],
            'today': today.day,
            'weeks': cal.monthdayscalendar(today.year, today.month),
            'marked_days': marked_days,
            'upcoming': upcoming,
        },
    }


@projects_bp.route('/<int:project_id>')
@login_required
def dashboard(project_id):
    project = _get_accessible_project(project_id)
    return render_template(
        'projects/dashboard.html',
        project=project,
        colors=PROJECT_COLORS,
        can_manage=_can_manage_project(project),
        active_tab='overview',
        previews=_dashboard_previews(project),
    )


# ── Edit ──────────────────────────────────────────────────────────────

@projects_bp.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(project_id):
    project = _get_accessible_project(project_id)
    if not _can_manage_project(project):
        flash('You do not have permission to edit this project.', 'error')
        return redirect(url_for('projects.dashboard', project_id=project.id))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip() or None
        color = request.form.get('color') or project.color or DEFAULT_PROJECT_COLOR
        if color not in PROJECT_COLORS:
            color = DEFAULT_PROJECT_COLOR
        start_date = _parse_date(request.form.get('start_date'))
        end_date = _parse_date(request.form.get('end_date'))

        if not name:
            flash('Project name is required.', 'error')
            return render_template(
                'projects/edit.html',
                project=project,
                colors=PROJECT_COLORS,
            )

        if name != project.name:
            project.slug = _unique_slug(name, exclude_id=project.id)
        project.name = name
        project.description = description
        project.color = color
        project.start_date = start_date
        project.end_date = end_date
        project.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Project updated.', 'success')
        return redirect(url_for('projects.dashboard', project_id=project.id))

    return render_template(
        'projects/edit.html',
        project=project,
        colors=PROJECT_COLORS,
    )


# ── Colour ────────────────────────────────────────────────────────────

@projects_bp.route('/<int:project_id>/color', methods=['POST'])
@login_required
def set_color(project_id):
    project = _get_accessible_project(project_id)
    if not _can_manage_project(project):
        return jsonify({'ok': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    color = (payload.get('color') or request.form.get('color') or '').strip()
    if color not in PROJECT_COLORS:
        return jsonify({'ok': False, 'error': 'Invalid colour'}), 400

    project.color = color
    project.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({
        'ok': True,
        'color': color,
        'hex': PROJECT_COLORS[color],
    })


# ── Archive / Restore / Delete ────────────────────────────────────────

@projects_bp.route('/<int:project_id>/archive', methods=['POST'])
@login_required
def archive(project_id):
    project = _get_accessible_project(project_id)
    if not _can_manage_project(project):
        flash('You do not have permission to archive this project.', 'error')
        return redirect(url_for('projects.dashboard', project_id=project.id))

    project.status = 'archived'
    project.archived_at = datetime.utcnow()
    project.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f'Project "{project.name}" archived.', 'success')
    return redirect(url_for('home.index'))


@projects_bp.route('/<int:project_id>/restore', methods=['POST'])
@login_required
def restore(project_id):
    project = _get_accessible_project(project_id)
    if not _can_manage_project(project):
        flash('You do not have permission to restore this project.', 'error')
        return redirect(url_for('projects.archived'))

    project.status = 'active'
    project.archived_at = None
    project.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f'Project "{project.name}" restored.', 'success')
    return redirect(url_for('projects.dashboard', project_id=project.id))


@projects_bp.route('/<int:project_id>/delete', methods=['POST'])
@login_required
def delete(project_id):
    project = _get_accessible_project(project_id)
    if not current_user.is_admin and not _can_manage_project(project):
        flash('You do not have permission to delete this project.', 'error')
        return redirect(url_for('projects.archived'))

    if project.status != 'archived':
        flash('Only archived projects can be permanently deleted.', 'error')
        return redirect(url_for('projects.dashboard', project_id=project.id))

    name = project.name
    db.session.delete(project)
    db.session.commit()
    flash(f'Project "{name}" permanently deleted.', 'success')
    return redirect(url_for('projects.archived'))


# ── To-dos ────────────────────────────────────────────────────────────

def _get_project_todo(project_id: int, todo_id: int) -> tuple[Project, Todo]:
    project = _get_accessible_project(project_id)
    todo = Todo.query.filter_by(id=todo_id, project_id=project.id).first_or_404()
    return project, todo


def _touch_project(project: Project) -> None:
    project.updated_at = datetime.utcnow()


def _checklist_upload_dir(project_id: int, todo_id: int, item_id: int) -> Path:
    path = (
        Path(current_app.config['UPLOAD_FOLDER'])
        / 'checklist'
        / str(project_id)
        / str(todo_id)
        / str(item_id)
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_allowed_checklist_image(filename: str) -> bool:
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_CHECKLIST_IMAGE_EXTENSIONS
    )


def _save_checklist_images(project: Project, todo: Todo, item: TodoChecklistItem, files) -> int:
    saved = 0
    upload_dir = _checklist_upload_dir(project.id, todo.id, item.id)
    for file in files:
        if not file or not file.filename:
            continue
        if not _is_allowed_checklist_image(file.filename):
            continue
        original = secure_filename(file.filename) or 'image'
        ext = original.rsplit('.', 1)[-1].lower()
        stored = f'{uuid4().hex}.{ext}'
        dest = upload_dir / stored
        file.save(dest)
        content_type = file.content_type or mimetypes.guess_type(original)[0]
        db.session.add(TodoChecklistImage(
            checklist_item_id=item.id,
            original_filename=original,
            stored_filename=stored,
            content_type=content_type,
            file_size=dest.stat().st_size if dest.exists() else 0,
            uploaded_by=current_user.id,
        ))
        saved += 1
    return saved


def _delete_checklist_image_files(project_id: int, todo_id: int, item: TodoChecklistItem) -> None:
    folder = (
        Path(current_app.config['UPLOAD_FOLDER'])
        / 'checklist'
        / str(project_id)
        / str(todo_id)
        / str(item.id)
    )
    for image in list(item.images):
        path = folder / image.stored_filename
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    if folder.exists():
        try:
            folder.rmdir()
        except OSError:
            pass


@projects_bp.route('/<int:project_id>/todos')
@login_required
def todos(project_id):
    project = _get_accessible_project(project_id)
    todo_list = (
        Todo.query
        .filter_by(project_id=project.id)
        .order_by(Todo.completed.asc(), Todo.position.asc(), Todo.created_at.desc())
        .all()
    )
    members = (
        User.query
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .filter(ProjectMember.project_id == project.id)
        .order_by(User.name.asc())
        .all()
    )
    if current_user.is_admin and current_user.id not in {m.id for m in members}:
        members = [current_user] + list(members)
    return render_template(
        'projects/todos.html',
        project=project,
        colors=PROJECT_COLORS,
        can_manage=_can_manage_project(project),
        active_tab='todos',
        todos=todo_list,
        members=members,
    )


@projects_bp.route('/<int:project_id>/todos', methods=['POST'])
@login_required
def create_todo(project_id):
    project = _get_accessible_project(project_id)
    title = (request.form.get('title') or '').strip()
    if not title:
        flash('To-do title is required.', 'error')
        return redirect(url_for('projects.todos', project_id=project.id))

    max_pos = db.session.query(db.func.max(Todo.position)).filter_by(project_id=project.id).scalar() or 0
    todo = Todo(
        project_id=project.id,
        title=title,
        position=max_pos + 1,
        created_by=current_user.id,
    )
    db.session.add(todo)
    _touch_project(project)
    db.session.commit()
    flash('List added.', 'success')
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))


@projects_bp.route('/<int:project_id>/todos/<int:todo_id>/toggle', methods=['POST'])
@login_required
def toggle_todo(project_id, todo_id):
    project, todo = _get_project_todo(project_id, todo_id)
    todo.completed = not todo.completed
    todo.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))


@projects_bp.route('/<int:project_id>/todos/<int:todo_id>/delete', methods=['POST'])
@login_required
def delete_todo(project_id, todo_id):
    project, todo = _get_project_todo(project_id, todo_id)
    for item in list(todo.checklist_items):
        _delete_checklist_image_files(project.id, todo.id, item)
    db.session.delete(todo)
    _touch_project(project)
    db.session.commit()
    flash('List deleted.', 'success')
    return redirect(url_for('projects.todos', project_id=project.id))


@projects_bp.route('/<int:project_id>/todos/<int:todo_id>/checklist', methods=['POST'])
@login_required
def add_checklist_item(project_id, todo_id):
    project, todo = _get_project_todo(project_id, todo_id)
    text = (request.form.get('text') or '').strip()
    if not text:
        flash('Checklist item text is required.', 'error')
        return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))

    max_pos = (
        db.session.query(db.func.max(TodoChecklistItem.position))
        .filter_by(todo_id=todo.id)
        .scalar()
        or 0
    )
    item = TodoChecklistItem(todo_id=todo.id, text=text, position=max_pos + 1)
    db.session.add(item)
    todo.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))


@projects_bp.route(
    '/<int:project_id>/todos/<int:todo_id>/checklist/<int:item_id>/toggle',
    methods=['POST'],
)
@login_required
def toggle_checklist_item(project_id, todo_id, item_id):
    project, todo = _get_project_todo(project_id, todo_id)
    item = TodoChecklistItem.query.filter_by(id=item_id, todo_id=todo.id).first_or_404()
    item.completed = not item.completed
    todo.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))


@projects_bp.route(
    '/<int:project_id>/todos/<int:todo_id>/checklist/<int:item_id>/edit',
    methods=['POST'],
)
@login_required
def edit_checklist_item(project_id, todo_id, item_id):
    project, todo = _get_project_todo(project_id, todo_id)
    item = TodoChecklistItem.query.filter_by(id=item_id, todo_id=todo.id).first_or_404()
    text = (request.form.get('text') or '').strip()
    if not text:
        flash('To-do text is required.', 'error')
        return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))

    assignee_raw = (request.form.get('assigned_to') or '').strip()
    assigned_to = None
    if assignee_raw:
        try:
            assigned_to = int(assignee_raw)
        except ValueError:
            assigned_to = None
        if assigned_to is not None:
            member = ProjectMember.query.filter_by(
                project_id=project.id, user_id=assigned_to
            ).first()
            if not member and not (
                current_user.is_admin and assigned_to == current_user.id
            ):
                flash('Assignee must be a project member.', 'error')
                return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))

    item.text = text
    item.assigned_to = assigned_to
    item.due_date = _parse_date(request.form.get('due_date'))
    notes = (request.form.get('notes') or '').strip()
    item.notes = notes or None

    files = request.files.getlist('images')
    _save_checklist_images(project, todo, item, files)

    todo.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'checklist-{item.id}'))


@projects_bp.route(
    '/<int:project_id>/todos/<int:todo_id>/checklist/<int:item_id>/images/<int:image_id>',
    methods=['GET'],
)
@login_required
def checklist_image(project_id, todo_id, item_id, image_id):
    project, todo = _get_project_todo(project_id, todo_id)
    item = TodoChecklistItem.query.filter_by(id=item_id, todo_id=todo.id).first_or_404()
    image = TodoChecklistImage.query.filter_by(
        id=image_id, checklist_item_id=item.id
    ).first_or_404()
    folder = _checklist_upload_dir(project.id, todo.id, item.id)
    return send_from_directory(
        folder,
        image.stored_filename,
        mimetype=image.content_type,
        download_name=image.original_filename,
    )


@projects_bp.route(
    '/<int:project_id>/todos/<int:todo_id>/checklist/<int:item_id>/images/<int:image_id>/delete',
    methods=['POST'],
)
@login_required
def delete_checklist_image(project_id, todo_id, item_id, image_id):
    project, todo = _get_project_todo(project_id, todo_id)
    item = TodoChecklistItem.query.filter_by(id=item_id, todo_id=todo.id).first_or_404()
    image = TodoChecklistImage.query.filter_by(
        id=image_id, checklist_item_id=item.id
    ).first_or_404()
    folder = _checklist_upload_dir(project.id, todo.id, item.id)
    path = folder / image.stored_filename
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    db.session.delete(image)
    todo.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'checklist-{item.id}'))


@projects_bp.route(
    '/<int:project_id>/todos/<int:todo_id>/checklist/<int:item_id>/archive',
    methods=['POST'],
)
@login_required
def archive_checklist_item(project_id, todo_id, item_id):
    project, todo = _get_project_todo(project_id, todo_id)
    item = TodoChecklistItem.query.filter_by(id=item_id, todo_id=todo.id).first_or_404()
    item.archived = not item.archived
    todo.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))


@projects_bp.route(
    '/<int:project_id>/todos/<int:todo_id>/checklist/<int:item_id>/delete',
    methods=['POST'],
)
@login_required
def delete_checklist_item(project_id, todo_id, item_id):
    project, todo = _get_project_todo(project_id, todo_id)
    item = TodoChecklistItem.query.filter_by(id=item_id, todo_id=todo.id).first_or_404()
    _delete_checklist_image_files(project.id, todo.id, item)
    db.session.delete(item)
    todo.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.todos', project_id=project.id, _anchor=f'todo-{todo.id}'))


# ── People ─────────────────────────────────────────────────────────────

def _project_memberships(project):
    return (
        ProjectMember.query
        .filter_by(project_id=project.id)
        .join(User, User.id == ProjectMember.user_id)
        .order_by(ProjectMember.role.asc(), User.name.asc())
        .all()
    )


def _available_team_users(project):
    member_ids = {m.user_id for m in project.members}
    q = User.query.filter_by(is_active=True).order_by(User.name.asc())
    if member_ids:
        q = q.filter(~User.id.in_(member_ids))
    return q.all()


@projects_bp.route('/<int:project_id>/people')
@login_required
def people(project_id):
    project = _get_accessible_project(project_id)
    can_manage = _can_manage_project(project)
    memberships = _project_memberships(project)
    return render_template(
        'projects/people.html',
        project=project,
        colors=PROJECT_COLORS,
        can_manage=can_manage,
        active_tab='people',
        memberships=memberships,
        available_users=_available_team_users(project) if can_manage else [],
    )


@projects_bp.route('/<int:project_id>/people/add', methods=['POST'])
@login_required
def add_project_person(project_id):
    project = _get_accessible_project(project_id)
    if not _can_manage_project(project):
        flash('You do not have permission to add people to this project.', 'error')
        return redirect(url_for('projects.people', project_id=project.id))

    try:
        user_id = int(request.form.get('user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    user = User.query.get(user_id)
    if not user:
        flash('Choose someone from the team.', 'error')
        return redirect(url_for('projects.people', project_id=project.id))

    existing = ProjectMember.query.filter_by(
        project_id=project.id, user_id=user.id
    ).first()
    if existing:
        flash(f'{user.name} is already on this project.', 'error')
        return redirect(url_for('projects.people', project_id=project.id))

    db.session.add(ProjectMember(
        project_id=project.id,
        user_id=user.id,
        role='member',
    ))
    _touch_project(project)
    db.session.commit()
    flash(f'{user.name} was added to the project.', 'success')
    return redirect(url_for('projects.people', project_id=project.id))


@projects_bp.route('/<int:project_id>/people/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_project_person(project_id, user_id):
    project = _get_accessible_project(project_id)
    if not _can_manage_project(project):
        flash('You do not have permission to remove people from this project.', 'error')
        return redirect(url_for('projects.people', project_id=project.id))

    membership = ProjectMember.query.filter_by(
        project_id=project.id, user_id=user_id
    ).first_or_404()
    user = membership.user

    if ProjectMember.query.filter_by(project_id=project.id).count() <= 1:
        flash('A project needs at least one person.', 'error')
        return redirect(url_for('projects.people', project_id=project.id))

    if membership.role == 'owner':
        next_member = (
            ProjectMember.query
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id != user_id,
            )
            .order_by(ProjectMember.created_at.asc())
            .first()
        )
        if next_member and not ProjectMember.query.filter(
            ProjectMember.project_id == project.id,
            ProjectMember.role == 'owner',
            ProjectMember.user_id != user_id,
        ).first():
            next_member.role = 'owner'

    db.session.delete(membership)
    _touch_project(project)
    db.session.commit()
    flash(f'{user.name if user else "Person"} was removed from the project.', 'success')
    return redirect(url_for('projects.people', project_id=project.id))
