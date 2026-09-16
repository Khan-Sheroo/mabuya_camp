from flask import Blueprint

team_bp = Blueprint('team', __name__, url_prefix='/team')

from mabuya_camp.team import routes  # noqa: E402, F401
