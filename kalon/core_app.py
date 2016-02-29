from os.path import abspath, dirname
from flask import Flask
from flask.ext.principal import Principal
from flask.ext import restful, cors
from flask.ext.mongoengine import MongoEngine

from core.encoders import dynamic_json_encoder_factory, ObjectIdConverter, JsonRequest
from core.solr import Solr


class CoreApp(Flask):
    """
    CoreApp is a regular :class:`Flask` app with cors, flask-principal,
    "restfulness" flavors
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Support objectid in url routing
        self.url_map.converters['objectid'] = ObjectIdConverter
        # Custom json encoder for objectid and pagination
        # Mix between flask's root_path (module's path) and running dir path
        self.root_path = abspath(dirname(__file__) + '/..')
        # Overload default request to return 400 if no payload is provided
        self.request_class = JsonRequest
        self.json_encoder = dynamic_json_encoder_factory()
        restful.representations.json.settings['cls'] = self.json_encoder
        self.db = MongoEngine()
        self.solr = Solr()

    def bootstrap(self):
        """
        Initialize modules needing configuration

        :example:

            >>> app = CoreApp("my-app")
            >>> app.config['MY_CONF'] = 'DEFAULT_VALUE'
            >>> app.bootstrap()
        """
        # Principal and CORS support must be initialized at bootstrap time
        # in order to have up-to-date config
        self._principal = Principal(self, use_sessions=False)
        self._cors = cors.CORS(self)
        self.db.init_app(self)
        self.solr.init_app(self)
