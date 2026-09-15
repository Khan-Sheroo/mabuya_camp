"""Project Schedule / Calendar routes."""
from datetime import date, datetime, timedelta
from calendar import month_abbr

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from mabuya_camp import db
from mabuya_camp.projects import projects_bp
from mabuya_camp.projects.routes import _get_accessible_project, _can_manage_project, _touch_project
from mabuya_camp.models import ProjectEvent, TodoChecklistItem, Todo, User
from config import PROJECT_COLORS

WEEKDAYS = ('SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT')
WEEKS_VISIBLE = 6


def _sunday_on_or_before(d: date) -> date:
    # Python weekday(): Mon=0 … Sun=6 → days since Sunday
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _parse_anchor(raw) -> date:
    if not raw:
        return date.today()
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return date.today()


def _window_for_anchor(anchor: date):
    start = _sunday_on_or_before(anchor)
    days = [start + timedelta(days=i) for i in range(WEEKS_VISIBLE * 7)]
    end = days[-1]
    return start, end, days


def _parse_assignee_ids(raw_list, project) -> list:
    member_ids = {m.user_id for m in project.members}
    ids = []
    for raw in raw_list or []:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid in member_ids:
            ids.append(uid)
    return ids


def _set_event_assignees(event: ProjectEvent, user_ids: list) -> None:
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    # Preserve order of requested ids
    by_id = {u.id: u for u in users}
    event.assignees = [by_id[uid] for uid in user_ids if uid in by_id]


def _events_in_range(project_id: int, start: date, end: date):
    return (
        ProjectEvent.query
        .filter(
            ProjectEvent.project_id == project_id,
            ProjectEvent.event_date >= start,
            ProjectEvent.event_date <= end,
        )
        .order_by(ProjectEvent.event_date, ProjectEvent.id)
        .all()
    )


def _due_todos_in_range(project_id: int, start: date, end: date):
    return (
        TodoChecklistItem.query
        .join(Todo)
        .filter(
            Todo.project_id == project_id,
            TodoChecklistItem.archived.is_(False),
            TodoChecklistItem.due_date.isnot(None),
            TodoChecklistItem.due_date >= start,
            TodoChecklistItem.due_date <= end,
        )
        .order_by(TodoChecklistItem.due_date, TodoChecklistItem.id)
        .all()
    )


def _todo_item_payload(item: TodoChecklistItem) -> dict:
    assignees = []
    if item.assignee:
        assignees = [{
            'id': item.assignee.id,
            'name': item.assignee.name,
            'initials': item.assignee.initials,
        }]
    return {
        'id': item.id,
        'todo_id': item.todo_id,
        'title': item.text,
        'subtitle': item.todo.title if item.todo else '',
        'notes': item.notes or '',
        'event_date': item.due_date.isoformat() if item.due_date else None,
        'completed': item.completed,
        'has_notes': bool((item.notes or '').strip()),
        'assignees': assignees,
        'kind': 'todo',
    }


def _items_by_date(events, todo_items) -> dict:
    buckets = {}
    for event in events:
        key = event.event_date.isoformat()
        buckets.setdefault(key, []).append(event.to_dict())
    for item in todo_items:
        key = item.due_date.isoformat()
        buckets.setdefault(key, []).append(_todo_item_payload(item))
    return buckets


def _build_weeks(days, items_by_day, today: date):
    weeks = []
    for i in range(0, len(days), 7):
        week = []
        for d in days[i:i + 7]:
            is_today = d == today
            is_month_start = d.day == 1
            label = ''
            if is_today:
                label = f'Today, {month_abbr[d.month]} {d.day}'
            elif is_month_start:
                label = f'{month_abbr[d.month]} {d.day}, {d.year}'
            week.append({
                'date': d,
                'iso': d.isoformat(),
                'day': d.day,
                'is_today': is_today,
                'is_month_start': is_month_start,
                'label': label,
                'day_items': items_by_day.get(d.isoformat(), []),
            })
        weeks.append(week)
    return weeks


def _nav_label(start: date, today: date) -> str:
    current_start = _sunday_on_or_before(today)
    if start == current_start:
        return 'Next 6 Weeks'
    if start < current_start:
        return 'Previous 6 Weeks'
    return start.strftime('%b %d, %Y')


def _weeks_payload(project_id: int, anchor: date, weeks_count: int, today: date):
    start = _sunday_on_or_before(anchor)
    days = [start + timedelta(days=i) for i in range(weeks_count * 7)]
    end = days[-1]
    events = _events_in_range(project_id, start, end)
    todos = _due_todos_in_range(project_id, start, end)
    items_by_day = _items_by_date(events, todos)
    weeks = _build_weeks(days, items_by_day, today)
    html = render_template('projects/_schedule_weeks.html', weeks=weeks)
    return {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'next_start': (end + timedelta(days=1)).isoformat(),
        'prev_start': (start - timedelta(days=weeks_count * 7)).isoformat(),
        'nav_label': _nav_label(start, today),
        'html': html,
        'weeks_count': weeks_count,
    }


