import re
import mongoengine
from pysolr import SolrError
from flask import current_app

from core.tools import list_to_pagination
from core.model_util.version import VersionedDocument


class AsbFieldSolrConverter:
    """
    Abstract class for a converter from mongoengine field to solr

    A converter must implement two methods
    """
    FIELD_CLS = None
    FIELD_SOLR_EXTENSION = None

    def __init__(self, field_name, solr_field_name=None, extractor=None,
                 serializer=None, replace_aliases=None, aliases=None, multi=False):
        """
        :param field_name: name of the field
        :param solr_field_name: name of the field in solr
        :param extractor: function used to retrieve the field's
        value from it document
        :param serializer: function used to generate the dict of solr fields
        and their associated values
        :param replace_aliases: function used to replace the aliases in a query by
        their actual solr field names
        :param aliases: list of possible aliases of this field in a query
        :param multi: the extractor will returns a list of value, thus
        the solr field should be considered as multiple

        .. note : If multi=True the solr fields names will be corrected with a
            trailing "s" (e.g. "_s" ==> "_ss" for multi)
        """
        assert self.FIELD_CLS, 'FIELD_CLS must be set'
        assert self.FIELD_SOLR_EXTENSION, 'FIELD_SOLR_EXTENSION must be set'
        self._field_name = field_name
        if solr_field_name:
            self._solr_field_name = solr_field_name
        else:
            self._solr_field_name = field_name + self.FIELD_SOLR_EXTENSION
        if multi:
            self._solr_field_name += 's'
        self._extractor = extractor
        self._serializer = serializer
        self._replace_aliases = replace_aliases
        self._aliases = aliases or ()
        self._multi = multi

    def replace_aliases(self, query):
        """
        Look for the field possible aliases in the query and replace them by
        the actual solr field name
        """
        for alias in self._aliases:
            query = re.sub(r"\b%s\b" % alias, self._solr_field_name, query)
        if self._replace_aliases:
            return self._replace_aliases(query)
        else:
            return re.sub(r"\b%s\b" % self._field_name, self._solr_field_name, query)

    def _serialize(self, value):
        # Default serializer
        return {self._solr_field_name: value}

    def build_solr(self, doc):
        """
        Generate a dic of solr fields with their values from the given document
        """
        if self._extractor:
            value = self._extractor(doc)
        else:
            # Default value extractor
            value = getattr(doc, self._field_name, None)
        if not value:
            return {}
        if self._multi:
            if not isinstance(value, (list, tuple)):
                value = (value,)
            return self._multi_serialize_and_reduce(value)
        else:
            return self._serialize(value)

    def _multi_serialize_and_reduce(self, values):
        # Run the serialize for each value and merge the results
        reduced = {}
        for doc in [self._serialize(v) for v in values if v]:
            for key, value in doc.items():
                if key not in reduced:
                    reduced[key] = []
                reduced[key].append(value)
        return reduced

    @classmethod
    def can_convert(self, field_cls):
        """
        Determine if the given field can be handled by the converter
        """
        return issubclass(field_cls, self.FIELD_CLS)


class StringFieldSolrConverter(AsbFieldSolrConverter):
    FIELD_CLS = mongoengine.fields.StringField
    FIELD_SOLR_EXTENSION = '_s'


class IntFieldSolrConverter(AsbFieldSolrConverter):
    FIELD_CLS = mongoengine.fields.IntField
    FIELD_SOLR_EXTENSION = '_i'


class FloatFieldSolrConverter(AsbFieldSolrConverter):
    FIELD_CLS = mongoengine.fields.FloatField
    FIELD_SOLR_EXTENSION = '_f'


class DateTimeFieldSolrConverter(AsbFieldSolrConverter):
    FIELD_CLS = mongoengine.fields.DateTimeField
    FIELD_SOLR_EXTENSION = '_dt'


class BooleanFieldSolrConverter(AsbFieldSolrConverter):
    FIELD_CLS = mongoengine.fields.BooleanField
    FIELD_SOLR_EXTENSION = '_b'


class GenericReferenceFieldSolrConverter(AsbFieldSolrConverter):
    FIELD_CLS = mongoengine.fields.GenericReferenceField
    FIELD_SOLR_EXTENSION = '_r'

    def _serialize(self, value):
        return {self._solr_field_name: str(value.id)}


