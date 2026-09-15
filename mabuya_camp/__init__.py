from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from pathlib import Path

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'mabuya-camp-dev-secret-change-me'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mabuya_camp.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    upload_root = Path(app.root_path).parent / 'uploads'
    app.config['UPLOAD_FOLDER'] = str(upload_root)
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
    upload_root.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    from mabuya_camp.routes import main_bp, staff_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(staff_bp)

    with app.app_context():
        db.create_all()

    return app
