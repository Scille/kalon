from flask.ext.restful import Resource

from kalon.concurrency import concurrency_handler
from kalon.auth import login_required


class CoreResource(Resource):
    """
    Flask-restful resource with automatic authentication and
    concurrency handling
    """
    method_decorators = [concurrency_handler, login_required]  # reversed order