class ReferenceFieldSolrConverter(AsbFieldSolrConverter):
    FIELD_CLS = mongoengine.fields.ReferenceField
    FIELD_SOLR_EXTENSION = '_r'

    def _serialize(self, value):
        return {self._solr_field_name: str(value.id)}


class SolrFieldConverterManager:
    """
    Store the available converters class and provide a convenient way
    to tests
    """

    def __init__(self):
        # Default converters for base types
        self._converters = [
            StringFieldSolrConverter,
            IntFieldSolrConverter,
            FloatFieldSolrConverter,
            DateTimeFieldSolrConverter,
            BooleanFieldSolrConverter,
            GenericReferenceFieldSolrConverter,
            ReferenceFieldSolrConverter
        ]

    def register_converter_cls(self, converter_cls):
        """
        Add a new converter class.
        """
        # Register backward to prevent base generic fields to shadow
        self._converters.insert(0, converter_cls)

    def build_converter(self, field_name, field, **kwargs):
        """
        Retrieve and build a converter for the given field

        :param field_name: name of the field
        :param field: field on which the converter will be used
        :param kwargs: additional params passed to converter ``__init__``

        .. note : If multiple converter can match the field, the one
            added last will be used
        """
        if isinstance(field, mongoengine.fields.ListField):
            kwargs.setdefault('multi', True)
            field_cls = type(field.field)
        else:
            kwargs.setdefault('multi', False)
            field_cls = type(field)
        converter = next((c for c in self._converters
                          if c.can_convert(field_cls)), None)
        return converter(field_name, **kwargs)


# Created a single default instance and register shortcuts
solr_field_converter_manager = SolrFieldConverterManager()
solr_register_field_converter = solr_field_converter_manager.register_converter_cls
solr_build_converter = solr_field_converter_manager.build_converter


class Searcher:
    """
    Abstract default searcher class
    """

    def __init__(self, document_cls):
        self.document_cls = document_cls

    def search_or_abort(self, **kwargs):
        raise NotImplementedError()

    def build_document(self, document):
        """Register into solr the current mongoengine document"""
        raise NotImplementedError()

    def clear_document(self, document):
        """Remove from solr the current mongoengine document"""
        document = document or self.document
        raise NotImplementedError()

    @staticmethod
    def on_post_delete(sender, document):
        document.searcher.clear_document(document)

    @staticmethod
    def on_post_save(sender, document, created):
        document.searcher.build_document(document)


def get_document_base_type(document):
    return document._class_name.split('.')[0]


