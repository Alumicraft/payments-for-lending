"""Reproduce the installed Lending carry-forward calculation without a bench.

Run with a local copy of the pinned upstream repayment schedule controller.
This extracts its actual method, not a reimplementation. No database or network
writes occur. Exit 1 means its carry interest disagrees with DCR Actual/360.
"""

import argparse
import ast
from datetime import date
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


PINNED_SHA256 = "8ae00a7598f0a8becee4459fafee9f5e968b22ae44b8d641aaab2f2c7b46cf33"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native_source", type=Path)
    parser.add_argument("--dcr", action="store_true", help="Run the current DCR carry override against the same fixture")
    args = parser.parse_args()
    source = args.native_source.read_bytes()
    if hashlib.sha256(source).hexdigest() != PINNED_SHA256:
        parser.error("Source must match installed Lending commit 97f692e")
    tree = ast.parse(source)
    controller = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                      and node.name == "LoanRepaymentSchedule")
    method = next(node for node in controller.body if isinstance(node, ast.FunctionDef)
                  and node.name == "add_rows_from_prev_disbursement")
    if args.dcr:
        dcr_path = Path(__file__).resolve().parents[2] / 'dcr/overrides/loan_repayment_schedule.py'
        dcr_tree = ast.parse(dcr_path.read_text())
        dcr_controller = next(node for node in dcr_tree.body if isinstance(node, ast.ClassDef)
                              and node.name == 'CustomLoanRepaymentSchedule')
        method = next(node for node in dcr_controller.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'add_rows_from_prev_disbursement')

    def getdate(value):
        return value if isinstance(value, date) else date.fromisoformat(value)

    old_row = SimpleNamespace(payment_date=date(2026, 1, 1), principal_amount=0,
                              interest_amount=1000, total_payment=1000,
                              balance_loan_amount=100000, number_of_days=30,
                              demand_generated=1)
    previous = SimpleNamespace(posting_date=date(2025, 12, 1),
                               repayment_start_date=date(2026, 1, 1),
                               current_principal_amount=100000,
                               monthly_repayment_amount=1000,
                               broken_period_interest=0,
                               total_installments_raised=1, total_installments_paid=1,
                               total_installments_overdue=0,
                               get=lambda field: [old_row])
    native_globals = {
        "frappe": SimpleNamespace(db=SimpleNamespace(get_value=lambda *args: "Partially Disbursed"),
                                  get_doc=lambda *args: previous),
        "getdate": getdate,
        "date_diff": lambda end, start: (getdate(end) - getdate(start)).days,
        "flt": lambda value: float(value or 0),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(args.native_source), "exec"),
         native_globals)
    schedule = SimpleNamespace(current_principal_amount=100000, disbursed_amount=10000,
                               loan="DEMO", loan_disbursement=None,
                               repayment_schedule_type="Monthly as per repayment start date",
                               repayment_frequency="Monthly", restructure_type=None,
                               repayment_method="Repay Fixed Amount per Period",
                               repayment_start_date=date(2026, 2, 1),
                               posting_date=date(2026, 1, 16), moratorium_end_date=None,
                               rate_of_interest=12,
                               is_dcr_floorplan_structure=lambda: True,
                               get_contract_interest_rate=lambda: 12,
                               add_repayment_schedule_row=lambda *args, **kwargs: None)
    carry, balance, _, days = native_globals[method.name](schedule, "repayment_schedule", 100)
    expected = round(100000 * 12 * 15 / 36000, 2)
    actual = round(carry, 2)
    print(json.dumps(dict(scenario="15-day partial-disbursement carry", implementation='DCR' if args.dcr else 'upstream', days=days,
                          balance=balance, actual_carry=actual, expected_actual360=expected,
                          passed=actual == expected), sort_keys=True))
    return 0 if actual == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
