from lending.loan_management.doctype.loan_demand.loan_demand import LoanDemand

from dcr.api.lending import populate_loan_demand_from_loan
from dcr.api.floorplan_accrual import scheduled_interest_due


class CustomLoanDemand(LoanDemand):
    def validate(self):
        populate_loan_demand_from_loan(self)
        if ((self.get('docstatus', 0) == 0 or self.is_new()) and self.get('demand_type') == 'EMI'
                and self.get('demand_subtype') == 'Interest'
                and self.get('repayment_schedule_detail') and self.get('process_loan_demand')
                and not self.get('loan_repayment') and not self.get('is_imported')
                and not self.get('paid_amount') and not self.get('is_partial_pre_paid_interest')):
            actual = scheduled_interest_due(self.loan, self.demand_date)
            if actual is not None:
                self.demand_amount = float(actual)
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
        if not self.demand_amount:
            return
        return super().make_gl_entries(cancel=cancel)
