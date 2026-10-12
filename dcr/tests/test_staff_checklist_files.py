"""Native Desk child attachments remain private and readable by their dealer."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from dcr.api import dealer_portal as portal


@pytest.mark.parametrize('attachment_field', ['attachment', 'doc_checklist'])
def test_checklist_readback_recognizes_staff_and_legacy_portal_files(attachment_field):
    hbr = {'name': 'HBR-A', 'doc_checklist': [
        {'document_type': 'Insurance', 'attachment': '/private/files/demo.txt'}]}
    with patch.object(portal, 'frappe') as frappe:
        frappe.get_all.return_value = [{'file_url': '/private/files/demo.txt',
            'attached_to_field': attachment_field, 'file_name': 'demo.txt'}]
        result = portal._hbr_document_items(hbr)[0]
    assert result['can_download'] is True
    assert result['file_name'] == 'demo.txt'
    assert 'file_url' not in result


@pytest.mark.parametrize('attachment_field', ['attachment', 'doc_checklist'])
def test_download_uses_owned_checklist_url_and_keeps_bytes(attachment_field):
    data = b'DEMO ONLY insurance upload mechanics, not coverage.\n'
    file = SimpleNamespace(attached_to_doctype='Home Build Request', attached_to_name='HBR-A',
        attached_to_field=attachment_field, file_url='/private/files/demo.txt',
        is_private=1, file_name='demo.txt', get_content=Mock(return_value=data))
    def lookup(doctype, filters, field):
        constraint = filters.get('attached_to_field')
        allowed = constraint[1] if isinstance(constraint, list) else [constraint]
        return 'FILE-A' if attachment_field in allowed else None
    with patch.object(portal, 'frappe') as frappe, \
         patch.object(portal, 'get_current_dealer_customer', return_value={'name': 'DEALER-A'}), \
         patch.object(portal, '_get_owned_hbr', return_value={'name': 'HBR-A', 'doc_checklist': [
             {'document_type': 'Insurance', 'attachment': '/private/files/demo.txt'}]}):
        frappe.db.get_value.side_effect = lookup
        frappe.get_doc.return_value = file
        frappe.local.response = {}
        frappe.throw.side_effect = ValueError
        portal.download_document('hbr', 'HBR-A', 'Insurance')
        assert frappe.local.response['filecontent'] == data
        filters = frappe.db.get_value.call_args.args[1]
        assert filters['attached_to_name'] == 'HBR-A'
        assert filters['is_private'] == 1
        assert filters['file_url'] == '/private/files/demo.txt'
    file.get_content.assert_called_once_with(encodings=[])


@pytest.mark.parametrize('field,value', [
    ('attached_to_doctype', 'Customer'), ('attached_to_name', 'OTHER-HBR'),
    ('attached_to_field', 'notes'), ('attached_to_field', None),
    ('is_private', 0), ('file_url', '/private/files/other.txt'),
])
def test_native_attachment_format_does_not_admit_foreign_public_or_unrelated_files(field, value):
    file = SimpleNamespace(attached_to_doctype='Home Build Request', attached_to_name='HBR-A',
        attached_to_field='attachment', file_url='/private/files/demo.txt',
        is_private=1, file_name='demo.txt', get_content=Mock())
    setattr(file, field, value)
    with patch.object(portal, 'frappe') as frappe, \
         patch.object(portal, 'get_current_dealer_customer', return_value={'name': 'DEALER-A'}), \
         patch.object(portal, '_get_owned_hbr', return_value={'name': 'HBR-A', 'doc_checklist': [
             {'document_type': 'Insurance', 'attachment': '/private/files/demo.txt'}]}):
        frappe.db.get_value.return_value = 'FILE-A'
        frappe.get_doc.return_value = file
        frappe.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            portal.download_document('hbr', 'HBR-A', 'Insurance')
    file.get_content.assert_not_called()


def test_foreign_request_is_rejected_before_any_file_lookup():
    with patch.object(portal, 'frappe') as frappe, \
         patch.object(portal, 'get_current_dealer_customer', return_value={'name': 'DEALER-A'}):
        frappe.db.exists.return_value = False
        frappe.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            portal.download_document('hbr', 'OTHER-HBR', 'Insurance')
        frappe.db.exists.assert_called_once_with('Home Build Request', {'name': 'OTHER-HBR', 'customer': 'DEALER-A'})
        frappe.db.get_value.assert_not_called()
        frappe.get_doc.assert_not_called()


def test_aliases_sharing_storage_do_not_invent_an_upload_identity():
    with patch.object(portal, 'frappe') as frappe:
        frappe.get_all.return_value = [
            {'attached_to_field': field, 'file_url': '/private/files/demo.txt', 'file_name': field+'.txt'}
            for field in ('attachment', 'doc_checklist')]
        result = portal._hbr_document_items({'name': 'HBR-A', 'doc_checklist': [
            {'document_type': 'Insurance', 'attachment': '/private/files/demo.txt'}]})[0]
    assert result['can_download'] is True
    assert 'file_name' not in result


def test_new_portal_upload_matches_the_native_child_attachment_field():
    row = SimpleNamespace(document_type='Insurance', attachment=None)
    hbr = Mock()
    hbr.get.side_effect = lambda field, default=None: [row] if field == 'doc_checklist' else default
    with patch.object(portal, 'get_current_dealer_customer', return_value={'name': 'DEALER-A'}), \
         patch.object(portal, '_get_owned_hbr', return_value=hbr), \
         patch.object(portal, '_require_uploadable_hbr'), \
         patch.object(portal, '_request_file'), \
         patch.object(portal, '_validate_upload', return_value=('demo.txt', b'DEMO ONLY')), \
         patch.object(portal, '_insert_private_file', return_value=SimpleNamespace(file_url='/private/files/demo.txt')) as insert:
        portal.upload_document('hbr', 'HBR-A', 'Insurance')
    insert.assert_called_once_with('demo.txt', b'DEMO ONLY', 'Home Build Request', 'HBR-A', 'attachment')
    assert row.attachment == '/private/files/demo.txt'
    hbr.save.assert_called_once_with(ignore_permissions=True)
