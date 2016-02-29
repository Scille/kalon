from marshmallow import MarshalResult, Schema, validates_schema, ValidationError
from marshmallow_mongoengine import ModelSchema, fields
from flask import request
from flask.ext.restful import abort


def get_pagination_urlargs(default_per_page=20):
    msg = 'must be number > 0'
    try:
        page = int(request.args.get('page', 1))
        if page <= 0:
            abort(400, page=msg)
    except ValueError:
        abort(400, page=msg)
    if 'per_page' not in request.args:
        return page, default_per_page
    try:
        per_page = int(request.args['per_page'])
        if per_page <= 0:
            abort(400, page=msg)
    except ValueError:
        abort(400, page=msg)
    return page, per_page


class PaginationSerializer:

    def __init__(self, elem_serializer, route):
        """
        :params elem_serializer: serializer to use on each item. If callable
        it is expected to return the actual serializer to use after being
        called with the current item to serialize
        :params route: base route to use in the links of the pagination
        """
        self.elem_serializer = elem_serializer
        self.route = route

    def dump(self, pagination, links=None):
        serialized_items = []
        errors = []
        links = links or {}
        for item in pagination.items:
            if callable(self.elem_serializer):
                serializer = self.elem_serializer(item)
                result = serializer.dump(item)
            else:
                result = self.elem_serializer.dump(item)
            serialized_items.append(result.data)
            errors += result.errors
        result = MarshalResult(data={
            '_items': serialized_items,
            '_meta': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total
            },
            '_links': links
        }, errors=errors)
        args = []
        for field in ('q', 'fq', 'sort', 'per_page'):
            item = getattr(pagination, field, None)
            if item:
                if isinstance(item, (list, tuple)):
                    for i in item:
                        args.append('%s=%s' % (field, i))
                else:
                    args.append('%s=%s' % (field, item))
        base_route = self.route + '?' + '&'.join(args)

        def make_route(current_page):
            return base_route + '&page=%s' % current_page

        result.data['_links']['self'] = make_route(pagination.page)
        if pagination.page * pagination.per_page < pagination.total:
            result.data['_links']['next'] = make_route(pagination.page + 1)
        if pagination.page > 1:
            result.data['_links']['previous'] = make_route(pagination.page - 1)
        return result


class LinkedSchema(Schema):

    """
    Marshmallow Schema providing _links entry in it dump
    """

    def dump(self, obj, many=None, links=None, **kwargs):
        if many:
            raise NotImplementedError("Doesn't support many dump, sorry.")
        result = super().dump(obj, many, **kwargs)
        if not result.errors:
            # Default links uses current request path
            if not links:
                links = getattr(self.Meta, 'links', {})
            if callable(links):
                links = links(obj)
            result.data['_links'] = links
        return result


class UnknownCheckedSchema(ModelSchema):

    """
    ModelSchema with check for unknown field
    """

    @validates_schema(pass_original=True)
    def check_unknown_fields(self, data, original_data):
        for key in original_data:
            if key not in self.fields or self.fields[key].dump_only:
                raise ValidationError('Unknown field name {}'.format(key))


class BaseModelSchema(UnknownCheckedSchema):

    """
    Base schema to handle the default fields of a BaseModel
    """
    BASE_FIELDS = ('id', '_version', '_created', '_updated', '_links')
    id = fields.String(dump_only=True)
    _version = fields.Integer(dump_only=True, attribute="doc_version")
    _created = fields.DateTime(dump_only=True, attribute="doc_created")
    _updated = fields.DateTime(dump_only=True, attribute="doc_updated")
    # Shadow the model fields
    doc_version = fields.Skip(load_only=True, dump_only=True)
    doc_created = fields.Skip(load_only=True, dump_only=True)
    doc_updated = fields.Skip(load_only=True, dump_only=True)
    # TODO: move this to marshmallow-mongoengine ?
    _cls = fields.Skip(load_only=True, dump_only=True)

    _links = fields.Method('get_links', dump_only=True)

    def get_links(self, obj):
        raise NotImplementedError()
