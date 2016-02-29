from functools import wraps
from flask import request
from flask.ext.restful import unpack

from core.tools import abort


class ConcurrencyError(Exception):
    pass


def concurrency_handler(func, etag_src_field='_version'):
    """
    Decorator to handle ConcurrencyError (retry or abort depending of the
    presence of the If-Match header) and ETAG
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if_match = request.headers.get("if-match")
        while True:
            try:
                ret = func(*args, **kwargs)
            except ConcurrencyError:
                # Concurrency exception happened, if if_match was
                # specified (i.e. the user requested a specific version
                # to work against) we have to fail. Otherwise we replay
                # the request until success.
                if if_match:
                    abort(412)
                else:
                    continue
            break
        # Automatically set ETAG for payload with _version field
        data, status_code, headers = unpack(ret)
        etag = data.get(etag_src_field)
        if etag is not None:
            headers['Etag'] = str(etag)
        return data, status_code, headers
    return wrapper
