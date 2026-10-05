"""Remaining controlled-pilot boundaries and intake/attachment regressions."""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import base64
import pytest
from dcr.api.dealer_portal import _parse_payload, HBR_INPUT_FIELDS, _serialize_hbr
from dcr.api.dcr_email import _purchase_order_quote_files, send_purchase_order_email
from dcr.dcr.doctype.ach_settings.ach_settings import loan_is_in_ach_scope


def test_dealer_can_capture_buyer_without_linking_arbitrary_customers():
    payload = {'end_buyer_name':'Pilot Buyer','end_buyer_email':'buyer@example.test','end_buyer_phone':'555-0100','installed_value':150000}
    assert _parse_payload(payload) == payload
    assert 'home_buyer' not in HBR_INPUT_FIELDS
    assert 'in_storage' not in HBR_INPUT_FIELDS


@patch('dcr.api.dealer_portal._hbr_document_items',return_value=[])
@patch('dcr.api.dealer_portal._loan_summary',return_value=None)
@patch('dcr.api.dealer_portal._has_field',return_value=True)
def test_buyer_storage_and_value_are_read_back(*mocks):
    result = _serialize_hbr({'name':'HBR-1','docstatus':0,'end_buyer_name':'Buyer','in_storage':1,'installed_value':150000})
    assert result['end_buyer_name'] == 'Buyer'
    assert result['installed_value'] == 150000
    assert result['in_storage'] is True
    assert 'in_storage' not in result['editable']


@pytest.mark.parametrize('scope,pilot,loan,expected', [('Controlled Pilot','LOAN-1','LOAN-1',True),('Controlled Pilot','LOAN-1','LOAN-OTHER',False),(None,None,'LOAN-1',False),('All Eligible Loans',None,'LOAN-1',True)])
def test_ach_scope_fails_closed_to_selected_pilot(scope,pilot,loan,expected):
    with patch('dcr.dcr.doctype.ach_settings.ach_settings.get_ach_settings') as settings:
        settings.return_value.get.side_effect = {'ach_scope':scope,'pilot_loan':pilot}.get
        assert loan_is_in_ach_scope(loan) is expected


def test_quote_files_must_belong_to_linked_deal():
    po = MagicMock(); po.get.return_value = 'HBR-1'
    hbr = MagicMock(); hbr.get.return_value = [{'document_type':'Factory Quote','attachment':'/private/files/quote.pdf'}]
    with patch('dcr.api.dcr_email.frappe') as f:
        f.get_doc.return_value = hbr; f.db.get_value.return_value = None; f.throw.side_effect = ValueError
        with pytest.raises(ValueError): _purchase_order_quote_files(po)
        f.db.get_value.assert_called_once_with('File',{'file_url':'/private/files/quote.pdf','attached_to_doctype':'Home Build Request','attached_to_name':'HBR-1'},'name')


def test_quote_list_is_deduplicated_and_checks_file_read_permission():
    po = MagicMock(); po.get.return_value = 'HBR-1'
    hbr = MagicMock(); hbr.get.return_value = [{'document_type':'Factory Quote','attachment':'/private/files/quote.pdf'}]*2
    file = MagicMock()
    with patch('dcr.api.dcr_email.frappe') as f:
        f.get_doc.side_effect = [hbr,file]; f.db.get_value.return_value = 'FILE-1'
        assert _purchase_order_quote_files(po) == [file]
        file.check_permission.assert_called_once_with('read')


def test_po_email_contains_po_pdf_and_original_uploaded_quote():
    generic = MagicMock(); generic.generate_pdf_attachment.return_value = [{'filename':'PO-1.pdf','content':'PDF'}]
    file = MagicMock(); file.file_name = 'quote-original.pdf'; file.get_content.return_value = b'UPLOADED-QUOTE'
    with patch.dict('sys.modules',{'emails':MagicMock(),'emails.email_service':MagicMock(),'emails.email_service.generic_email':generic}), patch('dcr.api.dcr_email.frappe'), patch('dcr.api.dcr_email._purchase_order_quote_files',return_value=[file]), patch('dcr.api.dcr_email._purchase_order_email_context',return_value={}):
        send_purchase_order_email('PO-1','pilot@example.test')
    attachments = generic.send_document_email.call_args.kwargs['attachments']
    assert attachments[0]['filename'] == 'PO-1.pdf'
    assert attachments[1]['filename'] == 'quote-original.pdf'
    assert base64.b64decode(attachments[1]['content']) == b'UPLOADED-QUOTE'


