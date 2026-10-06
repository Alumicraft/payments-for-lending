"""File identity readbacks never broaden the parent/private attachment boundary."""
from datetime import datetime
from unittest.mock import patch
import pytest
from dcr.api import dealer_portal as portal


def test_hbr_metadata_is_queried_once_with_all_private_attachment_constraints():
    hbr = {"name": "HBR-A", "doc_checklist": [
        {"document_type": "Spec Info Sheet", "attachment": "/private/files/a.pdf"},
        {"document_type": "Factory Quote", "attachment": "/private/files/b.pdf"},
        {"document_type": "Plot Plan", "waived": 1},
    ]}
    with patch.object(portal, "frappe") as frappe:
        frappe.get_all.return_value = [{"file_url": "/private/files/a.pdf", "attached_to_field": "doc_checklist",
            "file_name": "../demo spec.pdf", "creation": datetime(2026, 10, 6, 5, 30)}]
        items = portal._hbr_document_items(hbr)
        assert items[0]["file_name"] == "demo-spec.pdf"
        assert items[0]["uploaded_on"] == "2026-10-06T05:30:00"
        assert "file_url" not in items[0] and "attachment" not in items[0]
        assert "file_name" not in items[1], "unmatched file metadata stays unavailable"
        assert items[2] == {"document_type": "Plot Plan", "uploaded": False, "complete": True}
        frappe.get_all.assert_called_once()
        filters = frappe.get_all.call_args.kwargs["filters"]
        assert filters["attached_to_doctype"] == "Home Build Request"
        assert filters["attached_to_name"] == "HBR-A"
        assert filters["attached_to_field"] == ["in", ["doc_checklist"]]
        assert filters["is_private"] == 1
        assert set(filters["file_url"][1]) == {"/private/files/a.pdf", "/private/files/b.pdf"}


def test_customer_metadata_must_match_the_specific_onboarding_field():
    with patch.object(portal, "frappe") as frappe, patch.object(portal, "_has_field", return_value=True):
        frappe.db.get_value.return_value = {"w9_copy": "/private/files/shared.pdf"}
        frappe.get_all.return_value = [{"file_url": "/private/files/shared.pdf", "attached_to_field": "dealer_license_copy",
            "file_name": "foreign-field.pdf", "creation": "2026-10-06"}]
        result = portal._get_onboarding_documents({"name": "DEALER-A"})
        w9 = next(item for item in result if item["fieldname"] == "w9_copy")
        assert w9["uploaded"]
        assert "file_name" not in w9
        assert frappe.get_all.call_args.kwargs["filters"]["attached_to_name"] == "DEALER-A"


def test_no_attachment_does_not_read_files():
    with patch.object(portal, "frappe") as frappe:
        assert portal._attached_file_metadata("Home Build Request", "HBR-A", ["doc_checklist"], [None, ""]) == {}
        frappe.get_all.assert_not_called()


def test_shared_storage_url_with_multiple_upload_rows_does_not_invent_identity():
    with patch.object(portal, "frappe") as frappe:
        frappe.get_all.return_value = [
            {"file_url": "/private/files/a.pdf", "attached_to_field": "doc_checklist", "file_name": name}
            for name in ["original.pdf", "replacement.pdf"]
        ]
        assert portal._attached_file_metadata("Home Build Request", "HBR-A", ["doc_checklist"], ["/private/files/a.pdf"]) == {}


def test_support_lookup_failure_does_not_break_portal():
    with patch.object(portal, "frappe") as frappe:
        frappe.db.get_single_value.side_effect = RuntimeError("unavailable settings")
        assert portal._support_url() == ""


@pytest.mark.parametrize("disabled,expected", [(0, "/contact"), (1, "")])
def test_native_contact_route_respects_existing_site_disabled_setting(disabled, expected):
    with patch.object(portal, "frappe") as frappe:
        frappe.db.get_single_value.return_value = disabled
        assert portal._support_url() == expected
        frappe.db.get_single_value.assert_called_once_with("Contact Us Settings", "is_disabled")
