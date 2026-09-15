from flask import Blueprint

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')
home_bp = Blueprint('home', __name__)

from mabuya_camp.projects import routes  # noqa: E402, F401
from mabuya_camp.projects import files_routes  # noqa: E402, F401
from mabuya_camp.projects import schedule_routes  # noqa: E402, F401
from mabuya_camp.projects import messages_routes  # noqa: E402, F401
