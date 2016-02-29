import pytest
from mongoengine import ValidationError as MongoValidationError

from tests import common
from tests.fixtures import *

from kalon.model_util import (Document, HistorizedDocument, BaseController,
                              ControlledDocument, VersionedDocument)
from kalon.concurrency import ConcurrencyError
from sample.model import fields

class TestController(common.BaseTest):

    def test_controller(self):
        def controller_factory(document):
            router = {
                'ready': ReadyController,
                'fired': FiredController,
                'reloading': ReloadingController
            }
            return router[document.status](document)
        class ReadyController(BaseController):
            def state(self):
                return "%s is ready to fire" % self.document.name
            def fire(self):
                self.document.status = 'fired'
                self.document.save()
        class FiredController(BaseController):
            def state(self):
                return "%s is empty" % self.document.name
            def reload(self):
                self.document.status = 'reloading'
                self.document.save()
        class ReloadingController(BaseController):
            def state(self):
                return "%s is reloading..." % self.document.name
            def done(self):
                self.document.status = 'ready'
                self.document.save()
        class Gun(ControlledDocument):
            meta = {'controller_cls': controller_factory}
            name = fields.StringField(required=True)
            status = fields.StringField(choices=['ready', 'fired', 'reloading'], required=True)
        doc = Gun(name='gun-1', status='ready')
        doc.save()
        assert isinstance(doc.controller, ReadyController)
        assert hasattr(doc.controller, 'fire')
        assert doc.controller.state() == 'gun-1 is ready to fire'
        doc.controller.fire()
        assert isinstance(doc.controller, FiredController)
        assert doc.controller.state() == 'gun-1 is empty'
        doc.controller.reload()
        assert isinstance(doc.controller, ReloadingController)
        doc.controller.done()

    def test_dualinheritance(self):
        class DualInheritanceController(BaseController):
            def make_v2(self):
                self.document.field = 'v2'
                self.document.save()
        class DualInheritanceDoc(ControlledDocument, HistorizedDocument):
            meta = {'controller_cls': DualInheritanceController}
            field = fields.StringField()
        doc = DualInheritanceDoc(field='v1')
        doc.save()
        # Make sure we have both history and controller functionalities
        assert isinstance(doc.controller, DualInheritanceController)
        doc.controller.make_v2()
        assert hasattr(doc, 'get_history')
        history = doc.get_history()
        assert history.count() == 2


class TestConcurrency(common.BaseTest):
    def test_concurrency(self):
        class Doc(VersionedDocument):
            field = fields.StringField()
        doc = Doc(field="v1")
        doc.save()
        assert doc.doc_version == 1
        doc_concurrent = Doc.objects(field="v1").first()
        assert doc_concurrent
        doc.field = "v2"
        doc_concurrent.field = "v2_alternate"
        doc_concurrent.save()
        assert doc_concurrent.doc_version == 2
        with pytest.raises(ConcurrencyError):
            doc.save()
        doc.reload()
        assert doc.field == doc_concurrent.field
        assert doc.doc_version == 2
