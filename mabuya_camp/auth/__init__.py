from flask import Blueprint

auth_bp = Blueprint('auth', __name__)

from mabuya_camp.auth import routes  # noqa: E402, F401
