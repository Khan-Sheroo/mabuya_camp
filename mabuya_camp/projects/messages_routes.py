"""Project Message Board routes."""
from datetime import datetime
import re

from flask import render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from mabuya_camp import db
from mabuya_camp.projects import projects_bp
from mabuya_camp.projects.routes import _get_accessible_project, _can_manage_project, _touch_project
from mabuya_camp.models import MessageCategory, ProjectMessage, MessageComment, User
from config import PROJECT_COLORS


def _normalize_category_name(name: str) -> str:
    return ' '.join((name or '').strip().split())[:120]


def _sanitize_message_html(html: str) -> str:
    text = html or ''
    text = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', text, flags=re.I | re.S)
    text = re.sub(r'\son\w+\s*=\s*([\'"]).*?\1', '', text, flags=re.I | re.S)
    text = re.sub(r'\son\w+\s*=\s*[^\s>]+', '', text, flags=re.I)
    text = re.sub(r'javascript:', '', text, flags=re.I)
    return text.strip()


def _plain_excerpt(html: str, limit: int = 160) -> str:
    text = re.sub(r'<[^>]+>', ' ', html or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '…'


def _categories_payload(project_id: int) -> list:
    cats = (
        MessageCategory.query
        .filter_by(project_id=project_id)
        .order_by(MessageCategory.name)
        .all()
    )
    payload = []
    for cat in cats:
        count = ProjectMessage.query.filter_by(
            project_id=project_id, category_id=cat.id, is_draft=False
        ).count()
        payload.append(cat.to_dict(message_count=count))
    return payload


def _resolve_category(project_id: int, category_id):
    if category_id in (None, '', 'null', 'none', '0'):
        return None
    try:
        cid = int(category_id)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid category') from exc
    cat = MessageCategory.query.filter_by(id=cid, project_id=project_id).first()
    if cat is None:
        raise ValueError('Category not found')
    return cat


def _parse_notify_mode(raw: str) -> str:
    mode = (raw or 'subscribers').strip().lower()
    if mode not in ('subscribers', 'select', 'none'):
        return 'subscribers'
    return mode


def _set_notify_users(message: ProjectMessage, project, mode: str, raw_ids) -> None:
    if mode != 'select':
        message.notify_users = []
        return
    member_ids = {m.user_id for m in project.members}
    ids = []
    for raw in raw_ids or []:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid in member_ids:
            ids.append(uid)
    users = User.query.filter(User.id.in_(ids)).all() if ids else []
    by_id = {u.id: u for u in users}
    message.notify_users = [by_id[uid] for uid in ids if uid in by_id]


def _form_context(project, categories, form, mode, message=None):
    members = project.member_users
    return dict(
        project=project,
        colors=PROJECT_COLORS,
        can_manage=_can_manage_project(project),
        categories=categories,
        form=form,
        mode=mode,
        message=message,
        members=members,
        member_count=len(members),
    )


@projects_bp.route('/<int:project_id>/messages')
@login_required
def messages(project_id):
    project = _get_accessible_project(project_id)
    category_filter = request.args.get('category', 'all')
    sort = request.args.get('sort', 'newest')
    if sort not in ('newest', 'oldest', 'title'):
        sort = 'newest'

    query = ProjectMessage.query.filter_by(project_id=project.id, is_draft=False)
    if category_filter not in ('', 'all', None):
        try:
            cid = int(category_filter)
            query = query.filter_by(category_id=cid)
        except ValueError:
            category_filter = 'all'

    if sort == 'oldest':
        query = query.order_by(ProjectMessage.created_at.asc(), ProjectMessage.id.asc())
    elif sort == 'title':
        query = query.order_by(ProjectMessage.title.asc(), ProjectMessage.id.asc())
    else:
        query = query.order_by(ProjectMessage.created_at.desc(), ProjectMessage.id.desc())

    message_list = query.all()
    drafts = (
        ProjectMessage.query
        .filter_by(project_id=project.id, is_draft=True, created_by=current_user.id)
        .order_by(ProjectMessage.updated_at.desc())
        .all()
    )
    categories = _categories_payload(project.id)

    return render_template(
        'projects/messages.html',
        project=project,
        colors=PROJECT_COLORS,
        can_manage=_can_manage_project(project),
        messages=message_list,
        drafts=drafts,
        categories=categories,
        category_filter=category_filter,
        sort=sort,
        plain_excerpt=_plain_excerpt,
    )


@projects_bp.route('/<int:project_id>/messages/new', methods=['GET', 'POST'])
@login_required
def new_message(project_id):
    project = _get_accessible_project(project_id)
    categories = _categories_payload(project.id)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:300]
        body = _sanitize_message_html(request.form.get('body') or '')
        is_draft = request.form.get('intent') == 'draft'
        notify_mode = _parse_notify_mode(request.form.get('notify_mode'))
        form = {
            'title': title,
            'body': body,
            'category_id': request.form.get('category_id') or '',
            'notify_mode': notify_mode,
            'notify_user_ids': request.form.getlist('notify_user_ids'),
        }
        if not title:
            flash('Title is required.', 'error')
            return render_template(
                'projects/message_form.html',
                **_form_context(project, categories, form, 'new'),
            )
        try:
            category = _resolve_category(project.id, form['category_id'])
        except ValueError:
            flash('Invalid category.', 'error')
            return redirect(url_for('projects.new_message', project_id=project.id))

        msg = ProjectMessage(
            project_id=project.id,
            category_id=category.id if category else None,
            title=title,
            body=body,
            is_draft=is_draft,
            notify_mode=notify_mode if not is_draft else 'none',
            created_by=current_user.id,
        )
        db.session.add(msg)
        db.session.flush()
        if not is_draft:
            _set_notify_users(msg, project, notify_mode, form['notify_user_ids'])
        _touch_project(project)
        db.session.commit()
        if is_draft:
            flash('Draft saved.', 'success')
            return redirect(url_for('projects.edit_message', project_id=project.id, message_id=msg.id))
        flash('Message posted.', 'success')
        return redirect(url_for('projects.message_detail', project_id=project.id, message_id=msg.id))

    return render_template(
        'projects/message_form.html',
        **_form_context(project, categories, {'notify_mode': 'subscribers'}, 'new'),
    )


