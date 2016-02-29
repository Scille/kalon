from marshmallow import ValidationError
# Republishing the default fields...
from marshmallow_mongoengine.fields import *  # noqa

from core.view_util.schema import UnknownCheckedSchema


# ...and add custom ones


class UTCTZnaiveDateTime(DateTime):
    """
    DateTime object in UTC with no tzinfo
    """

    def _deserialize(self, value):
        value = super()._deserialize(value)
        if value and value.tzinfo:
            value = (value - value.utcoffset()).replace(tzinfo=None)
        return value


class StrictBoolean(Boolean):
    """
    Real boolean (i.e. no cast from string) validation
    """

    def _deserialize(self, value):
        if value not in (True, False, None):
            raise ValidationError('Not a boolean')
        return super()._deserialize(value)


class StrictString(String):
    """
    Real string (i.e. no desesperate cast) validation
    """

    def _deserialize(self, value):
        if not isinstance(value, str):
            raise ValidationError('Not a string')
        return super()._deserialize(value)


class StrictList(List):
    """
    Real List (i.e. no cast from string) validation
    """

    def _deserialize(self, value):
        if not isinstance(value, (list, tuple)):
            raise ValidationError('Not a list')
        return super()._deserialize(value)


class LinkedReference(Reference):
    """
    Marshmallow custom field to map with :class Mongoengine.Reference:
    """

    def _deserialize(self, value):
        # Incomming document can be 1) a single ObjectId,
        # 2) a dict containing an 'id' entry with the ObjectId
        if isinstance(value, dict):
            value = value.get('id')
            if not value:
                raise ValidationError("Champ 'id' manquant")
        return super()._deserialize(value)

    def _serialize(self, value, attr, obj):
        # Return a dict containing the id and the links if registered for
        # this document type
        if value is None:
            return missing
        dump = {'id': getattr(value, 'pk', value.id)}
        if hasattr(value, 'get_links'):
            links = value.get_links()
            if links:
                dump['_links'] = links
        return dump


class LinkedGenericReference(GenericReference):
    """
    Marshmallow custom field to map with :class Mongoengine.GenericReference:
    """

    def _serialize(self, value, attr, obj):
        # Return a dict containing the id and the links if registered for
        # this document type
        if value is None:
            return missing
        dump = {'id': getattr(value, 'pk', value.id),
                '_cls': value._class_name}
        if hasattr(value, 'get_links'):
            links = value.get_links()
            if links:
                dump['_links'] = links
        return dump


# Monkey patch to replace default DocumentReference field by our custom one
from marshmallow_mongoengine import register_field, register_field_builder
from marshmallow_mongoengine.conversion.fields import (
    ReferenceBuilder, ListBuilder, EmbeddedDocumentBuilder, GenericReferenceBuilder)

from core.model_util import fields as me_fields


class ReferenceBuilder(ReferenceBuilder):
    MARSHMALLOW_FIELD_CLS = LinkedReference
register_field_builder(me_fields.ReferenceField, ReferenceBuilder)


class ListBuilder(ListBuilder):
    MARSHMALLOW_FIELD_CLS = StrictList
register_field_builder(me_fields.ListField, ListBuilder)


class EmbeddedDocumentBuilder(EmbeddedDocumentBuilder):
    BASE_NESTED_SCHEMA_CLS = UnknownCheckedSchema
register_field_builder(me_fields.EmbeddedDocumentField, EmbeddedDocumentBuilder)


class GenericReferenceBuilder(GenericReferenceBuilder):
    MARSHMALLOW_FIELD_CLS = LinkedGenericReference
register_field_builder(me_fields.GenericReferenceField, GenericReferenceBuilder)

register_field(me_fields.BooleanField, StrictBoolean)
register_field(me_fields.StringField, StrictString)
register_field(me_fields.DateTimeField, UTCTZnaiveDateTime)
register_field(me_fields.ComplexDateTimeField, UTCTZnaiveDateTime)
