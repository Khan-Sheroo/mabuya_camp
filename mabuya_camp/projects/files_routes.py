"""Project Docs & Files routes (CashUp-style folders + uploads)."""
from pathlib import Path
from uuid import uuid4
import mimetypes

from flask import (
    render_template, request, jsonify, current_app, send_from_directory, abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from mabuya_camp import db
from mabuya_camp.projects import projects_bp
from mabuya_camp.projects.routes import _get_accessible_project, _can_manage_project, _touch_project
from mabuya_camp.models import ProjectFolder, ProjectDocument
from config import PROJECT_COLORS

ALLOWED_PROJECT_FILE_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'csv',
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp',
    'heic', 'heif',
}


def _allowed_project_file(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_PROJECT_FILE_EXTENSIONS


def _default_file_label(filename: str) -> str:
    name = Path(filename or '').name
    stem = name.rsplit('.', 1)[0] if '.' in name else name
    cleaned = ' '.join(stem.replace('_', ' ').replace('-', ' ').split())
    return cleaned[:200] if cleaned else (name[:200] or 'Untitled')


def _project_upload_dir(project_id: int) -> Path:
    root = Path(current_app.config['UPLOAD_FOLDER']) / 'projects' / str(project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _delete_document_file(doc: ProjectDocument) -> None:
    path = (
        Path(current_app.config['UPLOAD_FOLDER'])
        / 'projects'
        / str(doc.project_id)
        / doc.stored_filename
    )
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _normalize_folder_name(name: str) -> str:
    return ' '.join((name or '').strip().split())[:120]


def _project_folders_payload(project_id: int) -> list:
    folders = (
        ProjectFolder.query
        .filter_by(project_id=project_id)
        .order_by(ProjectFolder.name)
        .all()
    )
    payload = []
    for folder in folders:
        count = ProjectDocument.query.filter_by(
            project_id=project_id, folder_id=folder.id
        ).count()
        payload.append(folder.to_dict(document_count=count))
    return payload


def _resolve_folder_for_project(project_id: int, folder_id):
    if folder_id in (None, '', 'null', 'none', '0'):
        return None
    try:
        folder_id_int = int(folder_id)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid folder') from exc
    folder = ProjectFolder.query.filter_by(
        id=folder_id_int, project_id=project_id
    ).first()
    if folder is None:
        raise ValueError('Folder not found')
    return folder


def _filtered_documents(project_id: int, folder_filter: str):
    documents_query = ProjectDocument.query.filter_by(project_id=project_id)
    if folder_filter == 'unfiled':
        documents_query = documents_query.filter(ProjectDocument.folder_id.is_(None))
    elif folder_filter not in ('', 'all', None):
        try:
            folder_id = int(folder_filter)
            documents_query = documents_query.filter_by(folder_id=folder_id)
        except ValueError:
            folder_filter = 'all'
    documents = documents_query.order_by(ProjectDocument.uploaded_at.desc()).all()
    if folder_filter in ('', 'all', None):
        documents = sorted(
            documents,
            key=lambda d: (
                1 if d.folder_id is None else 0,
                (d.folder.name.lower() if d.folder else ''),
                -(d.uploaded_at.timestamp() if d.uploaded_at else 0),
            ),
        )
    return documents, folder_filter


@projects_bp.route('/<int:project_id>/files')
@login_required
def files(project_id):
    project = _get_accessible_project(project_id)
    documents = (
        ProjectDocument.query
        .filter_by(project_id=project.id)
        .order_by(ProjectDocument.uploaded_at.desc())
        .all()
    )
    folders = _project_folders_payload(project.id)
    unfiled_count = sum(1 for d in documents if d.folder_id is None)
    total_count = len(documents)
    return render_template(
        'projects/files.html',
        project=project,
        colors=PROJECT_COLORS,
        can_manage=_can_manage_project(project),
        documents=documents,
        folders=folders,
        unfiled_count=unfiled_count,
        total_count=total_count,
    )


@projects_bp.route('/<int:project_id>/api/files', methods=['GET'])
@login_required
def api_list_project_files(project_id):
    project = _get_accessible_project(project_id)
    folder_filter = request.args.get('folder', 'all')
    documents, folder_filter = _filtered_documents(project.id, folder_filter)
    return jsonify({
        'success': True,
        'folder_filter': folder_filter,
        'folders': _project_folders_payload(project.id),
        'unfiled_count': ProjectDocument.query.filter_by(
            project_id=project.id, folder_id=None
        ).count(),
        'total_count': ProjectDocument.query.filter_by(project_id=project.id).count(),
        'documents': [d.to_dict() for d in documents],
    })


@projects_bp.route('/<int:project_id>/api/folders', methods=['GET'])
@login_required
def api_list_project_folders(project_id):
    project = _get_accessible_project(project_id)
    return jsonify({
        'success': True,
        'folders': _project_folders_payload(project.id),
        'unfiled_count': ProjectDocument.query.filter_by(
            project_id=project.id, folder_id=None
        ).count(),
        'total_count': ProjectDocument.query.filter_by(project_id=project.id).count(),
    })


@projects_bp.route('/<int:project_id>/api/folders', methods=['POST'])
@login_required
def api_create_project_folder(project_id):
    project = _get_accessible_project(project_id)
    data = request.get_json(silent=True) or {}
    name = _normalize_folder_name(data.get('name') or request.form.get('name', ''))
    if not name:
        return jsonify({'success': False, 'error': 'Folder name is required'}), 400
    existing = ProjectFolder.query.filter_by(project_id=project.id, name=name).first()
    if existing:
        return jsonify({'success': False, 'error': 'A folder with that name already exists'}), 400
    folder = ProjectFolder(project_id=project.id, name=name)
    db.session.add(folder)
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True, 'folder': folder.to_dict(document_count=0)})


