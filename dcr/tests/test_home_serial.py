"""Serial numbers are descriptive data, not a uniqueness key."""
from unittest.mock import MagicMock, patch
import pytest

from dcr.api import dealer_portal as portal
from dcr.dcr.doctype.home_build_request import home_build_request as hbr


@pytest.mark.parametrize("value", ["TBD", "t.b.d", "tbd", "SERIAL-123", "", None])
@patch("dcr.api.hbr_stage.apply_hbr_stage_defaults")
@patch.object(hbr, "frappe")
def test_native_requests_allow_repeated_serial_values(frappe, stages, value):
    frappe.db.get_value.return_value = "EXISTING-HBR"
    frappe.throw.side_effect = ValueError
    for name in ["HBR-A", "HBR-B"]:
        request = hbr.HomeBuildRequest()
        request.name = name
        request.factory = request.customer = None
        request.home_serial_no = value
        request.ensure_required_checklist = MagicMock()
        request.validate()
        assert request.home_serial_no == value
    frappe.db.get_value.assert_not_called()


@pytest.mark.parametrize("value", ["TBD", "t.b.d", "tbd", "SERIAL-123"])
@patch.object(portal, "_serialize_hbr", return_value={"name": "HBR-A"})
@patch.object(portal, "_has_field", return_value=False)
@patch.object(portal, "_require_active_factory")
@patch.object(portal, "_get_owned_hbr")
@patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
@patch.object(portal, "frappe")
def test_portal_create_and_edit_allow_repeated_serial_values(frappe, identity, owned, factory, has_field, serialize, value):
    frappe.db.exists.return_value = True
    frappe.throw.side_effect = ValueError
    for name in [None, "HBR-A"]:
        request = MagicMock()
        request.get.side_effect = {"docstatus": 0, "custom_portal_status": "Draft", "factory": "FACTORY-A"}.get
        owned.return_value = request
        frappe.new_doc.return_value = request
        portal.save_hbr_draft({"factory": "FACTORY-A", "home_serial_no": value}, name=name)
        request.set.assert_any_call("home_serial_no", value)
    assert not any(call.args[0] == "Home Build Request" and "home_serial_no" in call.args[1]
        for call in frappe.db.exists.call_args_list)
