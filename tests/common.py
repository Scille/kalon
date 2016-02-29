import json
import pytest
from collections import namedtuple
from sample.main import bootstrap_app, create_app
from kalon.auth import generate_access_token


class NOT_SET:

    def __repr__(self):
        return '<not_set>'
NOT_SET = NOT_SET()


def update_payload(payload, route, value):
    splitted = route.split('.')
    cur_node = payload
    for key in splitted[:-1]:
        if isinstance(cur_node, (list, tuple)):
            key = int(key)
            if len(cur_node) <= key:
                raise ValueError('indice %s is not in list' % key)
        elif isinstance(cur_node, dict):
            if key not in cur_node:
                cur_node[key] = {}
        else:
            raise ValueError('%s must lead to a dict' % key)
        cur_node = cur_node[key]
    last_key = splitted[-1]
    if value is NOT_SET:
        if last_key in cur_node:
            del cur_node[last_key]
    elif isinstance(cur_node, (list, tuple)):
        cur_node[int(last_key)] = value
    else:
        cur_node[last_key] = value


def assert_links(response, links):
    assert '_links' in response.data
    data_links = response.data['_links']
    for l in links:
        assert l in data_links, l
    assert not data_links.keys() - set(links)


class AuthRequests:

    """Wrap user model to easily do requests on the api with it credentials"""

    CookedResponse = namedtuple('CookedResponse', ['status_code', 'headers', 'data'])

    def __init__(self, document, app, client_app):
        self.document = document
        self.client_app = client_app
        self.app = app
        # generate a token for the requests
        with self.app.app_context():
            self.token = generate_access_token(document.email,
                                               document.password, fresh=True)

    def _decode_response(self, response):
        encoded = response.get_data()
        if encoded:
            decoded = json.loads(encoded.decode('utf-8'))
            assert isinstance(decoded, dict)
        else:
            decoded = encoded
        return self.CookedResponse(response.status_code, response.headers, decoded)

    def __getattr__(self, name):
        method_name = name.upper()
        if method_name not in ['POST', 'PATCH', 'PUT', 'GET',
                               'OPTIONS', 'HEAD', 'DELETE']:
            return super().__getattr__(name)

        def caller(route, headers=None, data=None, auth=True, dump_data=True, **kwargs):
            if dump_data:
                serial_data = json.dumps(data, cls=self.app.json_encoder)
            else:
                serial_data = data
            headers = headers or {}
            if auth:
                headers['Authorization'] = 'Token ' + self.token
            params = {
                'headers': headers,
                'content_type': 'application/json',
                'content_length': len(serial_data)
            }
            params.update(kwargs)
            if data or isinstance(data, dict):
                params['data'] = serial_data
            method_fn = getattr(self.client_app, method_name.lower())
            return self._decode_response(method_fn(route, **params))
        return caller


class ClientAppRouteWrapper(object):

    def __init__(self, app):
        self.app = app
        self.client_app = app.test_client()

    def _wrap(self, fn):
        url_prefix = self.app.config['BACKEND_API_PREFIX']
        if not url_prefix:
            return fn

        def wrapper(route, *args, force_route=False, **kwargs):
            if not force_route and not route.startswith(url_prefix):
                route = url_prefix + route
            return fn(route, *args, **kwargs)
        return wrapper

    def __getattr__(self, method_name):
        if method_name in ['post', 'patch', 'put', 'get',
                           'options', 'head', 'delete']:
            return self._wrap(getattr(self.client_app, method_name))
        return super().__getattr__(method_name)


class BaseTest:

    client_app = None

    def make_auth_request(self, user, password):
        return AuthRequests(user, self.app, self.client_app)

    @classmethod
    def _clean_solr(cls):
        cls.app.solr.delete(q='*:*', waitFlush=True)

    @classmethod
    def _clean_db(cls):
        cls.app.db.connection.drop_database(
            cls.app.db.connection.get_default_database().name)

    @classmethod
    def setup_class(cls):
        """
        Initialize flask app and configure it with a clean test database
        """
        runsolr = pytest.config.getoption('runsolr')
        app = create_app()
        app.testing = True
        if runsolr:
            test_config = {
                'MONGODB_HOST': app.config['MONGODB_TEST_URL'],
                'SOLR_URL': app.config['SOLR_TEST_URL'],
                'DISABLE_SOLR': False,
                'TESTING': True
            }
        else:
            test_config = {
                'MONGODB_HOST': app.config['MONGODB_TEST_URL'],
                'DISABLE_SOLR': True,
                'TESTING': True
            }
        test_config['DISABLE_MAIL'] = False
        test_config['MAIL_SUPPRESS_SEND'] = True
        bootstrap_app(app=app, config=test_config)

        cls.app = app
        cls.ctx = app.app_context()
        cls.ctx.push()
        cls.client_app = ClientAppRouteWrapper(app)
        if runsolr:
            cls._clean_solr()
        cls._clean_db()

    @classmethod
    def teardown_class(cls):
        cls.ctx.pop()


@pytest.mark.solr
class BaseSolrTest(BaseTest):
    pass


def pagination_testbed(user_req, route):
    """
    Generic pagination test (just need to populate 50 documents before)
    """
    r = user_req.get(route)
    assert r.status_code == 200
    assert r.data['_meta']['total'] == 50, ('Must be 50 elements in the'
                                            ' ressource to use the testbed !')
    items_len = len(r.data['_items'])
    if items_len < r.data['_meta']['per_page']:
        assert items_len == r.data['_meta']['total']
    else:
        assert items_len == r.data['_meta']['per_page']
    assert '_links' in r.data['_items'][0], r.data['_items'][0]
    assert 'self' in r.data['_items'][0]['_links'], r.data['_items'][0]
    assert 'parent' in r.data['_items'][0]['_links'], r.data['_items'][0]
    # Now let's test the pagination !

    def check_page(data, page, count, per_page, total):
        assert len(r.data['_items']) == count
        assert r.data['_meta']['page'] == page
        assert r.data['_meta']['per_page'] == per_page
        assert r.data['_meta']['total'] == total
    for page, count, per_page in [(1, 20, 20), (2, 20, 20), (3, 10, 20),
                                  (1, 50, 50), (1, 50, 100), (8, 1, 7)]:
        r = user_req.get('%s?page=%s&per_page=%s' % (route, page, per_page))
        assert r.status_code == 200, r
        check_page(r.data, page, count, per_page, 50)
    # Test links
    r = user_req.get('%s?page=1&per_page=100' % route)
    assert r.status_code == 200, r
    assert 'next' not in r.data['_links']
    assert 'previous' not in r.data['_links']
    assert 'self' in r.data['_links']
    r = user_req.get('%s?page=1&per_page=10' % route)
    assert r.status_code == 200, r
    assert 'next' in r.data['_links']
    assert 'previous' not in r.data['_links']
    assert 'self' in r.data['_links']
    r = user_req.get('%s?page=2&per_page=10' % route)
    assert r.status_code == 200, r
    assert 'next' in r.data['_links']
    assert 'previous' in r.data['_links']
    assert 'self' in r.data['_links']
    # Test bad pagination as well
    r = user_req.get('%s?page=2&per_page=60' % route)
    assert r.status_code == 404, r
    for page, per_page in [('', 20), (1, ''), ('nan', 20), (1, 'nan'),
                           (-1, 20), (1, -20)]:
        r = user_req.get('%s?page=%s&per_page=%s' % (route, page, per_page))
        assert r.status_code == 400, (page, per_page)
