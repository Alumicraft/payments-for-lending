"""DCR safeguards for Frappe Lending repayments."""

import frappe
from frappe.utils import cint, flt
from lending.loan_management.doctype.loan_repayment.loan_repayment import LoanRepayment

from dcr.lending_rules import has_material_outstanding_principal


class CustomLoanRepayment(LoanRepayment):
    def auto_close_loan(self):
        """Do not close an interest-only loan while principal is outstanding.

        Frappe Lending's generic auto-close rule considers a normal repayment
        complete when the current installment has zero principal due and its
        interest is fully paid. DCR interest-only schedules intentionally have
        zero principal on each monthly row, so that rule would close a
        $100,000 loan after its first $1,000 interest payment.
        """
        auto_close = super().auto_close_loan()
        if not auto_close or self.repayment_type in (
            "Full Settlement",
            "Write Off Settlement",
            "Write Off Recovery",
        ):
            return auto_close

        loan = frappe.db.get_value(
            "Loan",
            self.against_loan,
            ["loan_amount", "total_principal_paid", "loan_product"],
            as_dict=True,
        )
        if not loan:
            return auto_close

        write_off_amount = frappe.get_cached_value(
            "Loan Product",
            loan.get("loan_product"),
            "write_off_amount",
        )
        precision = cint(frappe.db.get_default("currency_precision")) or 2
        if has_material_outstanding_principal(
            loan_amount=flt(loan.get("loan_amount")),
            total_principal_paid=flt(loan.get("total_principal_paid")),
            current_principal_paid=flt(self.principal_amount_paid),
            write_off_amount=flt(write_off_amount),
            precision=precision,
        ):
            self.flags.auto_close = False

        return self.flags.auto_close
