from contextlib import contextmanager

from lending.loan_management.doctype.process_loan_demand.process_loan_demand import (
    ProcessLoanDemand,
)

from dcr.api.lending import create_loan_demand_with_context


@contextmanager
def _patched_create_loan_demand():
    from lending.loan_management.doctype.loan_demand import loan_demand

    original = loan_demand.create_loan_demand
    loan_demand.create_loan_demand = create_loan_demand_with_context
    try:
        yield
    finally:
        loan_demand.create_loan_demand = original


class CustomProcessLoanDemand(ProcessLoanDemand):
    def on_submit(self):
        with _patched_create_loan_demand():
            return super().on_submit()
