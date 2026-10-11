from lending.loan_management.doctype.process_loan_interest_accrual.process_loan_interest_accrual import (
    ProcessLoanInterestAccrual,
)

from dcr.api.floorplan_accrual import actual_principal_accruals


class CustomProcessLoanInterestAccrual(ProcessLoanInterestAccrual):
    def on_submit(self):
        with actual_principal_accruals():
            return super().on_submit()
