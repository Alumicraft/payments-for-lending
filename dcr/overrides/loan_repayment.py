"""DCR safeguards for Frappe Lending repayments."""

import frappe
from frappe.utils import cint, flt
from lending.loan_management.doctype.loan_repayment.loan_repayment import LoanRepayment

from dcr.lending_rules import has_material_outstanding_principal


class CustomLoanRepayment(LoanRepayment):
    def allocate_charges(self, amount_paid, demands):
        remaining = super().allocate_charges(amount_paid, demands)
        precision = cint(frappe.db.get_default("currency_precision")) or 2
        if self.repayment_type == 'Charge Payment' and flt(remaining, precision) > 0:
            frappe.throw(
                'Set the amounts in Payable Charges to cover this Charge Payment. '
                'The payment cannot include principal or interest.'
            )
        return remaining

    def set_missing_values(self, amounts):
        if self.repayment_type == 'Loan Closure':
            from dcr.api.floorplan_accrual import adjust_closure_amounts

            adjust_closure_amounts(self.against_loan, self.value_date, amounts)
        return super().set_missing_values(amounts)

    def mark_as_unpaid(self):
        if self.repayment_type not in ('Charge Payment', 'Charges Waiver'):
            return super().mark_as_unpaid()
        loan = frappe.qb.DocType('Loan')
        query = (
            frappe.qb.update(loan)
            .set(loan.total_amount_paid, loan.total_amount_paid - self.amount_paid)
            .set(loan.total_principal_paid, loan.total_principal_paid - self.principal_amount_paid)
            .where(loan.name == self.against_loan)
        )
        if self.loan_disbursement:
            disbursement = frappe.qb.DocType('Loan Disbursement')
            (
                frappe.qb.update(disbursement)
                .set(disbursement.principal_amount_paid,
                     disbursement.principal_amount_paid - self.principal_amount_paid)
                .where(disbursement.name == self.loan_disbursement)
            ).run()
        self.update_limits(query, loan, cancel=1).run()

    def before_submit(self):
        if self.repayment_type == 'Loan Closure':
            from datetime import timedelta
            from frappe.utils import getdate
            from dcr.api.floorplan_accrual import floorplan_loan

            if floorplan_loan(self.against_loan):
                from lending.loan_management.doctype.process_loan_interest_accrual.process_loan_interest_accrual import (
                    process_loan_interest_accrual_for_loans,
                )

                process_loan_interest_accrual_for_loans(
                    posting_date=getdate(self.value_date) - timedelta(days=1),
                    loan=self.against_loan, loan_disbursement=self.loan_disbursement,
                    from_demand=True,
                )
                self.validate()
        native_before_submit = getattr(super(), 'before_submit', None)
        if callable(native_before_submit):
            return native_before_submit()

    def validate(self):
        if (self.repayment_type == 'Charge Payment'
                or (self.repayment_type in ('Charges Waiver', 'Charges Capitalization')
                    and self.get('loan_restructure'))):
            charges = []
            for row in self.get('payable_charges') or []:
                if not row.get('charge_code'):
                    if flt(row.get('amount')):
                        frappe.throw(
                            f'Payable Charges row {row.idx}: choose a Charge Code before entering an amount.'
                        )
                    continue
                charges.append(row)
            self.set('payable_charges', charges)
            for idx, row in enumerate(charges, 1):
                row.idx = idx
        self._reopen_legacy_interest_only_loan()
        super().validate()

    def on_submit(self):
        super().on_submit()
        self._reopen_legacy_interest_only_loan()

    def on_cancel(self):
        super().on_cancel()
        subtype = self._generated_waiver_subtype()
        if subtype:
            for name in frappe.get_all(
                "Loan Demand", filters={
                    "loan": self.against_loan, "loan_repayment": self.name,
                    "docstatus": 1, "demand_subtype": subtype,
                }, pluck="name",
            ):
                frappe.get_doc("Loan Demand", name).cancel()
        self._reopen_legacy_interest_only_loan()

    def book_interest_accrued_not_demanded(self):
        super().book_interest_accrued_not_demanded()
        subtype = self._generated_waiver_subtype()
        if not subtype:
            return
        for demand in frappe.get_all(
            "Loan Demand", filters={
                "loan": self.against_loan, "loan_repayment": self.name,
                "docstatus": 1, "demand_subtype": subtype,
            }, fields=["name", "paid_amount", "waived_amount"],
        ):
            if flt(demand.paid_amount) > 0:
                frappe.db.set_value("Loan Demand", demand.name, {
                    "paid_amount": 0,
                    "waived_amount": flt(demand.waived_amount) + flt(demand.paid_amount),
                }, update_modified=False)

    def _generated_waiver_subtype(self):
        subtype = {"Interest Waiver": "Interest", "Penalty Waiver": "Penalty"}.get(self.repayment_type)
        if not subtype:
            return None
        from dcr.api.floorplan_accrual import floorplan_loan

        return subtype if floorplan_loan(self.against_loan) else None

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

    def _reopen_legacy_interest_only_loan(self):
        """Repair loans closed by the old interest-only auto-close behavior."""
        if self.repayment_type in (
            "Full Settlement",
            "Write Off Settlement",
            "Write Off Recovery",
        ):
            return

        loan = frappe.db.get_value(
            "Loan",
            self.against_loan,
            [
                "status",
                "loan_amount",
                "total_principal_paid",
                "loan_product",
                "repayment_schedule_type",
            ],
            as_dict=True,
        )
        if not loan or loan.get("status") != "Closed":
            return

        write_off_amount = frappe.get_cached_value(
            "Loan Product",
            loan.get("loan_product"),
            "write_off_amount",
        )
        precision = cint(frappe.db.get_default("currency_precision")) or 2
        if not has_material_outstanding_principal(
            loan_amount=flt(loan.get("loan_amount")),
            total_principal_paid=flt(loan.get("total_principal_paid")),
            write_off_amount=flt(write_off_amount),
            precision=precision,
        ):
            return

        status = (
            "Active"
            if loan.get("repayment_schedule_type") == "Line of Credit"
            else "Disbursed"
        )
        frappe.db.set_value(
            "Loan",
            self.against_loan,
            {"status": status, "closure_date": None},
        )
