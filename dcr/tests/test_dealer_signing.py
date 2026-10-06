"""Portal signing links preserve the reviewed recipient and truthful returns."""
from unittest.mock import patch

from dcr.api import dealer_portal as portal


@patch("dcr.api.docusign.DocuSignClient")
@patch.object(portal, "get_current_dealer_customer", return_value={
    "name": "DEALER-A", "email_id": "changed@example.test", "customer_name": "Changed name"})
@patch.object(portal, "frappe")
def test_portal_signing_uses_original_envelope_recipient_after_customer_edit(frappe, identity, client):
    frappe.db.exists.return_value = True
    frappe.utils.get_url.side_effect = lambda value: value
    frappe.get_doc.return_value = {"status": "Sent", "envelope_id": "ENVELOPE-A",
        "recipient_email": "reviewed@example.test", "recipient_name": "Reviewed name",
        "document_type": "Flooring Packet"}
    portal.start_signature("SIG-A")
    args = client.return_value.get_signing_url.call_args.kwargs
    assert args["email"] == "reviewed@example.test"
    assert args["name"] == "Reviewed name"
    assert "signature_request=SIG-A" in args["return_url"]


@patch("dcr.api.docusign._handle_envelope_completed")
@patch("dcr.api.docusign.DocuSignClient")
@patch.object(portal, "get_current_dealer_customer", return_value={"name": "DEALER-A"})
@patch.object(portal, "frappe")
def test_cancelled_or_pending_signing_return_does_not_claim_completion(frappe, identity, client, complete):
    frappe.db.exists.return_value = True
    frappe.get_doc.return_value = {"status": "Sent", "envelope_id": "ENVELOPE-A"}
    frappe.utils.get_url.side_effect = lambda value: value
    client.return_value.get_envelope_status.return_value = "sent"
    portal.signature_complete("SIG-A")
    assert frappe.local.response.__setitem__.call_args_list[-1].args == ("location", "/portal?signature=pending")
    complete.assert_not_called()
    frappe.db.commit.assert_not_called()
