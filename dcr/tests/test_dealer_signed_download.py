"""Signed-copy downloads must remain scoped to the authenticated dealer."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest


def signature(**changes):
    return dict(name='SIG-1', customer='DEALER-1', status='Signed',
                document_type='Flooring Packet', signed_attachment='/private/files/signed.pdf', **changes)


def test_owned_signed_copy_downloads_native_attachment_without_field_binding():
    from dcr.api.dealer_portal import download_document
    values = signature()
    pdf = b'%PDF-1.4\n\x00\xffsigned'
    file_doc = SimpleNamespace(attached_to_doctype='Signature Request', attached_to_name='SIG-1',
                              attached_to_field=None, file_url=values['signed_attachment'], is_private=1,
                              file_name='signed.pdf', get_content=Mock(return_value=pdf))
    with patch('dcr.api.dealer_portal.frappe') as frappe, \
         patch('dcr.api.dealer_portal.get_current_dealer_customer', return_value={'name':'DEALER-1'}):
        def get_value(doctype, filters, fields, **kwargs):
            return values if doctype == 'Signature Request' else 'FILE-1'
        frappe.db.get_value.side_effect = get_value
        frappe.get_doc.return_value = file_doc
        frappe.local.response = {}
        download_document('signature', 'SIG-1', 'Flooring Packet')
        assert frappe.local.response['filecontent'] == pdf
        file_doc.get_content.assert_called_once_with(encodings=[])
        file_filter = frappe.db.get_value.call_args.args[1]
        assert file_filter['attached_to_doctype'] == 'Signature Request'
        assert file_filter['attached_to_name'] == 'SIG-1'
        assert 'attached_to_field' not in file_filter


@pytest.mark.parametrize('change', [dict(customer='OTHER'), dict(status='Sent'),
                                    dict(signed_attachment=''), dict(document_type='MIFA')])
def test_invalid_signature_refused_before_file_lookup(change):
    from dcr.api.dealer_portal import download_document
    values = signature(); values.update(change)
    with patch('dcr.api.dealer_portal.frappe') as frappe, \
         patch('dcr.api.dealer_portal.get_current_dealer_customer', return_value={'name':'DEALER-1'}):
        frappe.db.get_value.return_value = values
        frappe.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            download_document('signature', 'SIG-1', 'Flooring Packet')
        frappe.get_doc.assert_not_called()
        assert all(call.args[0] != 'File' for call in frappe.db.get_value.call_args_list)


@pytest.mark.parametrize('change', [dict(attached_to_name='OTHER'), dict(attached_to_doctype='Customer'),
                                    dict(is_private=0), dict(file_url='/private/files/other.pdf')])
def test_signature_file_mismatch_refused_before_bytes(change):
    from dcr.api.dealer_portal import download_document
    values = signature()
    file_values = dict(attached_to_doctype='Signature Request', attached_to_name='SIG-1',
                       attached_to_field=None, file_url=values['signed_attachment'], is_private=1,
                       get_content=Mock())
    file_values.update(change); file_doc = SimpleNamespace(**file_values)
    with patch('dcr.api.dealer_portal.frappe') as frappe, \
         patch('dcr.api.dealer_portal.get_current_dealer_customer', return_value={'name':'DEALER-1'}):
        frappe.db.get_value.side_effect = [values, 'FILE-1']
        frappe.get_doc.return_value = file_doc
        frappe.throw.side_effect = ValueError
        with pytest.raises(ValueError):
            download_document('signature', 'SIG-1', 'Flooring Packet')
        file_doc.get_content.assert_not_called()


def test_signature_availability_is_scoped_and_does_not_expose_storage_urls():
    from dcr.api.dealer_portal import _get_signatures
    rows = [signature(), dict(name='SIG-2', status='Sent', document_type='Flooring Packet',
                             signed_attachment='/private/files/pending.pdf', envelope_id='ENVELOPE')]
    with patch('dcr.api.dealer_portal.frappe') as frappe, \
         patch('dcr.api.dealer_portal._available_fields', side_effect=lambda doctype, fields: fields):
        frappe.get_all.side_effect = [rows, [dict(attached_to_name='SIG-1', file_url=rows[0]['signed_attachment'])]]
        result = _get_signatures({'name':'DEALER-1'})
        assert result[0]['can_download'] is True
        assert result[1]['can_download'] is False
        assert result[1]['actionable'] is True
        assert all('signed_attachment' not in item and 'file_url' not in item for item in result)
        signature_filter = frappe.get_all.call_args_list[0].kwargs['filters']
        assert signature_filter == {'customer':'DEALER-1'}
        file_filter = frappe.get_all.call_args.kwargs['filters']
        assert file_filter == {'attached_to_doctype':'Signature Request',
                               'attached_to_name':['in',['SIG-1']],
                               'file_url':['in',['/private/files/signed.pdf']], 'is_private':1}


def test_unavailable_signed_copy_has_no_download_affordance():
    from dcr.api.dealer_portal import _get_signatures
    with patch('dcr.api.dealer_portal.frappe') as frappe, \
         patch('dcr.api.dealer_portal._available_fields', side_effect=lambda doctype, fields: fields):
        frappe.get_all.side_effect = [[signature()], []]
        assert _get_signatures({'name':'DEALER-1'})[0]['can_download'] is False
