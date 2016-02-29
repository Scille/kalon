from flask.ext.mongoengine import mongoengine, Document

from core.tools import abort


class BaseController:
    """
    Controller base class, providing usefull function for handling document
    """
    def __init__(self, document):
        self.document = document

    def save_or_abort(self, abort=abort, if_match=None):
        try:
            if if_match is True:
                self.document.save(save_condition={"doc_version": self.document.doc_version})
            elif if_match:
                self.document.save(save_condition={"doc_version": if_match})
            else:
                self.document.save()
        except mongoengine.ValidationError as e:
            errors = e.to_dict()
            if errors:
                # ValidationErrors issued in the clean function are wrapped
                # in a useless NON_FIELD_ERRORS
                non_field_errors = errors.pop(mongoengine.base.NON_FIELD_ERRORS, {})
                if isinstance(non_field_errors, dict):
                    errors.update(non_field_errors)
                    abort(400, **errors)
                else:
                    abort(400, non_field_errors)
            else:
                abort(400, e.message)
        except mongoengine.errors.NotUniqueError as e:
            abort(400, str(e))
        except mongoengine.errors.FieldDoesNotExist as e:
            abort(400, str(e))

    def update(self, payload):
        for key, value in payload.items():
            setattr(self.document, key, value)


class ControlledDocument(Document):
    """
    Mongoengine abstract document providing a controller attribute to
    alter with style the document !
    """
    meta = {'abstract': True, 'controller_cls': BaseController}

    @property
    def controller(self):
        controller_cls = self._meta.get('controller_cls')
        if not controller_cls:
            raise NotImplementedError('No controller setted for this document')
        return controller_cls(self)

    def clean(self):
        """Automatically called at save time, triggers controller's clean"""
        ctrl = self.controller
        if hasattr(ctrl, 'clean'):
            ctrl.clean()
