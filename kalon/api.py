from flask.ext.restful import Api


class CoreApi(Api):
    """
    Flask-restful Api with no auto lowercasing of the endpoints
    """
    def __init__(self):
        super().__init__(catch_all_404s=True)

    def add_resource(self, resource, *args, endpoint=None, **kwargs):
        # Avoid lowercasing of the endpoint
        endpoint = endpoint or resource.__name__
        return super().add_resource(resource, *args, endpoint=endpoint, **kwargs)
