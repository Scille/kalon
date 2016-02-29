import pytest
import json
from datetime import datetime, timedelta

from tests import common
from tests.test_auth import user

from sample.model.user import User
from sample.permissions import POLICIES as p
from sample.tasks.email import mail


@pytest.fixture
def another_user(request, password='password', email="jane.dane@test.com"):
    return user(request, email=email, password=password)


class TestUser(common.BaseTest):

    def test_links_list(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.user.see.name]
        user.save()
        r = user_req.get('/users')
        assert r.status_code == 200, r
        common.assert_links(r, ['self', 'root'])
        user.permissions.append(p.user.create.name)
        user.save()
        r = user_req.get('/users')
        assert r.status_code == 200, r
        common.assert_links(r, ['self', 'create', 'root'])

    def test_links_single(self, user, another_user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.user.see.name]
        user.save()
        route = '/users/%s' % another_user.pk
        r = user_req.get(route)
        assert r.status_code == 200, r
        common.assert_links(r, ['self', 'parent'])
        user.permissions.append(p.user.modify.name)
        user.save()
        r = user_req.get(route)
        assert r.status_code == 200, r
        common.assert_links(r, ['self', 'update', 'parent'])
        user.permissions = [p.user.see.name, p.history.see.name]
        user.save()
        r = user_req.get(route)
        assert r.status_code == 200, r
        common.assert_links(r, ['self', 'history', 'parent'])

    def test_links_self(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        r = user_req.get('/me')
        assert r.status_code == 200, r
        common.assert_links(r, ['self', 'update', 'root'])

    def test_bad_field(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Invalid field
        r = user_req.patch('/me', data={'bad_field': 'eee'})
        assert r.status_code == 400, r

    def test_change_self_password(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        r = user_req.patch('/me', data={'password': 'h4ck'})
        assert r.status_code == 400, r.data

    def test_change_self_permissions(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        r = user_req.patch('/me', data={'permissions': ['h4ck']})
        assert r.status_code == 400, r.data

    def test_update_user(self, user, another_user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Need permission to do it
        route = '/users/{}'.format(another_user.id)
        r = user_req.patch(route, data={'lastname': 'Doe'})
        assert r.status_code == 403, r
        # Now provide the permission
        user.permissions = [p.user.modify.name]
        user.save()
        r = user_req.patch(route, data={'lastname': 'Doe'})
        assert r.status_code == 200, r
        assert r.data.get('lastname', '<invalid>') == 'Doe'

    def test_bad_update_user(self, user, another_user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.user.modify.name]
        user.save()
        # Need permission to do it
        route = '/users/{}'.format(another_user.id)
        for key, value in (('id', '554534801d41c8de989d038e'),
                           ('doc_version', 42), ('doc_version', '42'),
                           ('_version', '42'), ('_version', 42)):
            r = user_req.patch(route, data={key: value})
            assert r.status_code == 400, (key, value)

    def test_change_password(self, user, another_user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Need permission to do it
        route = '/users/{}'.format(another_user.id)
        r = user_req.patch(route, data={'password': 'new_pass'})
        assert r.status_code == 403, r
        # Now provide the permission
        user.permissions = [p.user.modify.name]
        user.save()
        old_password = another_user.password
        r = user_req.patch(route, data={'password': 'new_pass'})
        assert r.status_code == 200, r
        assert r.data.get('password', '<invalid>') != old_password

    def test_create_user(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Need permission to do it
        r = user_req.post('/users', data={
            "email": "new@user.com",
            "password": "secret",
            "lastname": "Doe",
            "firstname": "John"
        })
        assert r.status_code == 403, r
        # Now provide the permission
        user.permissions = [p.user.create.name]
        user.save()
        r = user_req.post('/users', data={
            "email": "new@user.com",
            "password": "secret",
            "lastname": "Doe",
            "firstname": "John"
        })
        assert r.status_code == 201, r
        assert r.data.get("email", '<invalid>') == "new@user.com"
        assert r.data.get("lastname", '<invalid>') == "Doe"
        assert r.data.get("firstname", '<invalid>') == "John"
        # Try to login with our brand new user
        payload = json.dumps({
            "email": "new@user.com",
            "password": "secret"
        })
        r = self.client_app.post('/login', data=payload,
                                 content_type='application/json',
                                 content_length=len(payload))
        assert r.status_code == 401, r  # Cannot login anymore, sorry
        with mail.record_messages() as outbox:
            r = user_req.post('/users', data={
                "email": "new@user.com.local",
                "lastname": "Doe",
                "firstname": "John"
            })
            assert r.status_code == 201, r
            assert r.data.get("email", '<invalid>') == "new@user.com.local"
            assert r.data.get("lastname", '<invalid>') == "Doe"
            assert r.data.get("firstname", '<invalid>') == "John"
            assert len(outbox) == 1

    def test_bad_create_user(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.user.create.name]
        user.save()
        default_payload = {
            "email": "bad_create_user@user.com",
            "password": "secret",
            "lastname": "Doe",
            "firstname": "John"
        }
        for key, value in [
            ("id", "554534801d41c8de989d038e"),  # id is read only
            ("email", user.email),  # already taken
                ]:
            payload = default_payload.copy()
            if value is None:
                del payload[key]
            else:
                payload[key] = value
            r = user_req.post('/users', data=payload)
            assert r.status_code == 400, (r, key, value)

    def test_get_users(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Need permission to do it
        r = user_req.get('/users')
        assert r.status_code == 403, r
        r = user_req.get('/users/{}'.format(user.id))
        assert r.status_code == 403, r
        # Now provide the permission
        user.permissions = [p.user.see.name]
        user.save()
        r = user_req.get('/users')
        assert r.status_code == 200, r
        r = user_req.get('/users/{}'.format(user.id))
        assert r.status_code == 200, r


class TestPaginationUser(common.BaseTest):

    def test_paginate_users(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.user.see.name]
        user.save()
        # Start by creating a lot of users
        for i in range(49):
            new_user = User(email='pag.%s@user.com' % i,
                                   password='password',
                                   lastname='Pagination', firstname='Elem')
            new_user.save()
        # Now let's test the pagination !
        common.pagination_testbed(user_req, '/users')


class TestUserConcurrency(common.BaseTest):

    def test_concurrency(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.user.modify.name,
                            p.user.see.name]
        user.save()
        route = '/users/{}'.format(user.id)
        bad_version = user.doc_version + 1
        # Test the presence of the ETAG header in the get
        r = user_req.get(route)
        assert r.status_code == 200, r
        assert r.headers['etag'] == str(user.doc_version)
        # Try to modify the document with bad conditions
        r = user_req.patch(route, data={'firstname': 'Doe'},
                           headers={'If-Match': bad_version})
        assert r.status_code == 412, r
        # Now use the correct condition two times
        good_version = user.doc_version
        r = user_req.patch(route, data={'firstname': 'Doe'},
                           headers={'If-Match': good_version})
        assert r.status_code == 200, r
        # Now good_version is not good anymore...
        r = user_req.patch(route, data={'firstname': 'Dooe'},
                           headers={'If-Match': good_version})
        assert r.status_code == 412, r
        # Test dummy If-Match values as well
        r = user_req.patch(route, data={'firstname': 'Dooe'},
                           headers={'If-Match': 'NaN'})
        assert r.status_code == 412, r
