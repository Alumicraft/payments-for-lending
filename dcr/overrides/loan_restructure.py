"""Keep restructure interest on the same actual principal basis as accruals."""

from lending.loan_management.doctype.loan_restructure.loan_restructure import LoanRestructure

from dcr.api.floorplan_accrual import actual_principal_accruals, floorplan_loan, interest_projection


class CustomLoanRestructure(LoanRestructure):
    def update_overdue_amounts(self):
        with actual_principal_accruals():
            result = super().update_overdue_amounts()
        loan = floorplan_loan(self.loan)
        if loan:
            rounded, native = interest_projection(loan, self.restructure_date)
            self.unaccrued_interest = round(float(self.unaccrued_interest) + float(rounded-native), 2)
        return result
