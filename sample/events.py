"""
Centralize the events
"""

from flask.ext.restful import Resource

from kalon.tools import Tree
from kalon.auth import current_user, login_required

from sample.permissions import POLICIES as p


class Event:

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<Event %s>' % self.name

    def __eq__(self, other):
        if isinstance(other, Event):
            return self.name == other.name
        else:
            return self.name == other

    def send(self, origin=None, **kwargs):
        origin = str(origin or current_user.pk)
        # return broker.send(self.name, origin=origin, context=kwargs)


class EventTree(Tree):

    def build_leaf(self, route):
        return Event(route)


EVENTS = EventTree({
    'user': ('created', 'modified'),
    # TODO: complete me !
})


def init_events(app, **kwargs):
    app.json_encoder.register(Event, lambda x: x.name)
