import simplejson as json
import bson
import datetime
from werkzeug.routing import BaseConverter, ValidationError
from flask import Request
# using flask.ext.mongoengine import makes isinstance fail
from flask_mongoengine.pagination import Pagination
from mongoengine import Document

from core.view_util.fields import LinkedGenericReference


class JsonRequest(Request):
    """
    Default flask ``request.get_json()`` returns ``None`` if no payload
    has been provided.
    This class fix this behavior by making get_json failed on missing payload
    """
    def get_json(self, *args, **kwargs):
        json = super().get_json(*args, **kwargs)
        if json is None:
            self.on_json_loading_failed('no payload provided')
        return json


def dynamic_json_encoder_factory():
    """
    Handle a JSONEncoder that can be dynamically constructed by adding
    new class and their encoding function
    """

    class DynamicJSONEncoder(json.JSONEncoder):
        ENCODERS = []

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Initialize default encoders

            def encode_pagination(obj):
                return {
                    '_items': obj.items,
                    '_meta': {
                        'page': obj.page,
                        'per_page': obj.per_page,
                        'total': obj.total
                    }
                }

            self.ENCODERS = [
                ((datetime.datetime, datetime.date), lambda x: x.isoformat()),
                (bson.ObjectId, lambda x: str(x)),
                (set, lambda x: list(x)),
                (Pagination, encode_pagination),
                (Document, lambda x: LinkedGenericReference(type(x))._serialize(x, None, None))
            ]

        def default(self, obj):
            for cls, fnc in self.ENCODERS:
                if isinstance(obj, cls):
                    return fnc(obj)
            return super().default(obj)

        @classmethod
        def register(cls, target_cls, fnc):
            cls.ENCODERS.append((target_cls, fnc))

    return DynamicJSONEncoder


class ObjectIdConverter(BaseConverter):
    """
        werkzeug converter to use ObjectId in url ::

            >>> from flask import Flask
            >>> app = Flask(__name__)
            >>> app.url_map.converters['objectid'] = ObjectIdConverter
            >>> @app.route('/objs/<objectid:object_id>')
            ... def route(object_id): return 'ok'
            ...
    """
    def to_python(self, value):
        try:
            return bson.ObjectId(value)
        except bson.errors.InvalidId:
            raise ValidationError()

    def to_url(self, value):
        return str(value)
