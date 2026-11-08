"""Tests for DCR Loan Repayment Schedule controller compatibility."""

from datetime import date
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
    frappe_utils.getdate = lambda value: value if isinstance(value, date) else date.fromisoformat(str(value))
    frappe_utils.date_diff = lambda end, start: (frappe_utils.getdate(end) - frappe_utils.getdate(start)).days
    frappe_utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)

    class BaseLoanRepaymentSchedule:
        def add_rows_from_prev_disbursement(self, *args):
            self.base_carry_args = args
            return (1, 2, 3, 4)

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
    def test_extra_principal_carries_unpaid_earned_interest_and_continues_curtailment(self):
        from types import SimpleNamespace
        module, frappe = import_override_with_stubs()
        old = SimpleNamespace(payment_date=date(2028, 1, 1), principal_amount=2250,
                              interest_amount=2301.75, total_payment=4551.75,
                              balance_loan_amount=220500, number_of_days=31, demand_generated=1)
        previous = SimpleNamespace(posting_date=date(2026, 11, 1), loan_disbursement=None,
            repayment_start_date=date(2026, 12, 1), current_principal_amount=225000,
            monthly_repayment_amount=4500, broken_period_interest=0,
            floorplan_periods_before_schedule=13, total_installments_raised=14,
            total_installments_paid=14, total_installments_overdue=0,
            get=lambda field: [old])
        frappe.get_doc = MagicMock(return_value=previous)
        for unpaid in (0, 1029):
            with self.subTest(unpaid=unpaid):
                def value(doctype, name, field):
                    if doctype == 'Loan':
                        return 'Disbursed'
                    if field == 'balance_unaccrued_interest':
                        return unpaid
                    return (1029, 1029 - unpaid)
                frappe.db.get_value.side_effect = value
                schedule = module.CustomLoanRepaymentSchedule()
                values = dict(loan='LOAN', loan_product='Standard', loan_restructure='RESTRUCTURE',
                    current_principal_amount=215500, loan_disbursement=None,
                    repayment_schedule_type='Monthly as per repayment start date',
                    repayment_frequency='Monthly', restructure_type='Pre Payment',
                    repayment_method='Repay Fixed Amount per Period',
                    repayment_start_date=date(2028, 2, 1), posting_date=date(2028, 1, 15),
                    moratorium_end_date=None, rate_of_interest=12)
                for key, val in values.items():
                    setattr(schedule, key, val)
                rows = []
                schedule.get = lambda field: rows
                schedule.is_dcr_floorplan_structure = lambda: True
                schedule.get_contract_interest_rate = lambda: 12
                schedule.get_floorplan_principal_reduction = lambda *args: 2250
                schedule.extra_payment_interest = lambda next_due: 1221.17
                schedule.get_prev_schedule_demand_generated = lambda *args: 0
                schedule.get_next_payment_date = lambda day: (
                    date(2028, 2, 1) if day < date(2028, 2, 1) else date(2028, 3, 1))
                schedule.add_repayment_schedule_row = lambda *args, **kwargs: rows.append(
                    SimpleNamespace(payment_date=args[0], principal_amount=args[1],
                        interest_amount=args[2], total_payment=args[4], balance_loan_amount=args[5]))
                result = schedule.add_rows_from_prev_disbursement('repayment_schedule', 100)
                self.assertEqual(rows[-1].payment_date, date(2028, 2, 1))
                self.assertEqual(rows[-1].principal_amount, 2250)
                self.assertEqual(rows[-1].interest_amount, round(1221.1666666667 + unpaid, 2))
                self.assertEqual(rows[-1].balance_loan_amount, 213250)
                self.assertEqual(result, (0, 213250, 0, 0))

    def test_non_dcr_carry_still_uses_native_controller(self):
        module, _ = import_override_with_stubs()
        schedule = module.CustomLoanRepaymentSchedule()
        schedule.is_dcr_floorplan_structure = lambda: False
        self.assertEqual(schedule.add_rows_from_prev_disbursement('repayment_schedule', 75, 50), (1,2,3,4))
        self.assertEqual(schedule.base_carry_args, ('repayment_schedule',75,50))

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
        schedule.make_repayment_schedule("repayment_schedule", 0, 218000, 0, 0, 12, 100, 100)
        schedule.set.assert_not_called()
        schedule.make_dcr_repayment_schedule.assert_called_once_with(
            "repayment_schedule", previous_interest_amount=0, balance_amount=218000,
            additional_principal_amount=0, pending_prev_days=0, rate_of_interest=12,
            principal_share_percentage=100, interest_share_percentage=100,
        )

    def test_missing_optional_loan_product_fields_are_skipped(self):
        module, frappe = import_override_with_stubs()
        frappe.db.has_column.return_value = False

        schedule = module.CustomLoanRepaymentSchedule()
        schedule.loan_product = "Standard"
        schedule.rate_of_interest = 12

        self.assertEqual(schedule.get_contract_interest_rate(), 12)
        frappe.db.get_value.assert_not_called()

    def test_add_schedule_row_appends_without_lending_helper(self):
        module, _frappe = import_override_with_stubs()

        schedule = module.CustomLoanRepaymentSchedule()
        schedule.append = MagicMock()
        schedule._add_schedule_row(
            schedule_field="repayment_schedule",
            payment_date="2026-05-05",
            principal_amount=0,
            interest_amount=2180,
            total_payment=2180,
            balance_loan_amount=218000,
            days=30,
        )

        schedule.append.assert_called_once_with(
            "repayment_schedule",
            {
                "payment_date": "2026-05-05",
                "principal_amount": 0,
                "interest_amount": 2180,
                "total_payment": 2180,
                "balance_loan_amount": 218000,
                "number_of_days": 30,
            },
        )


if __name__ == "__main__":
    unittest.main()
