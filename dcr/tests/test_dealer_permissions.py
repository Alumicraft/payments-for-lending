"""Legacy Dealer permissions must not bypass the portal ownership checks."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dcr.setup import ensure_dealer_portal_permissions


def test_migration_disables_all_legacy_dealer_rights_and_clears_cached_meta():
    permissions = MagicMock()
    permissions.get_rights.return_value = ["read", "write", "create", "select", "email", "print", "share"]
    with patch.dict(sys.modules, {"frappe.permissions": permissions}), patch("dcr.setup.frappe") as f:
        f.get_all.side_effect = [
            [SimpleNamespace(name="CUSTOMER-DEALER")],
            [],
            [SimpleNamespace(name="HBR-DEALER")],
        ]
        ensure_dealer_portal_permissions()
        assert [call.kwargs["filters"] for call in f.get_all.call_args_list] == [
            {"parent": dt, "role": "Dealer"}
            for dt in ("Customer", "Supplier", "Home Build Request")
        ]
        assert [call.args[1] for call in f.db.set_value.call_args_list] == ["CUSTOMER-DEALER", "HBR-DEALER"]
        assert all(not any(call.args[2].values()) for call in f.db.set_value.call_args_list)
        assert [call.kwargs["doctype"] for call in f.clear_cache.call_args_list] == ["Customer", "Home Build Request"]


def test_migration_without_legacy_rows_preserves_standard_permissions():
    permissions = MagicMock()
    with patch.dict(sys.modules, {"frappe.permissions": permissions}), patch("dcr.setup.frappe") as f:
        f.get_all.return_value = []
        ensure_dealer_portal_permissions()
        f.db.set_value.assert_not_called()
        permissions.get_rights.assert_not_called()
