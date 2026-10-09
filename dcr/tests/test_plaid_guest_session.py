"""Token-authorized bank setup must preserve a signed-in browser session."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class Session(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


@pytest.mark.parametrize('endpoint', ['link', 'callback'])
@pytest.mark.parametrize('fails', [False, True])
def test_guest_plaid_endpoint_restores_native_session_and_request(endpoint, fails):
    from dcr.api import achq_integration as api

    session = Session(user='test-staff', sid='existing-test-session', data={'csrf_token': 'test-csrf'})
    original = dict(session)
    form = {'cmd': 'test-endpoint', 'customer': 'DEMO DEALER'}
    fake = MagicMock()
    fake.session = session
    fake.local = SimpleNamespace(session=session, form_dict=form)

    def native_set_user(user):
        # Pinned Frappe set_user changes these values, including sid.
        session.user = user
        session.sid = user
        session.data = {}
        fake.local.form_dict = {}

    fake.set_user.side_effect = native_set_user

    def operation(*args, **kwargs):
        assert session.user == 'Administrator'
        if fails:
            raise ValueError('sandbox provider failed')
        return {'success': True}

    operation_name = 'get_plaid_link_token' if endpoint == 'link' else 'process_plaid_callback'
    with patch.object(api, 'frappe', fake), patch.object(api, '_verify_plaid_guest_token') as verify, \
            patch.object(api, operation_name, side_effect=operation):
        def invoke():
            if endpoint == 'link':
                return api.get_plaid_link_token_guest('DEMO DEALER', 'test-hmac')
            return api.process_plaid_callback_guest('test-public', 'selected', 'DEMO DEALER', 'test-hmac')
        if fails:
            with pytest.raises(ValueError, match='sandbox provider failed'):
                invoke()
        else:
            assert invoke() == {'success': True}
        verify.assert_called_once_with('DEMO DEALER', 'test-hmac')
    assert dict(session) == original
    assert fake.local.form_dict is form


def test_invalid_token_never_elevates_or_calls_provider():
    from dcr.api import achq_integration as api
    fake = MagicMock()
    with patch.object(api, 'frappe', fake), \
            patch.object(api, '_verify_plaid_guest_token', side_effect=ValueError('invalid link')), \
            patch.object(api, 'get_plaid_link_token') as provider:
        with pytest.raises(ValueError, match='invalid link'):
            api.get_plaid_link_token_guest('DEMO DEALER', 'bad-hmac')
    fake.set_user.assert_not_called()
    provider.assert_not_called()
