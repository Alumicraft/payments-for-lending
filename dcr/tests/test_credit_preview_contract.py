"""The draft refresh must agree with server-side loan validation."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dcr.api.lending import get_available_credit


@pytest.mark.parametrize("mifa", [None, SimpleNamespace(name="MIFA-ZERO", credit_limit=0)])
def test_missing_or_zero_limit_keeps_existing_balance_and_status(mifa):
    with (
        patch("dcr.api.lending.frappe") as frappe,
        patch("dcr.api.lending.require_staff"),
        patch("dcr.api.lending._require_complete_dealer_loan_access"),
        patch("dcr.api.lending._get_dealer_outstanding_balance", return_value=124561),
        patch("dcr.api.lending.is_dealer_current", return_value="No"),
    ):
        frappe.db.get_value.return_value = mifa
        assert get_available_credit("DEMO") == {
            "credit_limit": 0,
            "outstanding": 124561,
            "available": 0,
            "current_yn": "No",
        }


def test_positive_limit_subtracts_balance_and_retains_status():
    with (
        patch("dcr.api.lending.frappe") as frappe,
        patch("dcr.api.lending.require_staff") as access,
        patch("dcr.api.lending._require_complete_dealer_loan_access") as loan_access,
        patch("dcr.api.lending._get_dealer_outstanding_balance", return_value=124561),
        patch("dcr.api.lending.is_dealer_current", return_value="No"),
    ):
        frappe.db.get_value.return_value = SimpleNamespace(name="MIFA-1", credit_limit=300000)
        assert get_available_credit("DEMO") == {
            "credit_limit": 300000,
            "outstanding": 124561,
            "available": 175439,
            "current_yn": "No",
        }
        loan_access.assert_called_once_with("DEMO")
        access.assert_any_call("MIFA", "MIFA-1")