class BaseSolrSearcher(Searcher):
    """
    Base searcher class for solr integration
    """

    FIELDS = ()

    def __init__(self, *args, converters=None, **kwargs):
        super().__init__(*args, **kwargs)
        dcls = self.document_cls
        # Add default fields
        self.converters = [
            StringFieldSolrConverter('id', extractor=lambda doc: str(doc.id),
                                     solr_field_name='doc_id'),
            StringFieldSolrConverter('_class_name', solr_field_name='doc_type',
                                     replace_aliases=lambda x: x),
            StringFieldSolrConverter('_class_name', solr_field_name='doc_base_type',
                extractor=get_document_base_type, replace_aliases=lambda x: x),
            IntFieldSolrConverter('doc_version', aliases=('_version',)),
            DateTimeFieldSolrConverter('doc_updated', aliases=('_updated',)),
            DateTimeFieldSolrConverter('doc_created', aliases=('_created',)),
        ]
        for field in self.FIELDS:
            field_cls = getattr(dcls, field, None)
            if field_cls:
                self.converters.append(solr_build_converter(field, field_cls))

    def build_and_register_converter(self, *args, **kwargs):
        self.converters.append(solr_build_converter(*args, **kwargs))

    def register_custom_field(self, field_name, field_cls, field_extractor, alias=None):
        """
        Register a special field for the solr document

        :param field_name: name of the field in solr
        :param field_cls: mongoengine class of the field
        :param field_extractor: function that return the field's value
        from a given document or None
        :param alias: list of additional alias for the field
        """
        self.converters.append(
            solr_build_converter(field_name, field_cls, extractor=field_extractor, aliases=alias))

    def _replace_aliases(self, query):
        for c in self.converters:
            query = c.replace_aliases(query)
        return query

    def search_or_abort(self, q=None, fq=None, sort=None, page=1, per_page=20):
        """

        :param q: solr style query
        :param fq: solr style list of query filters
        :param sort: solr style list of query sorters
        :param page: current page to retrieve
        :param per_page: number of elements per page
        :return: a ``Pagination`` of mongoengine documents
        """
        if not q:
            q = '*:*'
        else:
            q = self._replace_aliases(q)
        kwargs = {'start': (page - 1) * per_page, 'rows': per_page, 'q': q}
        if fq:
            kwargs['fq'] = [self._replace_aliases(e) for e in fq]
        if sort:
            kwargs['sort'] = [self._replace_aliases(e) for e in sort]
        try:
            docs = self.solr_search(**kwargs)
            hits = docs.hits
        except SolrError as e:
            current_app.logger.warning('SolrError: %s' % str(e))
            docs = ()
            hits = 0
        # Pagination is already handled by solr, thus we use a dummy
        # one in mongo and correct it according to solr's query
        items = self.document_cls.objects(pk__in=[d['doc_id'] for d in docs])
        if 'sort' in kwargs:
            # If needed, reorder the results from mongo to match the original
            # order provided by solr
            ordered_items = []
            for d in docs:
                doc_id = d['doc_id']
                for item in items:
                    pk = str(item.pk)
                    if pk == doc_id:
                        ordered_items.append(item)
            items = ordered_items
        items = list_to_pagination(items, already_sliced=True, page=page,
                                   per_page=per_page, total=hits,
                                   q=q, fq=fq, sort=sort)
        return items

    def generate_solr_doc(self, document):
        """
        Create a solr document from a mongoengine document
        """
        sdoc = {
            'id': '%s-%s' % (document._class_name, document.pk),
        }
        for c in self.converters:
            sdoc.update(c.build_solr(document))
        return sdoc

    def build_document(self, document, **kwargs):
        """
        Register into solr the current mongoengine document
        """
        kwargs.setdefault('commit', False)
        kwargs.setdefault('waitFlush', False)
        doc = self.generate_solr_doc(document)
        # Given we use document's pk as solr id, no need to clear the
        # previous solr document (will be replace by the new one)
        current_app.solr.add((doc,), **kwargs)

    def clear_document(self, document, **kwargs):
        """
        Remove from solr the current mongoengine document
        """
        kwargs.setdefault('commit', False)
        kwargs.setdefault('waitFlush', False)
        if document.pk:
            current_app.solr.delete(id=str(document.pk), **kwargs)

    def clear_collection(self, **kwargs):
        """
        Remove the entire collection from solr
        """
        kwargs.setdefault('commit', False)
        kwargs.setdefault('waitFlush', False)
        base_type = get_document_base_type(self.document_cls)
        current_app.solr.delete(q='doc_base_type:' + base_type, **kwargs)

    def solr_search(self, q, fq=None, sort=None, **kwargs):
        """
        Do a solr query limited to the current collection
        """
        fq = fq or []
        if sort:
            if isinstance(sort, (list, tuple)):
                sort = ','.join(sort)
            kwargs['sort'] = sort
        base_type = get_document_base_type(self.document_cls)
        fq.append('doc_base_type:' + base_type)
        return current_app.solr.search(q, fq=fq, **kwargs)


class SearchableDocument(VersionedDocument):
    """
    Mongoengine abstract document providing search functionalities
    """
    meta = {'abstract': True, 'searcher_cls': None, '_searcher': None}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        searcher_cls = self._meta.get('searcher_cls')
        if searcher_cls:
            self.searcher = self._search_bootstrap()

    @classmethod
    def _search_bootstrap(cls):
        if cls._meta['_searcher']:
            return cls._meta['_searcher']
        # Register signals to trigger solr sync
        searcher_cls = cls._meta.get('searcher_cls')
        if not searcher_cls:
            raise NotImplementedError('No searcher setted for this document')
        searcher = searcher_cls(cls)
        mongoengine.signals.post_save.connect(searcher.on_post_save, sender=cls)
        mongoengine.signals.post_delete.connect(searcher.on_post_delete, sender=cls)
        cls._meta['_searcher'] = searcher
        return searcher

    @classmethod
    def search_or_abort(cls, *args, **kwargs):
        """
        Shortcut to ``SearchableDocument.searcher.search_or_abort``
        """
        return cls._search_bootstrap().search_or_abort(*args, **kwargs)
