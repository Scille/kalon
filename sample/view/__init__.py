from kalon import CoreResource, CoreApi
from kalon.view_util import history_api

from sample.view import user_api
from sample.model import user


api = CoreApi()


# user
api.add_resource(user_api.UserAPI,
                 '/users/<objectid:item_id>', '/me')
api.add_resource(user_api.UserListAPI, '/users')

# history
history_api.register_history(api, user.User, 'users')


class RootAPI(CoreResource):

    """Root endpoint for api discovering"""

    def get(self):
        return {
            '_links': {
                'users': '/users',
            }
        }
api.add_resource(RootAPI, '/')


__all__ = ('api',)
