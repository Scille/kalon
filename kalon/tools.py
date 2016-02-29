from flask import request
from collections.abc import Iterable
from werkzeug.exceptions import HTTPException
from flask import abort as original_flask_abort
from functools import namedtuple, wraps


def check_if_match(doc=None):
    """
    Retrieve if-match header or abort 412

    :param doc: if provided, abort 412 if doc.doc_version doesn't match
    """
    if_match = request.headers.get('if-match')
    if not if_match:
        return None
    try:
        if_match = int(if_match)
    except ValueError:
        abort(412)
    if doc and doc.doc_version != if_match:
        abort(412)
    return if_match


def abort(http_status_code, *args, **kwargs):
    """
    Rest style flask abort wrapper
    """
    try:
        original_flask_abort(http_status_code)
    except HTTPException as e:
        e.data = kwargs
        if len(args):
            e.data['_errors'] = args
        raise


class LazyList(Iterable):
    """
    List generated at evaluation time (useful to pass a reference
    on a list that should be configured at runtime)
    """

    def __init__(self, list_loader):
        self.list_loader = list_loader

    def __iter__(self):
        return iter(self.list_loader())

    def __getitem__(self, i):
        return self.list_loader()[i]

    def __str__(self):
        return str(self.list_loader())

    def __bool__(self):
        return bool(self.list_loader())


def get_pagination_urlargs(default_per_page=20):
    """
    Retrieve pagination arguments provided in the url

    :return: tuple of (page, per_page)

    .. note :
        abort 400 in case of an invalid pagination value
    """
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


def get_search_urlargs(default_per_page=20):
    """
    Retrieve search and pagination arguments

    :return: tuple of (page, per_page, q, fq, sort)
    """
    page, per_page = get_pagination_urlargs(default_per_page)
    q = request.args.get('q')
    sort = request.args.getlist('sort')
    fq = request.args.getlist('fq')
    return {'page': page, 'per_page': per_page, 'q': q, 'fq': fq, 'sort': sort}


def list_to_pagination(items, already_sliced=False, page=1, per_page=None,
                       total=None, **kwargs):
    """
    Convert the given list to a :class:`Pagination` object

    :param already_sliced: If true, don't slice the given items with
        page/per_page arguments
    """
    if page < 1:
        raise ValueError('page must be > 0')
    total = total or len(items)
    per_page = per_page or total
    fields = ['items', 'page', 'per_page', 'total']
    if kwargs:
        fields += list(kwargs.keys())
    Pagination = namedtuple('Pagination', fields)
    if not already_sliced:
        items = items[(page - 1) * per_page: page * per_page]
    return Pagination(items, page, per_page, total, **kwargs)


class Tree:
    """
    Tree can be used to represent a tree of object ::

        >>> t = Tree({
        ...     'node_1': ('leaf_1_1', 'leaf_1_2'),
        ...     'node_2': ('leaf_2_1', {node_2_2': ('leaf_2_2_1', 'leaf_2_2_2')}),
        ... })
        ...
        >>> t.node_1.leaf_1_1
        'node_1.leaf_1_1'
        >>> t.node_1.node_2_2.leaf_2_2_1
        'node_1.node_2_2.leaf_2_2_1'

    Each node in the tree is a Tree object, each leaf is build
    using :method:`build_leaf`

    Tree can be used as an iterable to walk the leafs recursively

        >>> len(t)
        5
        >>> [x for x in t]
        ['node_1.leaf_1_1', 'node_1.leaf_1_2', 'node_2.leaf_2_1',
         'node_2.node_2_2.leaf_2_2_1', 'node_2.node_2_2.leaf_2_2_2']
    """
    def __init__(self, nodes, basename=''):
        self.nodes = []
        if basename:
            make = lambda *args: basename + '.' + '.'.join(args)
        else:
            make = lambda *args: '.'.join(args)
        if isinstance(nodes, dict):
            for key, value in nodes.items():
                self._set_leaf(key, self.__class__(value, make(key)))
        elif isinstance(nodes, (tuple, list, set)):
            for node in nodes:
                if isinstance(node, str):
                    self._set_leaf(node, self.build_leaf(make(node)))
                elif isinstance(node, dict):
                    for key, value in node.items():
                        self._set_leaf(key, self.__class__(value, make(key)))
                else:
                    raise ValueError('Bad node type' % node)
        elif isinstance(nodes, str):
            self._set_leaf(nodes, self.build_leaf(make(nodes)))
        else:
            raise ValueError('Bad node type' % nodes)

    def build_leaf(self, route):
        return route

    def _set_leaf(self, key, value):
        setattr(self, key, value)
        self.nodes.append(value)

    def __iter__(self):
        for node in self.nodes:
            if isinstance(node, Tree):
                for sub_node in node:
                    yield sub_node
            else:
                yield node

    def __len__(self):
        return len([e for e in self])

    def __getitem__(self, i):
        return [e for e in self][i]

    def __str__(self):
        return str([e for e in self])


class LazzyManager:
    """
    Allow to dynimacally register function that will be called at
    lazily when they will be required
    """

    def __init__(self, app):
        self.app = app
        self.app.run = self.required(self.app.run)
        self.load_list = []
        self._loaded = False

    def register(self, fn):
        self.load_list.append(fn)
        return fn

    def load(self):
        if not self._loaded:
            self._loaded = True
            for fn in self.load_list:
                fn(self.app)

    def required(self, fn):
        """Decorator to activate the load before calling the given function"""
        @wraps(fn)
        def wrapper(*args, **kwargs):
            self.load()
            return fn(*args, **kwargs)
        return wrapper
