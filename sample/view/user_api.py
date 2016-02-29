from flask import request, url_for

from kalon.tools import abort, get_search_urlargs, check_if_match
from kalon.auth import current_user, is_fresh_auth
from kalon import CoreResource, view_util

from sample.permissions import POLICIES as p
from sample.model.user import User
from sample.events import EVENTS as e


User.set_link_builder_from_api('UserAPI')


class UserSchema(view_util.BaseModelSchema):
    _links = view_util.fields.Method('get_links')

    def __init__(self, *args, full_access=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not full_access:
            for field in ('role', 'permissions', 'password'):
                self.fields[field].dump_only = True

    def get_links(self, obj):
        route = url_for("UserAPI", item_id=obj.pk)
        links = {'self': route,
                 'parent': url_for("UserListAPI")}
        if p.user.modify.can():
            links['update'] = route
        if p.history.see.can():
            links['history'] = url_for("UserHistoryListAPI",
                                       origin_id=obj.pk)
        return links

    class Meta:
        model = User
        model_fields_kwargs = {'password': {'load_only': True}}


class UserAPI(CoreResource):

    def get(self, item_id=None):
        if not item_id:
            # Use current user by default
            user = current_user
            url = url_for('UserAPI')
            links = {'self': url, 'update': url, 'root': url_for('RootAPI')}
        else:
            with p.user.see.require(http_exception=403):
                user = User.objects.get_or_404(id=item_id)
                links = None  # Use default links
        data = UserSchema().dump(user).data
        if links:
            data['_links'] = links
        return data

    def patch(self, item_id=None):
        if not item_id:
            schema = UserSchema()
            user = current_user
            links = {'self': '/me', 'update': '/me'}
        else:
            if not is_fresh_auth():
                abort(401, 'Fresh token required')
            with p.user.modify.require(http_exception=403):
                schema = UserSchema(full_access=True)
                user = User.objects.get_or_404(id=item_id)
                links = None
        if_match = check_if_match(user)
        payload = request.get_json()
        user, errors = schema.update(user, payload)
        if errors:
            abort(400, **errors)
        if 'password' in user._get_changed_fields():
            user.controller.set_password(user.password)
        user.controller.save_or_abort(if_match=if_match)
        data = schema.dump(user).data
        e.user.modified.send(user=data, payload=payload)
        if links:
            data['_links'] = links
        return data


class UserListAPI(CoreResource):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._serializer = view_util.PaginationSerializer(
            UserSchema(), url_for('UserListAPI'))

    @p.user.see.require(http_exception=403)
    def get(self):
        urlargs = get_search_urlargs()
        if not urlargs['q'] and not urlargs['fq'] and not urlargs['sort']:
            # No need to use the searcher module
            users = User.objects().paginate(
                page=urlargs['page'], per_page=urlargs['per_page'])
        else:
            users = User.search_or_abort(**urlargs)
        links = {'root': url_for('RootAPI')}
        if p.user.create.can():
            links['create'] = url_for('UserListAPI')
        return self._serializer.dump(users, links=links).data

    @p.user.create.require(http_exception=403)
    def post(self):
        if not is_fresh_auth():
            abort(401, 'Token frais requis')
        payload = request.get_json()
        schema = UserSchema(full_access=True)
        user, errors = schema.load(payload)
        if errors:
            abort(400, **errors)
        user.controller.set_password_and_email()
        user.controller.save_or_abort()
        e.user.created.send(user=schema.dump(user).data)
        return schema.dump(user).data, 201