@projects_bp.route('/<int:project_id>/messages/<int:message_id>')
@login_required
def message_detail(project_id, message_id):
    project = _get_accessible_project(project_id)
    message = ProjectMessage.query.filter_by(id=message_id, project_id=project.id).first_or_404()
    if message.is_draft and message.created_by != current_user.id and not _can_manage_project(project):
        abort(404)
    return render_template(
        'projects/message_detail.html',
        project=project,
        colors=PROJECT_COLORS,
        can_manage=_can_manage_project(project),
        message=message,
        comments=message.comments,
    )


@projects_bp.route('/<int:project_id>/messages/<int:message_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_message(project_id, message_id):
    project = _get_accessible_project(project_id)
    message = ProjectMessage.query.filter_by(id=message_id, project_id=project.id).first_or_404()
    if message.created_by != current_user.id and not _can_manage_project(project):
        abort(403)
    categories = _categories_payload(project.id)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:300]
        body = _sanitize_message_html(request.form.get('body') or '')
        is_draft = request.form.get('intent') == 'draft'
        notify_mode = _parse_notify_mode(request.form.get('notify_mode'))
        form = {
            'title': title,
            'body': body,
            'category_id': request.form.get('category_id') or '',
            'notify_mode': notify_mode,
            'notify_user_ids': request.form.getlist('notify_user_ids'),
        }
        if not title:
            flash('Title is required.', 'error')
            return render_template(
                'projects/message_form.html',
                **_form_context(project, categories, form, 'edit', message),
            )
        try:
            category = _resolve_category(project.id, form['category_id'])
        except ValueError:
            flash('Invalid category.', 'error')
            return redirect(url_for('projects.edit_message', project_id=project.id, message_id=message.id))

        message.title = title
        message.body = body
        message.category_id = category.id if category else None
        message.is_draft = is_draft
        message.notify_mode = notify_mode if not is_draft else 'none'
        message.updated_at = datetime.utcnow()
        if not is_draft:
            _set_notify_users(message, project, notify_mode, form['notify_user_ids'])
        else:
            message.notify_users = []
        _touch_project(project)
        db.session.commit()
        if is_draft:
            flash('Draft saved.', 'success')
            return redirect(url_for('projects.edit_message', project_id=project.id, message_id=message.id))
        flash('Message posted.', 'success')
        return redirect(url_for('projects.message_detail', project_id=project.id, message_id=message.id))

    selected_ids = [str(u.id) for u in (message.notify_users or [])]
    return render_template(
        'projects/message_form.html',
        **_form_context(
            project,
            categories,
            {
                'title': message.title,
                'body': message.body or '',
                'category_id': str(message.category_id) if message.category_id else '',
                'notify_mode': message.notify_mode or 'subscribers',
                'notify_user_ids': selected_ids,
            },
            'edit',
            message,
        ),
    )