@projects_bp.route('/<int:project_id>/api/folders/<int:folder_id>', methods=['POST'])
@login_required
def api_update_project_folder(project_id, folder_id):
    project = _get_accessible_project(project_id)
    folder = ProjectFolder.query.filter_by(id=folder_id, project_id=project.id).first_or_404()
    data = request.get_json(silent=True) or {}
    name = _normalize_folder_name(data.get('name') or request.form.get('name', ''))
    if not name:
        return jsonify({'success': False, 'error': 'Folder name is required'}), 400
    clash = ProjectFolder.query.filter(
        ProjectFolder.project_id == project.id,
        ProjectFolder.name == name,
        ProjectFolder.id != folder.id,
    ).first()
    if clash:
        return jsonify({'success': False, 'error': 'A folder with that name already exists'}), 400
    folder.name = name
    _touch_project(project)
    db.session.commit()
    count = ProjectDocument.query.filter_by(folder_id=folder.id).count()
    return jsonify({'success': True, 'folder': folder.to_dict(document_count=count)})


@projects_bp.route('/<int:project_id>/api/folders/<int:folder_id>/delete', methods=['POST'])
@login_required
def api_delete_project_folder(project_id, folder_id):
    project = _get_accessible_project(project_id)
    folder = ProjectFolder.query.filter_by(id=folder_id, project_id=project.id).first_or_404()
    ProjectDocument.query.filter_by(folder_id=folder.id).update({'folder_id': None})
    db.session.delete(folder)
    _touch_project(project)
    db.session.commit()
    return jsonify({
        'success': True,
        'folders': _project_folders_payload(project.id),
        'unfiled_count': ProjectDocument.query.filter_by(
            project_id=project.id, folder_id=None
        ).count(),
    })


