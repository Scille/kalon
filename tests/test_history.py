from tests import common
import pytest
from tests.test_auth import user

from kalon.model_util import fields, HistorizedDocument
from kalon.concurrency import ConcurrencyError

from sample.permissions import POLICIES as p
from sample.model.user import User


DEFAULT_USER_PAYLOAD = {
    'email': 'new-user@test.com',
    'password': 'pass',
    'firstname': 'new',
    'lastname': 'user'
}


class Document(HistorizedDocument):
    field = fields.StringField()


class TestHistory(common.BaseTest):

    def test_history(self):
        doc = Document(field='first_version')
        doc.save()
        assert doc.doc_version == 1
        doc.field = 'new_version'
        doc.save()
        assert doc.doc_version == 2
        doc.delete()
        assert doc.doc_version == 2
        histories = Document._meta['history_cls'].objects().order_by('+date')
        assert len(histories) == 3
        assert histories[0].action == 'CREATE'
        assert histories[1].action == 'UPDATE'
        assert histories[2].action == 'DELETE'

    def test_concurrency(self):
        doc = Document(field='first_version')
        doc.save()
        assert doc.doc_version == 1
        doc.field = 'new_version'
        doc.save()
        assert doc.doc_version == 2
        doc_concurrent = Document.objects.get(pk=doc.pk)
        doc_concurrent.field = 'concurrent_version'
        doc_concurrent.save()
        assert doc_concurrent.doc_version == 3
        with pytest.raises(ConcurrencyError):
            doc.field = 'invalid_version'
            doc.save()


class TestAPIHistory(common.BaseTest):

    def test_access(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Need permission to do it
        route = '/users/%s/history' % user.pk
        r = user_req.get(route)
        assert r.status_code == 403, r
        # Now provide the permission
        user.permissions = [p.history.see.name]
        user.save()
        r = user_req.get(route)
        assert r.status_code == 200, r

    def test_api(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.history.see.name,
                            p.user.create.name,
                            p.user.modify.name]
        user.save()
        # History version 1 : creation
        r = user_req.post('/users', data=DEFAULT_USER_PAYLOAD)
        assert r.status_code == 201, r
        site_route = '/users/%s' % r.data['id']
        # History version 2 : update
        r = user_req.patch(site_route, data={'lastname': 'change 1'})
        assert r.status_code == 200, r
        # History version 3 : update
        r = user_req.patch(site_route, data={'lastname': 'change 2'})
        assert r.status_code == 200, r
        # History version 4 : delete
        site = User.objects.get(pk=r.data['id'])
        site.delete()
        # Get back & check history
        r = user_req.get('/users/%s/history' % site.pk)
        assert r.status_code == 200, r
        histories = r.data['_items']
        assert len(histories) == 4, len(histories)
        assert len([x for x in histories if x['action'] == 'CREATE']) == 1
        assert len([x for x in histories if x['action'] == 'UPDATE']) == 2
        assert len([x for x in histories if x['action'] == 'DELETE']) == 1
        # Get a single item
        r = user_req.get('/users/%s/history/%s' % (str(site.pk), histories[0]['id']))
        assert r.status_code == 200, r
        for field in ['content', 'action', 'origin',
                      'author', 'date', 'version']:
            assert field in r.data, field

    def test_bad_access(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.history.see.name,
                            p.user.create.name,
                            p.user.modify.name]
        user.save()
        # Non existing history
        r = user_req.get('/users/%s/history/554534801d41c8de989d038e' % user.pk)
        assert r.status_code == 404, r
        # Existing history, but not on this user
        doc = Document(field='first_version')
        doc.save()
        bad_history = Document._meta['history_cls'].objects()[0]
        r = user_req.get('/users/%s/history/%s' % (user.pk, bad_history.pk))
        assert r.status_code == 404, r

    @pytest.mark.xfail
    def test_links(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.history.see.name, p.user.see.name]
        user.save()
        r = user_req.get('/users/%s/history' % user.pk)
        assert r.status_code == 200, r
        history_elem_ref = r.data['_items'][0]['_links']['self']
        common.assert_links(r, ['self', 'origin'])
        history_ref = r.data['_links']['self'].split('?')[0]
        origin_ref = r.data['_links']['origin']
        r = user_req.get(r.data['_links']['origin'])
        assert r.status_code == 200, r
        assert 'history' in r.data['_links']
        assert history_ref == r.data['_links']['history']
        assert origin_ref == r.data['_links']['self']
        r = user_req.get(history_elem_ref)
        assert r.status_code == 200, r
        common.assert_links(r, ['self', 'origin', 'parent'])
        assert r.data['_links']['origin'] == origin_ref


class TestPaginationSite(common.BaseTest):

    @pytest.mark.xfail
    def test_paginate_users(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        user.permissions = [p.history.see.name,
                            p.user.create.name,
                            p.user.modify.name]
        user.save()
        payload = DEFAULT_USER_PAYLOAD.copy()
        r = user_req.post('/users', data=payload)
        assert r.status_code == 201, r
        site_id = r.data['id']
        site_route = '/users/%s' % site_id
        # Start by making plenty of changes
        for i in range(49):
            r = user_req.patch(site_route, data={'firstname': 'change-%s' % i})
            assert r.status_code == 200, r
        # Now let's test the pagination !
        common.pagination_testbed(user_req, '/users/%s/history' % site_id)
