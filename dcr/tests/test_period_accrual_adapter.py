from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys

import pytest

from dcr.api import floorplan_accrual as accrual


class Record(SimpleNamespace):
    def get(self, field, default=None):
        return getattr(self, field, default)


def contract():
    return Record(name='LOAN',company='DCR',rate_of_interest=12,is_term_loan=1,
                  repayment_start_date='2026-12-01',repayment_schedule_type='Monthly as per repayment start date')


EVENTS = [('2026-11-01',225000),('2027-12-01',-2250),('2028-01-01',-2250),('2028-01-15',-5000)]


def test_native_daily_entry_receives_cumulative_cent_amounts_and_context_restores_after_failure():
    getter, entry = Mock(), Mock()
    native=SimpleNamespace(get_principal_amount_for_term_loan=getter,make_loan_interest_accrual_entry=entry)
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_interest_accrual':
            SimpleNamespace(loan_interest_accrual=native)}), \
            patch.object(accrual,'floorplan_loan',return_value=contract()), \
            patch.object(accrual,'principal_events',return_value=EVENTS):
        with pytest.raises(RuntimeError):
            with accrual.actual_principal_accruals():
                for offset in range(31):
                    day=date(2028,1,1)+timedelta(days=offset)
                    native.make_loan_interest_accrual_entry('LOAN',999999,0,'PROCESS',day,day,
                        'Regular','Normal Interest',12,loan_repayment_schedule='SCHEDULE')
                raise RuntimeError('rollback')
    assert native.get_principal_amount_for_term_loan is getter
    assert native.make_loan_interest_accrual_entry is entry
    assert sum(Decimal(str(c.args[2])) for c in entry.call_args_list)==Decimal('2250.17')
    assert [c.args[2] for c in entry.call_args_list[14:17]]==[71.83,71.84,71.83]
    assert entry.call_args_list[14].args[1]==215500
    assert entry.call_args.kwargs['loan_repayment_schedule']=='SCHEDULE'


@pytest.mark.parametrize('kind,imported',[('Penal Interest',False),('Normal Interest',True)])
def test_penalty_and_imported_history_keep_the_native_amount(kind,imported):
    entry=Mock()
    native=SimpleNamespace(get_principal_amount_for_term_loan=Mock(),make_loan_interest_accrual_entry=entry)
    with patch.dict(sys.modules, {'lending.loan_management.doctype.loan_interest_accrual':
            SimpleNamespace(loan_interest_accrual=native)}), \
            patch.object(accrual,'floorplan_loan') as eligibility:
        with accrual.actual_principal_accruals():
            native.make_loan_interest_accrual_entry('LOAN',100,77,None,'2028-01-01','2028-01-01',
                                                   'Regular',kind,12,is_imported=imported)
    eligibility.assert_not_called()
    assert entry.call_args.args[2]==77


def test_extra_payment_preview_adds_the_event_once_before_or_after_receipt_submission():
    for events in (EVENTS[:-1],EVENTS):
        with patch.object(accrual,'floorplan_loan',return_value=contract()), \
                patch.object(accrual,'principal_events',return_value=list(events)):
            assert accrual.extra_payment_interest('LOAN','2028-01-15','2028-02-01',215500)==1221.17


def test_projected_tail_uses_the_same_monthly_cumulative_rounding_as_posted_days():
    loan=Record(name='LOAN',company='DCR',rate_of_interest=12,repayment_start_date='2026-02-01')
    with patch.object(accrual,'frappe') as frappe, \
            patch.object(accrual,'principal_events',return_value=[('2026-01-01',265000)]):
        frappe.db.get_value.return_value='Daily'
        frappe.get_all.return_value=[Record(posting_date='2026-01-01')]
        assert accrual.interest_projection(loan,'2026-01-03')==(Decimal('88.34'),Decimal('88.33'))


def test_mapped_pre_payment_uses_the_loans_term_flag_and_schedule_type():
    doc=Record(repayment_type='Pre Payment',against_loan='LOAN',is_term_loan=0,repayment_schedule_type=None)
    with patch.object(accrual,'floorplan_loan',return_value=contract()):
        accrual.populate_repayment_loan_type(doc)
    assert doc.is_term_loan==1
    assert doc.repayment_schedule_type=='Monthly as per repayment start date'


def test_restructure_keeps_the_original_application_period_anchor():
    loan = Record(loan_application='APPLICATION', repayment_start_date='2028-01-15')
    with patch.object(accrual, 'frappe') as frappe:
        frappe.db.get_value.return_value = '2026-12-01'
        assert accrual.first_payment_date(loan) == '2026-12-01'
        frappe.db.get_value.assert_called_once_with('Loan Application', 'APPLICATION', 'first_payment_date')
