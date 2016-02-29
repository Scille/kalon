from flask import url_for
from collections import namedtuple

from core.tools import get_pagination_urlargs, abort
from core import CoreResource, view_util
from xin.permissions import POLICIES as p


HistoryAPI = namedtuple('HistoryAPI', ('item', 'endpoint', 'list',
                                       'endpoint_list', 'schema'))


def history_api_factory(origin_cls):
    if 'history_cls' not in origin_cls._meta:
        raise RuntimeError('%s must have a `history_cls` meta field' % origin_cls)
    history_cls = origin_cls._bootstrap_history_cls()

    def history_link_builder(obj):
        return {'self': url_for('HistoryAPI', origin_id=obj.origin.id,
                                item_id=obj.id)}

    endpoint = "%sHistoryAPI" % origin_cls.__name__
    endpoint_list = "%sHistoryListAPI" % origin_cls.__name__
    endpoint_origin = "%sAPI" % origin_cls.__name__

    class HistorySchema(view_util.UnknownCheckedSchema):
        """Read-only schema"""

        def get_links(self, obj):
            return {
                'self': url_for(endpoint, origin_id=obj.origin.id,
                                item_id=obj.id),
                'parent': url_for(endpoint_list, origin_id=obj.origin.id),
                'origin': url_for(endpoint_origin, item_id=obj.origin.id)
            }

        class Meta:
            model = history_cls

    class HistoryItemAPI(CoreResource):

        @p.history.see.require(http_exception=403)
        def get(self, origin_id, item_id):
            origin = origin_cls()
            item = origin._meta['history_cls'].objects.get_or_404(id=item_id)
            if str(item.origin.id) != origin_id:
                abort(404)
            return HistorySchema().dump(item).data

    class HistoryListAPI(CoreResource):

        @p.history.see.require(http_exception=403)
        def get(self, origin_id):
            page, per_page = get_pagination_urlargs()
            origin = origin_cls()
            items = origin._meta['history_cls'].objects(
                origin=origin_id).paginate(page=page, per_page=per_page)
            links = {'origin': url_for(endpoint_origin, item_id=origin_id)}
            route = url_for(endpoint_list, origin_id=origin_id)
            return view_util.PaginationSerializer(HistorySchema(), route).dump(
                items, links=links).data

    return HistoryAPI(HistoryItemAPI, endpoint, HistoryListAPI,
                      endpoint_list, HistorySchema)


def register_history(api, origin_cls, name=None):
    name = name or origin_cls.__name__.lower()
    history = history_api_factory(origin_cls)
    api.add_resource(history.list, '/%s/<string:origin_id>/history' % name,
                     endpoint=history.endpoint_list)
    api.add_resource(history.item,
        '/%s/<string:origin_id>/history/<objectid:item_id>' % name,
        endpoint=history.endpoint)
