from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, jsonify,
    current_app, send_from_directory, abort,
)
from mabuya_camp import db
from mabuya_camp.models import Staff, StaffDocument, StaffFolder
from pathlib import Path
from uuid import uuid4
from werkzeug.utils import secure_filename
import mimetypes

ALLOWED_STAFF_FILE_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'csv',
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp',
    'heic', 'heif',
}

main_bp = Blueprint('main', __name__)
staff_bp = Blueprint('staff', __name__, url_prefix='/staff')


@main_bp.route('/')
def index():
    return redirect(url_for('staff.list_staff'))


@staff_bp.route('/')
def list_staff():
    staff_list = Staff.query.order_by(Staff.name).all()
    return render_template('staff/list.html', staff_list=staff_list)


@staff_bp.route('/add', methods=['GET', 'POST'])
def add_staff():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        active = request.form.get('active') == 'on'
        if not name:
            flash('Staff name is required', 'error')
            return render_template('staff/add.html')
        existing = Staff.query.filter_by(name=name).first()
        if existing:
            flash(f'Staff member "{name}" already exists', 'error')
            return render_template('staff/add.html')
        staff = Staff(name=name, active=active)
        db.session.add(staff)
        db.session.commit()
        flash(f'Staff member "{name}" added successfully', 'success')
        return redirect(url_for('staff.list_staff'))
    return render_template('staff/add.html')


@staff_bp.route('/<int:staff_id>/toggle', methods=['POST'])
def toggle_staff_status(staff_id):
    staff = Staff.query.get_or_404(staff_id)
    staff.active = not staff.active
    db.session.commit()
    status = 'activated' if staff.active else 'deactivated'
    flash(f'Staff member "{staff.name}" {status}', 'success')
    return redirect(url_for('staff.list_staff'))


@staff_bp.route('/<int:staff_id>/delete', methods=['POST'])
def delete_staff(staff_id):
    staff = Staff.query.get_or_404(staff_id)
    name = staff.name
    for doc in list(staff.documents):
        _delete_document_file(doc)
    StaffDocument.query.filter_by(staff_id=staff_id).delete()
    StaffFolder.query.filter_by(staff_id=staff_id).delete()
    db.session.delete(staff)
    db.session.commit()
    staff_dir = Path(current_app.config['UPLOAD_FOLDER']) / 'staff' / str(staff_id)
    if staff_dir.exists():
        try:
            staff_dir.rmdir()
        except OSError:
            pass
    flash(f'Staff member "{name}" deleted', 'success')
    return redirect(url_for('staff.list_staff'))


