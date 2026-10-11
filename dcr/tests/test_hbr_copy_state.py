from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dcr.api import hbr_stage as stages


class Request(dict):
    name = 'REQUEST'
    meta = SimpleNamespace(has_field=lambda name: True)

    def set(self, name, value):
        self[name] = value


@pytest.mark.parametrize('financing,expected', [('Floored', 'Not Started'), ('Cash', 'Not Applicable')])
def test_saved_copy_cannot_claim_acceptance_or_funding_without_documents(financing, expected):
    doc = Request(docstatus=0, status='Submitted', custom_portal_status='Accepted',
                  custom_portal_submitted_on='2026-10-01', custom_portal_submitted_by='OLD-DEALER',
                  financing_type=financing, custom_loan_stage='Funded', custom_order_stage='Ordered')
    with patch.object(stages, '_has_submitted_purchase_order', return_value=False), \
            patch.object(stages, '_has_submitted_purchase_receipt', return_value=False), \
            patch.object(stages, '_latest_loan_status', return_value=None), \
            patch.object(stages, '_latest_loan_application_status', return_value=None):
        stages.apply_hbr_stage_defaults(doc)
    assert doc['status'] == doc['custom_portal_status'] == doc['custom_order_stage'] == 'Draft'
    assert doc['custom_loan_stage'] == expected
    assert doc['custom_portal_submitted_on'] is None
    assert doc['custom_portal_submitted_by'] is None


@pytest.mark.parametrize('loan,application,expected', [('Closed', 'Approved', 'Closed'),
    ('Disbursed', 'Approved', 'Funded'), ('Sanctioned', 'Approved', 'Approved'),
    (None, 'Signed', 'Applied')])
def test_existing_accepted_request_keeps_actual_document_stage(loan, application, expected):
    doc = Request(docstatus=1, status='Submitted', custom_portal_status='Accepted',
                  financing_type='Floored', custom_loan_stage='Funded', custom_order_stage='Ordered')
    with patch.object(stages, '_has_submitted_purchase_order', return_value=True), \
            patch.object(stages, '_has_submitted_purchase_receipt', return_value=False), \
            patch.object(stages, '_latest_loan_status', return_value=loan), \
            patch.object(stages, '_latest_loan_application_status', return_value=application):
        stages.apply_hbr_stage_defaults(doc)
    assert doc['status'] == 'Submitted'
    assert doc['custom_portal_status'] == 'Accepted'
    assert doc['custom_loan_stage'] == expected
    assert doc['custom_order_stage'] == 'Ordered'


def test_draft_under_review_retains_submission_audit():
    doc = Request(docstatus=0, status='Draft', custom_portal_status='Submitted for Review',
                  custom_portal_submitted_on='2026-10-11', custom_portal_submitted_by='DEALER',
                  financing_type='Floored', custom_loan_stage='Not Started')
    with patch.object(stages, '_has_submitted_purchase_order', return_value=False), \
            patch.object(stages, '_has_submitted_purchase_receipt', return_value=False), \
            patch.object(stages, '_latest_loan_status', return_value=None), \
            patch.object(stages, '_latest_loan_application_status', return_value=None):
        stages.apply_hbr_stage_defaults(doc)
    assert doc['custom_portal_status'] == 'Submitted for Review'
    assert doc['custom_portal_submitted_on'] == '2026-10-11'
    assert doc['custom_portal_submitted_by'] == 'DEALER'
