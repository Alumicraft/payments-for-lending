"""Keep restructure interest on the same actual principal basis as accruals."""

from lending.loan_management.doctype.loan_restructure.loan_restructure import LoanRestructure

from dcr.api.floorplan_accrual import actual_principal_accruals


class CustomLoanRestructure(LoanRestructure):
    def update_overdue_amounts(self):
        with actual_principal_accruals():
            return super().update_overdue_amounts()
