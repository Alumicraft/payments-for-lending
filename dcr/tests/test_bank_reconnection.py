"""A verified reconnect must not collide with an earlier masked account name."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from dcr.api import achq_integration as api


@pytest.mark.parametrize('customer,bank_name', [('DEMO DEALER', 'First Platypus Bank'), ('D' * 100, 'B' * 60)])
def test_reconnecting_the_same_mask_keeps_both_verified_connections(customer, bank_name):
    stored = {}
    class BankAccount(SimpleNamespace):
        def insert(self):
            # ERPNext af63cde BankAccount.autoname uses this exact name.
            self.name = self.account_name + ' - ' + self.bank
            assert len(self.name) <= 140
            if self.name in stored:
                raise ValueError('Duplicate Bank Account name')
            stored[self.name] = self

    with patch.object(api, 'frappe') as f, patch.object(api, '_get_or_create_bank', return_value=bank_name):
        f.new_doc.side_effect = lambda doctype: BankAccount()
        f.generate_hash.side_effect = ['first-token1', 'second-token']
        kwargs = dict(customer=customer, bank_name=bank_name, account_type='Checking',
            token_source='Plaid', verify_status='POS', account_last4='0000', routing_last4='1533',
            is_default=True, settings=SimpleNamespace(default_sec_code='WEB'))
        first = api._create_bank_account(token='first-test-token', **kwargs)
        second = api._create_bank_account(token='second-test-token', **kwargs)
        assert first.name != second.name
        assert len(stored) == 2
        assert first.custom_achq_token == 'first-test-token'
        assert second.custom_achq_token == 'second-test-token'
        assert first.party == second.party == customer
        assert first.custom_account_last_four == second.custom_account_last_four == '0000'
        assert first.custom_routing_last_4 == second.custom_routing_last_4 == '1533'
        assert f.db.get_value.call_args_list[0].args == ('Customer', customer, 'name')
        assert f.db.get_value.call_args_list[0].kwargs['for_update'] is True
