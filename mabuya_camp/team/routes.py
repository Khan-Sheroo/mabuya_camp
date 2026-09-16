"""Account-level team members (admin manages who can log in and collaborate)."""
from functools import wraps

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from mabuya_camp import db
from mabuya_camp.team import team_bp
from mabuya_camp.models import User, ProjectMember


ALLOWED_ROLES = ('admin', 'manager', 'member')
CREATABLE_ROLES = ('manager', 'member')


def _admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _normalize_email(email: str) -> str:
    return (email or '').strip().lower()


def _normalize_name(name: str) -> str:
    return ' '.join((name or '').strip().split())[:120]


def _role_label(role: str) -> str:
    return {
        'admin': 'Team leader',
        'manager': 'Manager',
        'member': 'Member',
    }.get(role, role)


@team_bp.route('/')
@login_required
@_admin_required
def index():
    users = (
        User.query
        .filter_by(is_active=True)
        .order_by(User.role.asc(), User.name.asc())
        .all()
    )
    return render_template(
        'team/index.html',
        users=users,
        role_label=_role_label,
        creatable_roles=CREATABLE_ROLES,
    )


@team_bp.route('/add', methods=['POST'])
@login_required
@_admin_required
def add():
    name = _normalize_name(request.form.get('name'))
    email = _normalize_email(request.form.get('email'))
    password = request.form.get('password') or ''
    role = (request.form.get('role') or 'member').strip().lower()

    if role not in CREATABLE_ROLES:
        role = 'member'

    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('team.index'))
    if not email or '@' not in email:
        flash('A valid email is required.', 'error')
        return redirect(url_for('team.index'))
    if len(password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('team.index'))
    if User.query.filter_by(email=email).first():
        flash('That email is already on the team.', 'error')
        return redirect(url_for('team.index'))

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f'{name} was added to the team.', 'success')
    return redirect(url_for('team.index'))


@team_bp.route('/<int:user_id>/role', methods=['POST'])
@login_required
@_admin_required
def update_role(user_id):
    user = User.query.get_or_404(user_id)
    role = (request.form.get('role') or '').strip().lower()

    if user.id == current_user.id:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('team.index'))

    if role not in ALLOWED_ROLES:
        flash('Invalid role.', 'error')
        return redirect(url_for('team.index'))

    if user.role == 'admin' and role != 'admin':
        other_admins = User.query.filter(
            User.role == 'admin',
            User.id != user.id,
            User.is_active.is_(True),
        ).count()
        if other_admins == 0:
            flash('Keep at least one team leader on the account.', 'error')
            return redirect(url_for('team.index'))

    user.role = role
    db.session.commit()
    flash(f'{user.name} is now a {_role_label(role).lower()}.', 'success')
    return redirect(url_for('team.index'))


@team_bp.route('/<int:user_id>/password', methods=['POST'])
@login_required
@_admin_required
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    password = request.form.get('password') or ''
    if len(password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('team.index'))
    user.set_password(password)
    db.session.commit()
    flash(f'Password updated for {user.name}.', 'success')
    return redirect(url_for('team.index'))


@team_bp.route('/<int:user_id>/remove', methods=['POST'])
@login_required
@_admin_required
def remove(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot remove yourself.', 'error')
        return redirect(url_for('team.index'))

    if user.role == 'admin':
        other_admins = User.query.filter(
            User.role == 'admin',
            User.id != user.id,
            User.is_active.is_(True),
        ).count()
        if other_admins == 0:
            flash('Keep at least one team leader on the account.', 'error')
            return redirect(url_for('team.index'))

    ProjectMember.query.filter_by(user_id=user.id).delete()
    user.is_active = False
    # Free the email so it can be re-added later
    user.email = f'removed+{user.id}.{user.email}'
    if len(user.email) > 255:
        user.email = f'removed+{user.id}@mabuya.local'
    db.session.commit()
    flash(f'{user.name} was removed from the team.', 'success')
    return redirect(url_for('team.index'))
