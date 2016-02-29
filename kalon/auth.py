"""
Auth module provide two type of authentification
 - basic auth with login/password
 - token based with remember-me handling

On the top of that it handle the "freshness" of the authentification. An
authentification is considered as fresh if it has been generated from
the login/password:
 - basic auth is always fresh
 - token auth generated from login/password is fresh
 - token auth generated from remember-me token is not fresh

A fresh token should be required to do tasks requiring more security (i.g.
changing password)
"""

import jwt
from hashlib import sha256
from functools import wraps
from datetime import datetime
from passlib.apps import custom_app_context as pwd_context
from flask import g, request, current_app
from flask.ext.restful import Resource, reqparse
from flask.ext.principal import (Identity, ActionNeed, UserNeed,
                                 AnonymousIdentity, identity_changed)
from werkzeug.local import LocalProxy

from core.tools import abort
from core.api import CoreApi


# A proxy for the current user. If no user is logged in, returns None
current_user = LocalProxy(lambda: g._current_user)


def encrypt_password(password):
    return pwd_context.encrypt(password)


def verify_password(password, pwd_hash):
    return pwd_context.verify(password, pwd_hash)


def encode_token(payload):
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256').decode()


def decode_token(token):
    try:
        return jwt.decode(token, current_app.config['SECRET_KEY'])
    except jwt.InvalidTokenError:
        return None


def _build_pass_watcher(hashed_password):
    # Create a value that get revoked whenever the
    # user's password is changed
    key = current_app.config['SECRET_KEY'] + hashed_password
    return sha256(key.encode()).hexdigest()


def _check_pass_watcher(value, hashed_password):
    key = current_app.config['SECRET_KEY'] + hashed_password
    return value == sha256(key.encode()).hexdigest()


def is_fresh_auth():
    token = getattr(g, '_token', None)
    if token:
        return token['fresh']
    else:
        return True


def login_required_fresh(func):
    """
    Decorator to make mandatory fresh login
    """
    return login_required(func, True)


def generate_access_token(email, hashed_password, fresh=False, exp=None):
    exp = exp or datetime.utcnow().timestamp() + current_app.config['TOKEN_VALIDITY']
    return encode_token({
        'exp': exp,
        'email': email,
        'type': 'auth',
        'fresh': fresh,
        'watcher': _build_pass_watcher(hashed_password)
    })


def generate_remember_me_token(email, hashed_password, exp=None):
    exp = exp or datetime.utcnow().timestamp() + current_app.config['REMEMBER_ME_TOKEN_VALIDITY']
    return encode_token({
        'exp': exp,
        'email': email,
        'type': 'remember-me',
        'watcher': _build_pass_watcher(hashed_password)
    })


class Auth:
    """
    Bind the Auth api to the given app
    """
    def __init__(self, app=None, url_prefix=None):
        if app is not None:
            self.init_app(app, url_prefix=url_prefix)

    def init_app(self, app, url_prefix=None):
        self.app = app
        if not app.config.get('AUTH_USER_CLS'):
            raise RuntimeError('`AUTH_USER_CLS` config is mandatory for Auth module')
        app.config.setdefault('ROLES', {})
        api = CoreApi()
        api.prefix = url_prefix
        api.add_resource(Login, '/login')
        api.add_resource(RememberMe, '/login/remember-me')
        api.add_resource(ChangePassword, '/login/password')
        api.init_app(app)