def _allowed_staff_file(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_STAFF_FILE_EXTENSIONS


def _default_staff_file_label(filename: str) -> str:
    name = Path(filename or '').name
    stem = name.rsplit('.', 1)[0] if '.' in name else name
    cleaned = stem.replace('_', ' ').replace('-', ' ')
    cleaned = ' '.join(cleaned.split())
    return cleaned[:200] if cleaned else (name[:200] or 'Untitled')


def _staff_upload_dir(staff_id: int) -> Path:
    root = Path(current_app.config['UPLOAD_FOLDER']) / 'staff' / str(staff_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _delete_document_file(doc: StaffDocument) -> None:
    path = Path(current_app.config['UPLOAD_FOLDER']) / 'staff' / str(doc.staff_id) / doc.stored_filename
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _normalize_folder_name(name: str) -> str:
    return ' '.join((name or '').strip().split())[:120]


def _staff_folders_payload(staff_id: int) -> list:
    folders = (
        StaffFolder.query
        .filter_by(staff_id=staff_id)
        .order_by(StaffFolder.name)
        .all()
    )
    payload = []
    for folder in folders:
        count = StaffDocument.query.filter_by(staff_id=staff_id, folder_id=folder.id).count()
        payload.append(folder.to_dict(document_count=count))
    return payload


def _resolve_folder_for_staff(staff_id: int, folder_id):
    if folder_id in (None, '', 'null', 'none', '0'):
        return None
    try:
        folder_id_int = int(folder_id)
    except (TypeError, ValueError):
        raise ValueError('Invalid folder')
    folder = StaffFolder.query.filter_by(id=folder_id_int, staff_id=staff_id).first()
    if folder is None:
        raise ValueError('Folder not found')
    return folder


@staff_bp.route('/<int:staff_id>/files')
def staff_files(staff_id):
    staff = Staff.query.get_or_404(staff_id)
    folder_filter = request.args.get('folder', 'all')
    documents_query = StaffDocument.query.filter_by(staff_id=staff_id)
    if folder_filter == 'unfiled':
        documents_query = documents_query.filter(StaffDocument.folder_id.is_(None))
    elif folder_filter not in ('', 'all', None):
        try:
            folder_id = int(folder_filter)
            documents_query = documents_query.filter_by(folder_id=folder_id)
        except ValueError:
            folder_filter = 'all'
    documents = documents_query.order_by(StaffDocument.uploaded_at.desc()).all()
    if folder_filter in ('', 'all', None):
        documents = sorted(
            documents,
            key=lambda d: (
                1 if d.folder_id is None else 0,
                (d.folder.name.lower() if d.folder else ''),
                -(d.uploaded_at.timestamp() if d.uploaded_at else 0),
            ),
        )
    folders = _staff_folders_payload(staff_id)
    unfiled_count = StaffDocument.query.filter_by(staff_id=staff_id, folder_id=None).count()
    total_count = StaffDocument.query.filter_by(staff_id=staff_id).count()
    return render_template(
        'staff/files.html',
        staff=staff,
        documents=documents,
        folders=folders,
        folder_filter=folder_filter,
        unfiled_count=unfiled_count,
        total_count=total_count,
    )


@staff_bp.route('/api/<int:staff_id>/files', methods=['GET'])
def api_list_staff_files(staff_id):
    Staff.query.get_or_404(staff_id)
    folder_filter = request.args.get('folder', 'all')
    documents_query = StaffDocument.query.filter_by(staff_id=staff_id)
    if folder_filter == 'unfiled':
        documents_query = documents_query.filter(StaffDocument.folder_id.is_(None))
    elif folder_filter not in ('', 'all', None):
        try:
            folder_id = int(folder_filter)
            documents_query = documents_query.filter_by(folder_id=folder_id)
        except ValueError:
            folder_filter = 'all'
    documents = documents_query.order_by(StaffDocument.uploaded_at.desc()).all()
    if folder_filter in ('', 'all', None):
        documents = sorted(
            documents,
            key=lambda d: (
                1 if d.folder_id is None else 0,
                (d.folder.name.lower() if d.folder else ''),
                -(d.uploaded_at.timestamp() if d.uploaded_at else 0),
            ),
        )
    return jsonify({
        'success': True,
        'folder_filter': folder_filter,
        'folders': _staff_folders_payload(staff_id),
        'unfiled_count': StaffDocument.query.filter_by(staff_id=staff_id, folder_id=None).count(),
        'total_count': StaffDocument.query.filter_by(staff_id=staff_id).count(),
        'documents': [d.to_dict() for d in documents],
    })


@staff_bp.route('/api/<int:staff_id>/folders', methods=['GET'])
def api_list_staff_folders(staff_id):
    Staff.query.get_or_404(staff_id)
    return jsonify({
        'success': True,
        'folders': _staff_folders_payload(staff_id),
        'unfiled_count': StaffDocument.query.filter_by(staff_id=staff_id, folder_id=None).count(),
        'total_count': StaffDocument.query.filter_by(staff_id=staff_id).count(),
    })


@staff_bp.route('/api/<int:staff_id>/folders', methods=['POST'])
def api_create_staff_folder(staff_id):
    Staff.query.get_or_404(staff_id)
    data = request.get_json(silent=True) or {}
    name = _normalize_folder_name(data.get('name') or request.form.get('name', ''))
    if not name:
        return jsonify({'success': False, 'error': 'Folder name is required'}), 400
    existing = StaffFolder.query.filter_by(staff_id=staff_id, name=name).first()
    if existing:
        return jsonify({'success': False, 'error': f'Folder "{name}" already exists'}), 400
    folder = StaffFolder(staff_id=staff_id, name=name)
    db.session.add(folder)
    db.session.commit()
    return jsonify({'success': True, 'folder': folder.to_dict(document_count=0)})


@staff_bp.route('/api/folders/<int:folder_id>', methods=['POST'])
def api_update_staff_folder(folder_id):
    folder = StaffFolder.query.get_or_404(folder_id)
    data = request.get_json(silent=True) or {}
    name = _normalize_folder_name(data.get('name') or request.form.get('name', ''))
    if not name:
        return jsonify({'success': False, 'error': 'Folder name is required'}), 400
    clash = (
        StaffFolder.query
        .filter(
            StaffFolder.staff_id == folder.staff_id,
            StaffFolder.name == name,
            StaffFolder.id != folder.id,
        )
        .first()
    )
    if clash:
        return jsonify({'success': False, 'error': f'Folder "{name}" already exists'}), 400
    folder.name = name
    db.session.commit()
    count = StaffDocument.query.filter_by(folder_id=folder.id).count()
    return jsonify({'success': True, 'folder': folder.to_dict(document_count=count)})


@staff_bp.route('/api/folders/<int:folder_id>/delete', methods=['POST'])
def api_delete_staff_folder(folder_id):
    folder = StaffFolder.query.get_or_404(folder_id)
    staff_id = folder.staff_id
    StaffDocument.query.filter_by(folder_id=folder.id).update({'folder_id': None})
    db.session.delete(folder)
    db.session.commit()
    return jsonify({
        'success': True,
        'staff_id': staff_id,
        'folders': _staff_folders_payload(staff_id),
    })


@staff_bp.route('/files/<int:doc_id>/move', methods=['POST'])
def api_move_staff_file(doc_id):
    doc = StaffDocument.query.get_or_404(doc_id)
    data = request.get_json(silent=True) or {}
    folder_id = data.get('folder_id', request.form.get('folder_id'))
    try:
        folder = _resolve_folder_for_staff(doc.staff_id, folder_id)
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    doc.folder_id = folder.id if folder else None
    db.session.commit()
    return jsonify({'success': True, 'document': doc.to_dict()})


@staff_bp.route('/api/<int:staff_id>/files', methods=['POST'])
def api_upload_staff_file(staff_id):
    Staff.query.get_or_404(staff_id)
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
        target_folder = _resolve_folder_for_staff(staff_id, request.form.get('folder_id'))
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    allowed = ', '.join(sorted(ALLOWED_STAFF_FILE_EXTENSIONS))
    dest_dir = _staff_upload_dir(staff_id)
    saved = []
    errors = []

    for index, file in enumerate(files):
        if not _allowed_staff_file(file.filename):
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
        label = (raw_label or '').strip()[:200] or _default_staff_file_label(original)
        file_size = dest_path.stat().st_size if dest_path.exists() else 0
        doc = StaffDocument(
            staff_id=staff_id,
            folder_id=target_folder.id if target_folder else None,
            original_filename=original,
            stored_filename=stored,
            content_type=content_type,
            label=label,
            file_size=file_size,
        )
        db.session.add(doc)
        saved.append(doc)

    if not saved:
        return jsonify({
            'success': False,
            'error': errors[0] if errors else 'No files uploaded',
            'errors': errors,
        }), 400

    db.session.commit()
    return jsonify({
        'success': True,
        'count': len(saved),
        'document': saved[0].to_dict(),
        'documents': [d.to_dict() for d in saved],
        'errors': errors,
        'folders': _staff_folders_payload(staff_id),
    })


@staff_bp.route('/files/<int:doc_id>/download')
def download_staff_file(doc_id):
    doc = StaffDocument.query.get_or_404(doc_id)
    directory = Path(current_app.config['UPLOAD_FOLDER']) / 'staff' / str(doc.staff_id)
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


@staff_bp.route('/files/<int:doc_id>/delete', methods=['POST'])
def delete_staff_file(doc_id):
    doc = StaffDocument.query.get_or_404(doc_id)
    staff_id = doc.staff_id
    _delete_document_file(doc)
    db.session.delete(doc)
    db.session.commit()
    wants_json = (
        request.accept_mimetypes.best == 'application/json'
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.is_json
    )
    if wants_json:
        return jsonify({'success': True})
    flash('File deleted', 'success')
    next_url = request.form.get('next') or url_for('staff.staff_files', staff_id=staff_id)
    return redirect(next_url)
