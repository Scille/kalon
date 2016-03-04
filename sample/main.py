import logging
import requests
from os.path import abspath, dirname
from flask import current_app, make_response

from kalon.core_app import CoreApp


def create_app(config=None):
    """
    Build the app build don't initilize it, useful to get back the default
    app config, correct it, then call ``bootstrap_app`` with the now config
    """

    app = CoreApp(__name__)
    if config:
        app.config.update(config)
    app.config.from_pyfile('default_settings.cfg')
    return app


def bootstrap_app(app=None, config=None):
    """
    Create and initilize the app
    """

    if not app:
        app = create_app(config)
    elif config:
        app.config.update(config)

    from sample import model, events, roles
    from kalon import auth
    from sample.view import api
    from sample.tasks.email import mail

    app.bootstrap()

    model.init_app(app)
    api.prefix = app.config['BACKEND_API_PREFIX']
    app.config['AUTH_USER_CLS'] = model.User
    app.config['ROLES'] = roles.ROLES
    auth.Auth(app, url_prefix=app.config['BACKEND_API_PREFIX'])
    api.init_app(app)
    events.init_events(app)
    mail.init_app(app)

    # Configure static hosting of the front
    if app.config['FRONTEND_HOSTED']:
        from flask import send_from_directory
        try:
            from flask.ext.cache import Cache
        except ImportError:
            raise ImportError('module `flask_cache` is required to'
                              ' enable FRONTEND_HOSTED')
        cache = Cache(app, config={'CACHE_TYPE': 'simple'})
        app.root_path = abspath(dirname(__file__) + '/..')
        redirect_url = app.config['FRONTEND_HOSTED_REDIRECT_URL']

        @app.route('/')
        @app.route('/<path:path>')
        @cache.cached(timeout=600)
        def host_front(path='index.html'):
            if redirect_url:
                target = '{}/{}'.format(redirect_url, path)
                r = requests.get(target)
                if r.status_code != 200:
                    app.logger.error('cannot fetch {}, error {} : {}'.format(
                        target, r.status_code, r.data))
                response = make_response(r.content, r.status_code)
                for key, value in r.headers.items():
                    response.headers[key] = value
                return response
            return send_from_directory('static', path)

    else:
        # Root access is useful to test if the server is online (no auth needed)
        @app.route('/')
        def index():
            return ''

    # Create a user to test with
    @app.before_first_request
    def create_user():
        if not current_app.config.get('DEBUG', False):
            # Enable logger in production
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
            app.logger.addHandler(stream_handler)
        else:
            # Create a default admin in debug
            from sample.model import User
            try:
                User.objects.get(email='admin@test.com')
            except User.DoesNotExist:
                current_app.logger.info('Creating default user admin@test.com')
                new_user = User(email='admin@test.com', role="Admin")
                new_user.controller.set_password('password')
                new_user.save()
    return app
