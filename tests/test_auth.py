import pytest
import json
from base64 import b64decode, b64encode
from datetime import datetime

from tests import common
from sample.model.user import User
from kalon.auth import generate_access_token, generate_remember_me_token


@pytest.fixture
def user(request, email='john.doe@test.com', password='password', **kwargs):
    new_user = User(email=email, **kwargs)
    new_user.controller.set_password(password)
    new_user.save()
    new_user._raw_password = 'password'

    def finalizer():
        new_user.delete()
    request.addfinalizer(finalizer)
    return new_user


class TestAuth(common.BaseTest):

    def test_not_allowed(self):
        assert self.client_app.get('/me').status_code == 401
        # Dummy try
        assert self.client_app.post('/login').status_code == 400

    def test_authentication(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        r = user_req.post('/login', data={
            'email': user.email,
            'password': 'password'
        }, auth=False)
        assert r.status_code == 200, r
        assert 'token' in r.data, r
        # Try to authenticate with the given token
        user_req.token = r.data['token']
        assert user_req.get('/me').status_code == 200
        # Change password
        r = user_req.patch('/login/password', data={'new_password': 'new_pass'})
        assert r.status_code == 200, r
        assert 'token' in r.data, r
        # Old token is no longer valid
        assert user_req.get('/me').status_code == 401
        # Instead we have to use the given token
        user_req.token = r.data['token']
        assert user_req.get('/me').status_code == 200

    def test_remember_me(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        r = user_req.post('/login', data={
            'email': user.email,
            'password': 'password',
            'remember_me': True
        }, auth=False)
        assert r.status_code == 200, r
        assert 'token' in r.data, r
        assert 'remember_me_token' in r.data, r
        # Try to authenticate with the given token
        user_req.token = r.data['token']
        user_req.remember_me_token = r.data['remember_me_token']
        assert user_req.get('/me').status_code == 200
        # Ask for a new token with the remember-me one
        r = user_req.post('/login/remember-me', data={
            'remember_me_token': user_req.remember_me_token
        }, auth=False)
        assert r.status_code == 200, r
        assert 'token' in r.data
        # Test the issued token
        user_req.token = r.data['token']
        assert user_req.get('/me').status_code == 200
        # Bonus test : remember-me token is non-fresh, we should not be
        # allowed to change password with it
        r = user_req.patch('/login/password', data={'new_password': 'nevermind'})
        assert r.status_code == 401, r
        # 2nd Bonus test : remember-me token and issued from it tokens are
        # no longer valid once the password has changed
        user.controller.set_password('new_password')
        user.save()
        assert user_req.get('/me').status_code == 401
        assert user_req.post('/login/remember-me', data={
            'remember_me_token': user_req.remember_me_token
        }, auth=False).status_code == 401

    def test_expirate_access_token(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Build an expirate token
        old_token = generate_access_token(user.email, user.password,
                                          exp=datetime.utcnow().timestamp() - 1)
        user_req.token = old_token
        assert user_req.get('/me').status_code == 401

    def test_expirate_remember_me_token(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Build an expirate token
        old_remember = generate_remember_me_token(
            user.email, user.password, exp=datetime.utcnow().timestamp() - 1)
        assert user_req.post('/login/remember-me', data={
            'remember_me_token': old_remember
        }, auth=False).status_code == 401

    def test_alter_token(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Build an expirate token and make sure we can no longer use it
        old_token = generate_access_token(user.email, user.password,
                                          exp=datetime.utcnow().timestamp() - 1)
        user_req.token = old_token
        r = user_req.get('/me')
        assert r.status_code == 401, r
        # Hack it to make it valid again
        head, payload, signature = old_token.split('.')
        payload = payload + '=' * (4 - len(payload) % 4)  # Add required padding
        payload = json.loads(b64decode(payload).decode())
        payload['exp'] = datetime.utcnow().timestamp() + 50000
        hacked_token = '.'.join(
            (head, b64encode(json.dumps(payload).encode()).decode(), signature))
        user_req.token = hacked_token
        r = user_req.get('/me')
        assert r.status_code == 401, r