@projects_bp.route('/<int:project_id>/schedule')
@login_required
def schedule(project_id):
    project = _get_accessible_project(project_id)
    today = date.today()
    anchor = _parse_anchor(request.args.get('start'))
    # Snap to Sunday of requested week
    start, end, days = _window_for_anchor(anchor)
    events = _events_in_range(project.id, start, end)
    todos = _due_todos_in_range(project.id, start, end)
    items_by_day = _items_by_date(events, todos)
    weeks = _build_weeks(days, items_by_day, today)

    prev_start = (start - timedelta(days=WEEKS_VISIBLE * 7)).isoformat()
    next_start = (start + timedelta(days=WEEKS_VISIBLE * 7)).isoformat()

    # Agenda: upcoming from today within a wider window (current + next)
    agenda_end = today + timedelta(days=WEEKS_VISIBLE * 7 * 2)
    agenda_events = _events_in_range(project.id, today, agenda_end)
    agenda_todos = _due_todos_in_range(project.id, today, agenda_end)
    agenda_items = []
    for e in agenda_events:
        payload = e.to_dict()
        payload['display_date'] = e.event_date.strftime('%d %b %Y')
        agenda_items.append(payload)
    for t in agenda_todos:
        payload = _todo_item_payload(t)
        payload['display_date'] = t.due_date.strftime('%d %b %Y')
        agenda_items.append(payload)
    agenda_items.sort(key=lambda x: (x.get('event_date') or '', x.get('id') or 0))

    view = request.args.get('view', 'calendar')
    if view not in ('calendar', 'agenda'):
        view = 'calendar'

    return render_template(
        'projects/schedule.html',
        project=project,
        colors=PROJECT_COLORS,
        can_manage=_can_manage_project(project),
        weekdays=WEEKDAYS,
        weeks=weeks,
        window_start=start,
        window_end=end,
        prev_start=prev_start,
        next_start=next_start,
        nav_label=_nav_label(start, today),
        today=today,
        agenda_items=agenda_items,
        members=project.member_users,
        active_view=view,
    )


@projects_bp.route('/<int:project_id>/api/schedule/weeks')
@login_required
def api_schedule_weeks(project_id):
    project = _get_accessible_project(project_id)
    today = date.today()
    try:
        weeks_count = int(request.args.get('weeks', WEEKS_VISIBLE))
    except (TypeError, ValueError):
        weeks_count = WEEKS_VISIBLE
    weeks_count = max(1, min(weeks_count, 12))
    anchor = _parse_anchor(request.args.get('start'))
    payload = _weeks_payload(project.id, anchor, weeks_count, today)
    return jsonify({'success': True, **payload})


@projects_bp.route('/<int:project_id>/api/events', methods=['POST'])
@login_required
def api_create_event(project_id):
    project = _get_accessible_project(project_id)
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or request.form.get('title') or '').strip()[:300]
    if not title:
        return jsonify({'success': False, 'error': 'Title is required'}), 400

    raw_date = data.get('event_date') or request.form.get('event_date')
    try:
        event_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valid date is required'}), 400

    subtitle = (data.get('subtitle') or request.form.get('subtitle') or '').strip()[:200]
    notes = (data.get('notes') or request.form.get('notes') or '').strip()
    assignee_ids = data.get('assignee_ids')
    if assignee_ids is None:
        assignee_ids = request.form.getlist('assignee_ids')
    assignee_ids = _parse_assignee_ids(assignee_ids, project)

    event = ProjectEvent(
        project_id=project.id,
        title=title,
        subtitle=subtitle or None,
        notes=notes or None,
        event_date=event_date,
        created_by=current_user.id,
    )
    db.session.add(event)
    db.session.flush()
    _set_event_assignees(event, assignee_ids)
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True, 'event': event.to_dict()})


@projects_bp.route('/<int:project_id>/api/events/<int:event_id>', methods=['POST'])
@login_required
def api_update_event(project_id, event_id):
    project = _get_accessible_project(project_id)
    event = ProjectEvent.query.filter_by(id=event_id, project_id=project.id).first_or_404()
    data = request.get_json(silent=True) or {}

    if 'title' in data or request.form.get('title') is not None:
        title = (data.get('title') if 'title' in data else request.form.get('title') or '').strip()[:300]
        if not title:
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        event.title = title

    if 'subtitle' in data or request.form.get('subtitle') is not None:
        subtitle = (data.get('subtitle') if 'subtitle' in data else request.form.get('subtitle') or '').strip()[:200]
        event.subtitle = subtitle or None

    if 'notes' in data or request.form.get('notes') is not None:
        notes = (data.get('notes') if 'notes' in data else request.form.get('notes') or '').strip()
        event.notes = notes or None

    raw_date = data.get('event_date') if 'event_date' in data else request.form.get('event_date')
    if raw_date:
        try:
            event.event_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Valid date is required'}), 400

    if 'assignee_ids' in data or request.form.getlist('assignee_ids'):
        assignee_ids = data.get('assignee_ids') if 'assignee_ids' in data else request.form.getlist('assignee_ids')
        _set_event_assignees(event, _parse_assignee_ids(assignee_ids, project))

    event.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True, 'event': event.to_dict()})


@projects_bp.route('/<int:project_id>/api/events/<int:event_id>/toggle', methods=['POST'])
@login_required
def api_toggle_event(project_id, event_id):
    project = _get_accessible_project(project_id)
    event = ProjectEvent.query.filter_by(id=event_id, project_id=project.id).first_or_404()
    event.completed = not event.completed
    event.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True, 'event': event.to_dict()})


@projects_bp.route('/<int:project_id>/api/events/<int:event_id>/delete', methods=['POST'])
@login_required
def api_delete_event(project_id, event_id):
    project = _get_accessible_project(project_id)
    event = ProjectEvent.query.filter_by(id=event_id, project_id=project.id).first_or_404()
    event.assignees = []
    db.session.delete(event)
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True})
