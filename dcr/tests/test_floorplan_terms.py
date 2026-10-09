from unittest.mock import patch
import pytest
from dcr.api import floorplan_terms
from dcr.api import financing_basis
from dcr.api import lending
from dcr.tests.test_financing_basis import Doc
from dcr.tests.test_loan_repayment_schedule_override import import_override_with_stubs


def test_shared_product_reader_matches_schedule_contract_precedence():
    module,f = import_override_with_stubs()
    fields = dict(custom_contract_interest_rate=15,custom_rate_of_interest=18,
                  custom_interest_only_months=12,custom_monthly_principal_pct=1,
                  custom_schedule_type='Interest Only Then Percent Principal')
    f.db.has_column.side_effect = lambda doctype,name: name in fields
    f.db.get_value.side_effect = lambda doctype,product,name: fields.get(name)
    schedule = module.CustomLoanRepaymentSchedule()
    schedule.loan_product='Standard'; schedule.rate_of_interest=12
    with patch.object(floorplan_terms,'frappe',f):
        terms = floorplan_terms.product_terms('Standard',12)
    assert terms['annual_rate'] == schedule.get_contract_interest_rate() == 15
    assert terms['interest_only_periods'] == 12
    assert terms['monthly_principal_percent'] == 1


def test_packet_cannot_sign_application_rate_that_differs_from_product_contract():
    app=Doc(company='DCR',loan_product='Standard',rate_of_interest=12,loan_amount=225000)
    with patch.object(financing_basis,'frappe') as f, patch.object(financing_basis,'product_terms',return_value={
        'annual_rate':15,'schedule_type':'Interest Only Then Percent Principal'}):
        f.throw.side_effect = ValueError
        with pytest.raises(ValueError): financing_basis.financial_snapshot(app)


def test_non_floorplan_preview_preserves_native_product_behavior():
    with patch.object(lending,'require_staff'), patch.object(lending,'product_terms',return_value={'schedule_type':'Native'}):
        assert lending.get_dated_loan_preview('Loan',225000,12,36,loan_product='Other') == {}


@pytest.mark.parametrize('value', ['NaN','Infinity',-1,0,101])
def test_invalid_configured_principal_percentage_is_rejected(value):
    with patch.object(floorplan_terms,'frappe') as f:
        f.db.has_column.return_value = True
        f.db.get_value.side_effect = lambda doctype,product,name: 'Interest Only Then Percent Principal' if name == 'custom_schedule_type' else value if name == 'custom_monthly_principal_pct' else None
        f.throw.side_effect=ValueError
        with pytest.raises(ValueError): floorplan_terms.product_terms('Standard',12)


def test_native_product_does_not_validate_unused_floorplan_settings():
    with patch.object(floorplan_terms,'frappe') as f:
        f.db.has_column.return_value = True
        f.db.get_value.return_value = 'Native'
        assert floorplan_terms.product_terms('Other',12) == {'schedule_type':'Native'}
        assert f.db.get_value.call_count == 1
