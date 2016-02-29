from flask import url_for
from flask.ext.mongoengine import Document

from core.model_util.version import HistorizedDocument
from core.model_util.searcher import SearchableDocument
from core.model_util.controller import ControlledDocument


class LinkedDocument(Document):
    """
    Mongoengine abstract document providing a way to get links metadata
    from a document
    """
    meta = {'abstract': True}

    @classmethod
    def set_link_builder_from_api(cls, api):
        if not isinstance(api, str):
            api = api.__name__
        cls._meta['linker_builder'] = lambda obj: {'self': url_for(api, item_id=obj.pk)}

    @classmethod
    def set_link_builder(cls, builder):
        cls._meta['linker_builder'] = builder

    def get_links(self):
        if not self._meta.get('linker_builder'):
            return None
        return self._meta['linker_builder'](self)


class Marshallable(Document):
    """
    Special unmarshal to properly handle properties
    """
    meta = {'abstract': True}

    class Marshaller:

        def __init__(self, doc):
            self.doc = doc

        def __getitem__(self, key):
            return getattr(self.doc, key)

    def __marshallable__(self):
        return self.Marshaller(self)


class BaseDocument(ControlledDocument, Marshallable, HistorizedDocument,
                   SearchableDocument, LinkedDocument):
    """
    Document default class, all actual documents should inherit from this one
    """
    meta = {'abstract': True}
