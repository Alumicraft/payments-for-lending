"""Tests for DCR Loan Repayment Schedule controller compatibility."""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def import_override_with_stubs():
    frappe = types.ModuleType("frappe")
    frappe.db = MagicMock()

    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.add_months = lambda date, months: date
    frappe_utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)

    class BaseLoanRepaymentSchedule:
        def make_repayment_schedule(self, *args, **kwargs):
            self.base_args = args
            self.base_kwargs = kwargs
            return "base"

    lending = types.ModuleType("lending")
    loan_management = types.ModuleType("lending.loan_management")
    doctype = types.ModuleType("lending.loan_management.doctype")
    lrs_pkg = types.ModuleType(
        "lending.loan_management.doctype.loan_repayment_schedule"
    )
    lrs_mod = types.ModuleType(
        "lending.loan_management.doctype.loan_repayment_schedule.loan_repayment_schedule"
    )
    lrs_mod.LoanRepaymentSchedule = BaseLoanRepaymentSchedule

    modules = {
        "frappe": frappe,
        "frappe.utils": frappe_utils,
        "lending": lending,
        "lending.loan_management": loan_management,
        "lending.loan_management.doctype": doctype,
        "lending.loan_management.doctype.loan_repayment_schedule": lrs_pkg,
        "lending.loan_management.doctype.loan_repayment_schedule.loan_repayment_schedule": lrs_mod,
    }

    with patch.dict(sys.modules, modules):
        sys.modules.pop("dcr.overrides.loan_repayment_schedule", None)
        module = importlib.import_module("dcr.overrides.loan_repayment_schedule")
        return module, frappe


class TestLoanRepaymentScheduleOverride(unittest.TestCase):
    def test_non_dcr_schedule_passes_lending_v16_args_to_base(self):
        module, _frappe = import_override_with_stubs()

        schedule = module.CustomLoanRepaymentSchedule()
        schedule.is_dcr_floorplan_structure = lambda: False

        result = schedule.make_repayment_schedule(
            "repayment_schedule",
            "2026-05-05",
            218000,
            12,
            "Monthly",
            "Repay Over Number of Periods",
            0,
            100,
        )

        self.assertEqual(result, "base")
        self.assertEqual(
            schedule.base_args,
            (
                "repayment_schedule",
                "2026-05-05",
                218000,
                12,
                "Monthly",
                "Repay Over Number of Periods",
                0,
                100,
            ),
        )

    def test_dcr_schedule_accepts_lending_v16_args(self):
        module, _frappe = import_override_with_stubs()

        schedule = module.CustomLoanRepaymentSchedule()
        schedule.is_dcr_floorplan_structure = lambda: True
        schedule.set = MagicMock()
        schedule.make_dcr_repayment_schedule = MagicMock()

        schedule.make_repayment_schedule(
            "repayment_schedule",
            "2026-05-05",
            218000,
            12,
            "Monthly",
            "Repay Over Number of Periods",
            0,
            100,
        )

        schedule.set.assert_called_once_with("repayment_schedule", [])
        schedule.make_dcr_repayment_schedule.assert_called_once_with(
            "repayment_schedule"
        )

    def test_missing_optional_loan_product_fields_are_skipped(self):
        module, frappe = import_override_with_stubs()
        frappe.db.has_column.return_value = False

        schedule = module.CustomLoanRepaymentSchedule()
        schedule.loan_product = "Standard"
        schedule.rate_of_interest = 12

        self.assertEqual(schedule.get_contract_interest_rate(), 12)
        frappe.db.get_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
