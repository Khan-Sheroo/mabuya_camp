from mabuya_camp import db
from datetime import datetime


class Staff(db.Model):
    __tablename__ = 'staff'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    documents = db.relationship(
        'StaffDocument', backref='staff', lazy=True, cascade='all, delete-orphan'
    )
    folders = db.relationship(
        'StaffFolder', backref='staff', lazy=True, cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Staff {self.name}>'


class StaffFolder(db.Model):
    __tablename__ = 'staff_folder'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    documents = db.relationship('StaffDocument', backref='folder', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('staff_id', 'name', name='uq_staff_folder_name'),
    )

    def to_dict(self, document_count=None):
        data = {
            'id': self.id,
            'staff_id': self.staff_id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if document_count is not None:
            data['document_count'] = document_count
        return data


class StaffDocument(db.Model):
    __tablename__ = 'staff_document'

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('staff_folder.id'), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    label = db.Column(db.String(200), nullable=True)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

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
            'staff_id': self.staff_id,
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