def test_partial_lending_visibility_cannot_report_false_available_credit():
    from dcr.api.lending import _require_complete_dealer_loan_access
    with patch('dcr.api.lending.require_staff'), patch('dcr.api.lending.frappe') as f:
        f.get_all.return_value=['LOAN-1','LOAN-2']; f.get_list.return_value=['LOAN-1']; f.throw.side_effect=PermissionError
        with pytest.raises(PermissionError): _require_complete_dealer_loan_access('DEALER-1')


def test_refused_cancellation_does_not_stop_revoking_future_debits():
    from dcr.api.bank_account_ach import _cancel_pending_transactions
    txn = MagicMock(); txn.status='Initiated'; txn.cancel_transaction.side_effect=ValueError('Already processing')
    with patch('dcr.api.bank_account_ach.frappe') as f:
        f.get_all.side_effect=[['ACH-1'],[]]; f.get_doc.return_value=txn
        assert _cancel_pending_transactions('BANK-1') == ['ACH-1']
        f.msgprint.assert_called_once()


def test_portal_submission_records_staff_notice_after_persisting_review_state():
    from dcr.api.dealer_portal import submit_hbr_for_review
    hbr=SimpleNamespace(name='HBR-1',docstatus=0,custom_portal_status='Draft',reload=MagicMock())
    with patch('dcr.api.dealer_portal.frappe') as f, patch('dcr.api.dealer_portal.get_current_dealer_customer'), patch('dcr.api.dealer_portal._get_owned_hbr',return_value=hbr), patch('dcr.api.dealer_portal._has_field',return_value=True), patch('dcr.api.dealer_portal._serialize_hbr'), patch('dcr.api.status_notices.record_transition') as notice:
        def record(*args):
            f.db.set_value.assert_called_once()
            assert args==(hbr,'custom_portal_status','Draft','Submitted for Review')
        notice.side_effect=record
        submit_hbr_for_review('HBR-1')
        notice.assert_called_once()


def test_existing_due_date_attempt_blocks_schedule_admission_after_loan_lock():
    from dcr.tasks.scheduled_debits import process_loan_payment
    from datetime import date
    with patch('dcr.tasks.scheduled_debits.frappe') as f, patch('dcr.tasks.scheduled_debits.get_next_unpaid_repayment',return_value=(date(2026,10,10),1000)):
        f.get_doc.return_value.name='LOAN-1'; f.db.exists.return_value='ACH-EXISTING'
        def existing(*args,**kwargs):
            f.db.get_value.assert_called_once_with('Loan','LOAN-1','name',for_update=True)
            return 'ACH-EXISTING'
        f.db.exists.side_effect=existing
        process_loan_payment(SimpleNamespace(name='LOAN-1'),SimpleNamespace(name='BANK-1'),'2026-10-10',3)
        f.new_doc.assert_not_called()


def test_kanban_storage_field_preserves_existing_card_fields():
    import json
    from dcr.setup import ensure_hbr_kanban_columns
    fields={'fields':'["home_serial_no","quote_no"]','filters':None,'show_labels':0,'columns':[]}
    board=MagicMock(); board.get.side_effect=fields.get
    with patch('dcr.setup.frappe') as f:
        f.db.exists.return_value=True; f.get_all.return_value=['HBR']; f.get_doc.return_value=board
        ensure_hbr_kanban_columns()
        assert json.loads(board.fields)==['home_serial_no','quote_no','in_storage']
        assert board.show_labels==1


@pytest.mark.parametrize('unpaid,expected',[(0,'Yes'),(1,'No')])
def test_dealer_current_uses_submitted_unpaid_demands(unpaid,expected):
    from dcr.api.lending import is_dealer_current
    with patch('dcr.api.lending.frappe') as f:
        f.db.sql.return_value=[[unpaid]]
        assert is_dealer_current('DEALER-1')==expected
        query,params=f.db.sql.call_args.args
        assert '`tabLoan Demand`' in query and 'demand.outstanding_amount > 0' in query
        assert 'demand.docstatus = 1' in query
        assert params[0]=='DEALER-1'


def test_staff_acceptance_updates_portal_state_and_records_dealer_notice():
    from dcr.dcr.doctype.home_build_request.home_build_request import HomeBuildRequest
    doc=MagicMock(); doc.meta.has_field.return_value=True; doc.get.return_value='Submitted for Review'
    with patch('dcr.api.status_notices.record_transition') as notice:
        HomeBuildRequest.on_submit(doc)
        doc.db_set.assert_any_call('custom_portal_status','Accepted')
        notice.assert_called_once_with(doc,'custom_portal_status','Submitted for Review','Accepted')