def login_required(func, must_be_fresh=False):
    """Authenticate decorator for the routes"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not getattr(func, 'authenticated', True):
            return func(*args, **kwargs)
        # Custom account lookup function
        user = _basic_authentication()
        if not user:
            user = _token_authentication(must_be_fresh)
        if not user:
            if must_be_fresh:
                abort(401, 'Token frais requis')
            else:
                abort(401, 'Token invalide')
        # Authentication complete, keep user data and notify Flask-Principal
        _load_identity(user)
        return func(*args, **kwargs)
    return wrapper


def _load_identity(user=None):
    """
    Load a user identity into Flask-Principal
    :param user: curront user to load or anonymous user if empty
    """
    if not user:
        # Anonymous user
        identity = AnonymousIdentity()
    else:
        # Use str version of objectid to avoid json encoding troubles
        identity = Identity(str(user.id))
        identity.provides.add(UserNeed(user.id))
        if user.role:
            role_policies = current_app.config['ROLES'].get(user.role)
            if not role_policies:
                current_app.logger.warning('user `%s` has unknow role `%s`' %
                                           (user.id, user.role))
            else:
                for policy in role_policies:
                    identity.provides.add(policy.action_need)
        for action in user.permissions:
            identity.provides.add(ActionNeed(action))
    g._current_user = user
    identity_changed.send(current_app._get_current_object(),
                          identity=identity)


class ChangePassword(Resource):
    """
    Change the password for a user providing a fresh token (i.e. not remembered-me token)
    """
    @login_required_fresh
    def patch(self):
        parser = reqparse.RequestParser()
        parser.add_argument('new_password', type=str, required=True)
        args = parser.parse_args()
        current_user.controller.set_password(args['new_password'])
        current_user.save()
        # Reissue a new token
        return {'token': generate_access_token(current_user.email, current_user.password)}


class Login(Resource):
    """
    Authenticate a user given it email and password then
    issue him an access token
    """
    def post(self):
        # Tell Flask-Principal the user is anonymous
        _load_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        parser.add_argument('remember_me', type=bool, default=False)
        args = parser.parse_args()
        remember_me = args.get('remember_me', False)
        email = args['email']
        # Retrieve the user, check it password and issue the tokens
        user_cls = current_app.config.get('AUTH_USER_CLS')
        user = user_cls.objects(email=email).first()
        if not user or not verify_password(args['password'], user.password):
            abort(401)
        result = {'token': generate_access_token(email, user.password, fresh=True)}
        if remember_me:
            remember_me_token = generate_remember_me_token(email, user.password)
            result['remember_me_token'] = remember_me_token
        return result


class RememberMe(Resource):
    """
    Check the user's remember-me token and reissue an access token
    """
    def post(self):
        # Tell Flask-Principal the user is anonymous
        _load_identity()
        parser = reqparse.RequestParser()
        parser.add_argument('remember_me_token', type=str, required=True)
        args = parser.parse_args()
        remember = decode_token(args['remember_me_token'])
        if not remember or remember['type'] != 'remember-me':
            abort(401)
        email = remember['email']
        user_cls = current_app.config.get('AUTH_USER_CLS')
        user = user_cls.objects(email=email).first()
        if not user or not _check_pass_watcher(remember['watcher'], user.password):
            abort(401)
        return {'token': generate_access_token(email, user.password, fresh=False)}


def _basic_authentication():
    if not request.authorization:
        return None
    user_cls = current_app.config.get('AUTH_USER_CLS')
    try:
        user = user_cls.objects.get(email=request.authorization.username)
    except user_cls.DoesNotExist:
        return None
    if verify_password(request.authorization.password, user.password):
        return user


def _token_authentication(must_be_fresh=False):
    # Token must be passed as header (`{"Authorization": "Token <token>"}`)
    auth = request.headers.get('Authorization', '').split(' ', 1)
    if len(auth) != 2 or auth[0].lower() != 'token':
        return None
    token = decode_token(auth[1])
    g._token = token
    if not token or token['type'] != 'auth' or (must_be_fresh and not token['fresh']):
        return None
    user_cls = current_app.config.get('AUTH_USER_CLS')
    try:
        user = user_cls.objects.get(email=token['email'])
    except user_cls.DoesNotExist:
        return None
    if not _check_pass_watcher(token['watcher'], user.password):
        return None
    user._token_fresh = token['fresh']
    return user