@projects_bp.route('/<int:project_id>/messages/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_message(project_id, message_id):
    project = _get_accessible_project(project_id)
    message = ProjectMessage.query.filter_by(id=message_id, project_id=project.id).first_or_404()
    if message.created_by != current_user.id and not _can_manage_project(project):
        abort(403)
    message.notify_users = []
    db.session.delete(message)
    _touch_project(project)
    db.session.commit()
    flash('Message deleted.', 'success')
    return redirect(url_for('projects.messages', project_id=project.id))


@projects_bp.route('/<int:project_id>/messages/<int:message_id>/comments', methods=['POST'])
@login_required
def add_message_comment(project_id, message_id):
    project = _get_accessible_project(project_id)
    message = ProjectMessage.query.filter_by(id=message_id, project_id=project.id).first_or_404()
    if message.is_draft:
        abort(400)
    body = (request.form.get('body') or '').strip()
    if not body:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('projects.message_detail', project_id=project.id, message_id=message.id))
    comment = MessageComment(
        message_id=message.id,
        body=body,
        created_by=current_user.id,
    )
    db.session.add(comment)
    message.updated_at = datetime.utcnow()
    _touch_project(project)
    db.session.commit()
    return redirect(url_for('projects.message_detail', project_id=project.id, message_id=message.id, _anchor=f'comment-{comment.id}'))


@projects_bp.route('/<int:project_id>/api/message-categories', methods=['POST'])
@login_required
def api_create_message_category(project_id):
    project = _get_accessible_project(project_id)
    data = request.get_json(silent=True) or {}
    name = _normalize_category_name(data.get('name') or request.form.get('name', ''))
    if not name:
        return jsonify({'success': False, 'error': 'Category name is required'}), 400
    existing = MessageCategory.query.filter_by(project_id=project.id, name=name).first()
    if existing:
        return jsonify({'success': False, 'error': 'A category with that name already exists'}), 400
    cat = MessageCategory(project_id=project.id, name=name)
    db.session.add(cat)
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True, 'category': cat.to_dict(message_count=0)})


@projects_bp.route('/<int:project_id>/api/message-categories/<int:category_id>/delete', methods=['POST'])
@login_required
def api_delete_message_category(project_id, category_id):
    project = _get_accessible_project(project_id)
    if not _can_manage_project(project):
        return jsonify({'success': False, 'error': 'Not allowed'}), 403
    cat = MessageCategory.query.filter_by(id=category_id, project_id=project.id).first_or_404()
    ProjectMessage.query.filter_by(category_id=cat.id).update({'category_id': None})
    db.session.delete(cat)
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True, 'categories': _categories_payload(project.id)})