@projects_bp.route('/<int:project_id>/api/files', methods=['POST'])
@login_required
def api_upload_project_file(project_id):
    project = _get_accessible_project(project_id)
    files = [f for f in request.files.getlist('files') if f and f.filename]
    if not files:
        single = request.files.get('file')
        if single and single.filename:
            files = [single]
    if not files:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    labels = request.form.getlist('labels')
    if not labels and request.form.get('label') is not None:
        labels = [request.form.get('label', '')]

    try:
        target_folder = _resolve_folder_for_project(
            project.id, request.form.get('folder_id')
        )
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    allowed = ', '.join(sorted(ALLOWED_PROJECT_FILE_EXTENSIONS))
    dest_dir = _project_upload_dir(project.id)
    saved = []
    errors = []

    for index, file in enumerate(files):
        if not _allowed_project_file(file.filename):
            errors.append(f'{file.filename}: file type not allowed ({allowed})')
            continue
        original = secure_filename(file.filename) or 'upload'
        ext = original.rsplit('.', 1)[-1].lower() if '.' in original else 'bin'
        stored = f'{uuid4().hex}.{ext}'
        dest_path = dest_dir / stored
        try:
            file.save(dest_path)
        except OSError:
            errors.append(f'{file.filename}: could not save file')
            continue

        content_type = file.mimetype or mimetypes.guess_type(original)[0] or 'application/octet-stream'
        raw_label = labels[index] if index < len(labels) else ''
        label = (raw_label or '').strip()[:200] or _default_file_label(original)
        file_size = dest_path.stat().st_size if dest_path.exists() else 0

        doc = ProjectDocument(
            project_id=project.id,
            folder_id=target_folder.id if target_folder else None,
            original_filename=original,
            stored_filename=stored,
            content_type=content_type,
            label=label,
            file_size=file_size,
            uploaded_by=current_user.id,
        )
        db.session.add(doc)
        saved.append(doc)

    if not saved:
        return jsonify({
            'success': False,
            'error': errors[0] if errors else 'No files uploaded',
            'errors': errors,
        }), 400

    _touch_project(project)
    db.session.commit()
    return jsonify({
        'success': True,
        'count': len(saved),
        'document': saved[0].to_dict(),
        'documents': [d.to_dict() for d in saved],
        'errors': errors,
        'folders': _project_folders_payload(project.id),
    })


@projects_bp.route('/<int:project_id>/files/<int:doc_id>/move', methods=['POST'])
@login_required
def api_move_project_file(project_id, doc_id):
    project = _get_accessible_project(project_id)
    doc = ProjectDocument.query.filter_by(id=doc_id, project_id=project.id).first_or_404()
    data = request.get_json(silent=True) or {}
    folder_id = data.get('folder_id', request.form.get('folder_id'))
    try:
        folder = _resolve_folder_for_project(project.id, folder_id)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    doc.folder_id = folder.id if folder else None
    _touch_project(project)
    db.session.commit()
    return jsonify({'success': True, 'document': doc.to_dict()})


@projects_bp.route('/<int:project_id>/files/<int:doc_id>/download')
@login_required
def download_project_file(project_id, doc_id):
    project = _get_accessible_project(project_id)
    doc = ProjectDocument.query.filter_by(id=doc_id, project_id=project.id).first_or_404()
    directory = Path(current_app.config['UPLOAD_FOLDER']) / 'projects' / str(project.id)
    path = directory / doc.stored_filename
    if not path.is_file():
        abort(404)
    as_attachment = request.args.get('download') == '1'
    return send_from_directory(
        directory,
        doc.stored_filename,
        as_attachment=as_attachment,
        download_name=doc.original_filename,
        mimetype=doc.content_type,
    )


@projects_bp.route('/<int:project_id>/files/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_project_file(project_id, doc_id):
    project = _get_accessible_project(project_id)
    doc = ProjectDocument.query.filter_by(id=doc_id, project_id=project.id).first_or_404()
    _delete_document_file(doc)
    db.session.delete(doc)
    _touch_project(project)
    db.session.commit()
    return jsonify({
        'success': True,
        'folders': _project_folders_payload(project.id),
        'unfiled_count': ProjectDocument.query.filter_by(
            project_id=project.id, folder_id=None
        ).count(),
        'total_count': ProjectDocument.query.filter_by(project_id=project.id).count(),
    })
