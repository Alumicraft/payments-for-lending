"""Opening an existing packet never sends/reissues it or leaks provider errors."""
from unittest.mock import patch

import pytest
from requests import Response
from requests.exceptions import HTTPError, Timeout

from dcr.api import dealer_portal as portal


@pytest.fixture
def owned_packet():
    customer = {"name": "DEALER-A", "customer_name": "Demo Dealer"}
    packet = {"name": "SIG-A", "customer": "DEALER-A", "status": "Sent",
              "envelope_id": "existing-envelope", "recipient_email": "demo@example.test",
              "recipient_name": "Demo Dealer", "document_type": "Flooring Packet"}
    with patch.object(portal, "get_current_dealer_customer", return_value=customer), \
         patch.object(portal, "frappe") as frappe, \
         patch("dcr.api.docusign.DocuSignClient") as client:
        frappe.db.exists.return_value = True
        frappe.get_doc.return_value = packet
        frappe.throw.side_effect = lambda message, *args, **kwargs: (_ for _ in ()).throw(ValueError(message))
        frappe.utils.get_url.side_effect = lambda path: "https://demo.example.test" + path
        yield frappe, client.return_value


def test_missing_envelope_returns_safe_terminal_state_without_record_writes(owned_packet):
    frappe, client = owned_packet
    response = Response()
    response.status_code = 404
    client.get_signing_url.side_effect = HTTPError("private provider detail", response=response)
    result = portal.start_signature("SIG-A")
    assert result["url"] is None and result["unavailable"] is True
    assert "Flooring Packet" in result["message"] and "envelope is unavailable" in result["message"]
    assert "private provider detail" not in result["message"]
    frappe.db.set_value.assert_not_called()
    client.create_envelope.assert_not_called()


def test_transient_provider_error_is_safe_and_not_reported_as_missing(owned_packet):
    _, client = owned_packet
    response = Response()
    response.status_code = 503
    client.get_signing_url.side_effect = HTTPError("private provider detail", response=response)
    with pytest.raises(ValueError, match="Please try again later") as raised:
        portal.start_signature("SIG-A")
    assert "private provider detail" not in str(raised.value)


def test_network_timeout_has_safe_retry_message(owned_packet):
    _, client = owned_packet
    client.get_signing_url.side_effect = Timeout("private connection detail")
    with pytest.raises(ValueError, match="could not be reached"):
        portal.start_signature("SIG-A")


def test_success_opens_existing_envelope_without_sending(owned_packet):
    _, client = owned_packet
    client.get_signing_url.return_value = "https://sign.example.test/existing"
    assert portal.start_signature("SIG-A") == {"url": "https://sign.example.test/existing"}
    client.create_envelope.assert_not_called()


def test_foreign_packet_is_denied_before_provider(owned_packet):
    frappe, client = owned_packet
    frappe.db.exists.return_value = False
    with pytest.raises(ValueError, match="not available"):
        portal.start_signature("OTHER")
    client.get_signing_url.assert_not_called()
