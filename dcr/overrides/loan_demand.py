from lending.loan_management.doctype.loan_demand.loan_demand import LoanDemand

from dcr.api.lending import populate_loan_demand_from_loan


class CustomLoanDemand(LoanDemand):
    def validate(self):
        populate_loan_demand_from_loan(self)
        super_validate = getattr(super(), "validate", None)
        if callable(super_validate):
            super_validate()

    def before_submit(self):
        populate_loan_demand_from_loan(self)
        super_before_submit = getattr(super(), "before_submit", None)
        if callable(super_before_submit):
            super_before_submit()

    def make_gl_entries(self, cancel=0):
        populate_loan_demand_from_loan(self)
        return super().make_gl_entries(cancel=cancel)
