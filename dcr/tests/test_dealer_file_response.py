"""Binary and ownership regressions from the hosted dealer PDF rehearsal."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "filename,content_type,disposition",
    [
        ("spec.pdf", "application/pdf", "inline"),
        ("plot.png", "image/png", "inline"),
        ("quote.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "attachment"),
    ],
)
def test_owned_binary_file_preserves_bytes(filename, content_type, disposition):
    from dcr.api.dealer_portal import download_document

    original = b"%PDF-1.4\n%\x93\x8c\x8b\x9e\n\x00binary"

    def native_get_content(encodings=None):
        # Reproduce v16's default decode: a text response changes binary bytes.
        return original if encodings == [] else original.decode("windows-1252")

    file_doc = SimpleNamespace(
        attached_to_doctype="Home Build Request", attached_to_name="DEMO-HBR",
        attached_to_field="doc_checklist", is_private=1, file_name=filename,
        get_content=native_get_content,
    )
    with patch("dcr.api.dealer_portal.frappe") as frappe, \
         patch("dcr.api.dealer_portal.get_current_dealer_customer", return_value={"name": "DEMO"}), \
         patch("dcr.api.dealer_portal._document_url", return_value=("Home Build Request", "DEMO-HBR", "doc_checklist", "/private/files/spec.pdf")):
        frappe.get_doc.return_value = file_doc
        frappe.local.response = {}
        download_document("hbr", "DEMO-HBR", "Spec Info Sheet")
        assert frappe.get_doc.call_args.args == ("File", {
            "file_url": "/private/files/spec.pdf", "attached_to_doctype": "Home Build Request",
            "attached_to_name": "DEMO-HBR", "attached_to_field": "doc_checklist", "is_private": 1,
        }), "shared storage URLs must resolve only within this owned attachment"
        assert frappe.local.response["filecontent"] == original
        assert frappe.local.response["content_type"] == content_type
        assert frappe.local.response["display_content_as"] == disposition


@pytest.mark.parametrize("field,value", [("attached_to_name", "OTHER-HBR"), ("is_private", 0)])
def test_mismatched_or_public_file_refused_before_read(field, value):
    from dcr.api.dealer_portal import download_document
    from unittest.mock import Mock

    file_doc = SimpleNamespace(
        attached_to_doctype="Home Build Request", attached_to_name="DEMO-HBR",
        attached_to_field="doc_checklist", is_private=1, get_content=Mock(),
    )
    setattr(file_doc, field, value)
    with patch("dcr.api.dealer_portal.frappe") as frappe, \
         patch("dcr.api.dealer_portal.get_current_dealer_customer", return_value={"name": "DEMO"}), \
         patch("dcr.api.dealer_portal._document_url", return_value=("Home Build Request", "DEMO-HBR", "doc_checklist", "/private/files/spec.pdf")):
        frappe.get_doc.return_value = file_doc
        frappe.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            download_document("hbr", "DEMO-HBR", "Spec Info Sheet")
        file_doc.get_content.assert_not_called()


def test_recorded_attachment_without_scoped_file_has_safe_unavailable_message():
    from dcr.api.dealer_portal import download_document
    with patch("dcr.api.dealer_portal.frappe") as frappe, \
         patch("dcr.api.dealer_portal.get_current_dealer_customer", return_value={"name": "DEMO"}), \
         patch("dcr.api.dealer_portal._document_url", return_value=("Customer", "DEMO", "w9_copy", "/private/files/recorded.pdf")):
        frappe.DoesNotExistError = LookupError
        frappe.get_doc.side_effect = LookupError
        frappe.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            download_document("customer", "DEMO", "w9_copy")
        assert frappe.throw.call_args.args[0] == "That document's file is unavailable. Contact DCR for help."
