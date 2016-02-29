from datetime import datetime
from flask.ext.mongoengine import mongoengine, Document

from core.concurrency import ConcurrencyError
from core.auth import current_user


def _get_current_user():
    try:
        return current_user.id
    except (RuntimeError, AttributeError):
        # If working outside flask context (i.g. init test for exemple)
        # there is no current user
        return None


class VersionedDocument(Document):
    """
    Mongoengine abstract document handling version, udpated and created fields
    as long as concurrent modifications handling
    """
    doc_version = mongoengine.IntField(required=True, default=1)
    doc_updated = mongoengine.DateTimeField(default=datetime.utcnow)
    doc_created = mongoengine.DateTimeField(default=datetime.utcnow)
    meta = {'abstract': True, '_version_bootstrapped': False}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap_version()

    @staticmethod
    def _version_pre_save(sender, document, **kwargs):
        """
        Update version and modified date on document change
        """
        if document.pk:
            document.doc_updated = datetime.utcnow()
            document.doc_version += 1

    @classmethod
    def _bootstrap_version(cls):
        if not cls._meta['_version_bootstrapped']:
            cls._meta['_version_bootstrapped'] = True
            # Signal to update metadata on document change
            mongoengine.signals.pre_save.connect(cls._version_pre_save, sender=cls)

    def save(self, *args, **kwargs):
        # Check for race condition on insert
        if self.pk:
            if 'save_condition' not in kwargs:
                kwargs['save_condition'] = {}
            if 'doc_version' not in kwargs['save_condition']:
                kwargs['save_condition']['doc_version'] = self.doc_version
        try:
            return super().save(*args, **kwargs)
        except mongoengine.errors.OperationError as e:
            # TODO: fix this when https://github.com/MongoEngine/mongoengine/pull/1070 is upstream
            if type(e) is mongoengine.errors.OperationError:
                raise ConcurrencyError()
            else:
                raise


class HistorizedDocument(VersionedDocument):
    """
    Mongoengine abstract document handling history and race condition
    """
    meta = {'abstract': True, 'history_cls': None}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history_cls = self._bootstrap_history_cls()
        # Shorthand to get the history of the current document
        self.get_history = lambda *args, **kwargs: \
            self.history_cls.objects(*args, origin=self, **kwargs)

    @staticmethod
    def _history_post_delete(sender, document):
        """Create HistoryItem on delete"""
        version = document.doc_version + 1
        history_cls = sender._meta['history_cls']
        item = history_cls(origin=document, author=_get_current_user(),
                           action='DELETE', version=version,
                           date=datetime.utcnow())
        item.save()

    @staticmethod
    def _history_post_save(sender, document, created):
        """Create HistoryItem document modification"""
        history_cls = sender._meta['history_cls']
        item = history_cls(origin=document,
                           author=_get_current_user(),
                           action='CREATE' if created else 'UPDATE',
                           # content=document.to_mongo().to_dict(),
                           content=document.to_json(),
                           version=document.doc_version,
                           date=document.doc_updated)
        item.save()

    @classmethod
    def _bootstrap_history_cls(cls):
        if cls._meta['history_cls']:
            return cls._meta['history_cls']
        collection = cls._meta['collection'] + '.history'
        assert collection != '.history', cls

        class HistoryItem(Document):
            meta = {'collection': collection}
            origin = mongoengine.ReferenceField(cls, required=True)
            author = mongoengine.ReferenceField('User') # TODO should be configurable
            # content = mongoengine.DictField()
            content = mongoengine.StringField()
            action = mongoengine.StringField(choices=['CREATE', 'UPDATE', 'DELETE'], required=True)
            version = mongoengine.IntField(required=True)
            date = mongoengine.DateTimeField(required=True)

        cls._meta['history_cls'] = HistoryItem
        # Register signals to trigger history creation
        mongoengine.signals.post_save.connect(cls._history_post_save, sender=cls)
        mongoengine.signals.post_delete.connect(cls._history_post_delete, sender=cls)
        return cls._meta['history_cls']
