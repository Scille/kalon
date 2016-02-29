"""
This module centralize all the action-needs/permissions used for the
access rights policy
"""

from flask.ext.principal import Permission, ActionNeed

from kalon.tools import Tree


class Policy:
    def __init__(self, name):
        self.name = name
        self._action_need = ActionNeed(name)
        self._permission = Permission(self._action_need)

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<Policy %s>' % self.name

    def can(self):
        return self._permission.can()

    def require(self, *args, **kwargs):
        return self._permission.require(*args, **kwargs)

    @property
    def permission(self):
        return self._permission

    @property
    def action_need(self):
        return self._action_need


class PolicyTree(Tree):

    def build_leaf(self, route):
        return Policy(route)


POLICIES = PolicyTree({
    'history': 'see',
    'user': ('create', 'modify', 'see'),
    # TODO: complete me !
})
