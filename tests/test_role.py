import pytest

from tests import common
from tests.test_auth import user

from sample.permissions import POLICIES as p


class TestRole(common.BaseTest):

    @classmethod
    def setup_class(cls):
        # Monkey patch roles
        import sample.roles
        from sample.model.user import User
        cls.origin_roles = sample.roles.ROLES
        cls.origin_roles_choices = User._fields['role'].choices
        roles = {
            'role-1': [],  # Role with no permissions
            'role_on_user': p.user  # Role with a PolicyTree
        }
        sample.roles.ROLES = roles
        User._fields['role'].choices = list(roles.keys())
        super().setup_class()

    @classmethod
    def teardown_class(cls):
        # Undo the monkey patching
        import sample.roles
        from sample.model.user import User
        sample.roles.ROLES = cls.origin_roles
        User._fields['role'].choices = cls.origin_roles_choices

    def test_change_self_role(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        r = user_req.patch('/me', data={'role': 'role-1'})
        assert r.status_code == 400, r

    @pytest.mark.xfail
    def test_add_role(self, user):
        user_req = self.make_auth_request(user, user._raw_password)
        # Can't change role without proper permission
        route = '/users/%s' % user.id
        r = user_req.patch(route, data={'role': 'role-1'})
        assert r.status_code == 403, r
        # Add right permission and retry
        user.permissions.append(p.user.modify.name)
        user.save()
        r = user_req.patch(route, data={'role': 'role-1'})
        assert r.status_code == 200, r
        assert r.data.get('role', '<not_set>') == 'role-1'
        # Try to remove the role as well
        r = user_req.patch(route, data={'role': None})
        assert r.status_code == 200, r
        assert 'role' not in r.data

    def test_add_bad_role(self, user):
        user.permissions.append(p.user.modify.name)
        user.save()
        user_req = self.make_auth_request(user, user._raw_password)
        for bad_role in ['not_a_role', '', 42]:
            r = user_req.patch('/users/%s' % user.id, data={'role': bad_role})
            assert r.status_code == 400, r

    def test_role_give_permissions(self, user):
        user.role = "role_on_user"
        user.save()
        # Now the user have the permission through it role
        user_req = self.make_auth_request(user, user._raw_password)
        route = '/users/%s' % user.id
        r = user_req.patch(route, data={'firstname': 'new-name'})
        assert r.status_code == 200, r
