"""Custom repayment schedule controller overrides for DCR floor-plan loans."""

from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate
from dcr.lending_rules import floorplan_schedule
from lending.loan_management.doctype.loan_repayment_schedule import loan_repayment_schedule as native_schedule
from lending.loan_management.doctype.loan_repayment_schedule.loan_repayment_schedule import (
    LoanRepaymentSchedule,
)


class CustomLoanRepaymentSchedule(LoanRepaymentSchedule):
    """Inject DCR repayment pattern for configured loan products.

    Pattern:
    - Interest-only for first N periods.
    - Then dated interest + principal as a fixed % of original financed principal.
    """

    def add_rows_from_prev_disbursement(
        self, schedule_field, principal_share_percentage, interest_share_percentage=100
    ):
        # Adapted from Lending 97f692e (Frappe Technologies, GPL-3.0).
        # Own this method for DCR: upstream hardcodes Actual/365. Native
        # adjustments/demand flags are preserved, while dated interest is /360.
        if not self.is_dcr_floorplan_structure():
            return super().add_rows_from_prev_disbursement(
                schedule_field, principal_share_percentage, interest_share_percentage
            )
        self._dcr_prior_periods = None
        if self.restructure_type == "Normal Restructure":
            previous = frappe.get_doc("Loan Repayment Schedule", {
                "loan": self.loan, "docstatus": 1, "status": "Active"
            })
            # Normal restructure already supplies unpaid interest through
            # adjusted_interest. Retain the payment phase without adding that
            # interest again or restarting twelve interest-only installments.
            self._dcr_prior_periods = sum(
                getdate(row.payment_date) <= getdate(self.posting_date)
                for row in previous.get(schedule_field)
            )
            return 0, self.current_principal_amount, 0, 0
        previous_interest_amount = 0
        completed_tenure = 0
        balance_principal_amount = self.current_principal_amount
        additional_principal_amount = 0
        pending_prev_days = 0

        loan_status = frappe.db.get_value("Loan", self.loan, "status")
        if (
            (loan_status == "Partially Disbursed" and self.repayment_schedule_type != "Line of Credit")
            or self.restructure_type in ("Advance Payment", "Pre Payment")
            and self.repayment_frequency != "One Time"
        ):
            filters = {"loan": self.loan, "docstatus": 1, "status": "Active"}

            if self.loan_disbursement and self.repayment_schedule_type == "Line of Credit":
                filters["loan_disbursement"] = self.loan_disbursement

            prev_schedule = frappe.get_doc("Loan Repayment Schedule", filters)

            self.total_installments_raised = prev_schedule.total_installments_raised
            self.total_installments_paid = prev_schedule.total_installments_paid
            self.total_installments_overdue = prev_schedule.total_installments_overdue

            if prev_schedule:
                if self.restructure_type:
                    self.loan_disbursement = prev_schedule.loan_disbursement

                prev_repayment_date = prev_schedule.posting_date
                prev_balance_amount = prev_schedule.current_principal_amount
                if self.restructure_type != "Advance Payment":
                    self.monthly_repayment_amount = prev_schedule.monthly_repayment_amount
                first_date = prev_schedule.get(schedule_field)[0].payment_date
                previous_broken_period_interest = prev_schedule.broken_period_interest

                if (
                    getdate(self.repayment_start_date) > getdate(prev_schedule.repayment_start_date)
                    or getdate(first_date) < prev_schedule.repayment_start_date
                ):
                    for row in prev_schedule.get(schedule_field):
                        if getdate(row.payment_date) < getdate(self.posting_date) or (
                            getdate(row.payment_date) == getdate(self.posting_date) and self.restructure_type in (
                                "Pre Payment",
                                "Advance Payment",
                            )
                        ):
                            self.add_repayment_schedule_row(
                                row.payment_date,
                                row.principal_amount,
                                row.interest_amount,
                                0,
                                row.total_payment,
                                row.balance_loan_amount,
                                row.number_of_days,
                                demand_generated=row.demand_generated,
                                repayment_schedule_field=schedule_field,
                            )
                            prev_repayment_date = row.payment_date
                            prev_balance_amount = row.balance_loan_amount
                            if row.principal_amount:
                                completed_tenure += 1
                        elif getdate(self.posting_date) > row.payment_date:
                            self.repayment_start_date = row.payment_date
                            prev_repayment_date = row.payment_date
                            break

                    if (
                        self.moratorium_end_date
                        and getdate(self.posting_date) <= getdate(self.moratorium_end_date)
                        and self.restructure_type
                    ):
                        self.monthly_repayment_amount = native_schedule.get_monthly_repayment_amount(
                            self.current_principal_amount,
                            self.rate_of_interest,
                            self.repayment_periods,
                            self.repayment_frequency,
                        )
                        return (
                            previous_interest_amount,
                            self.current_principal_amount,
                            additional_principal_amount,
                            pending_prev_days,
                        )

                    if not self.restructure_type:
                        self.broken_period_interest = prev_schedule.broken_period_interest

                    pending_prev_days = date_diff(self.posting_date, prev_repayment_date)

                    if pending_prev_days > 0:
                        previous_interest_amount += flt(
                            prev_balance_amount * self.get_contract_interest_rate() * pending_prev_days / (36000)
                        )
                else:
                    prev_balance_amount = prev_schedule.current_principal_amount
                    # A second funding before the first due date splits the
                    # period at this posting date. Carry only elapsed interest
                    # on the old balance, then forecast the combined balance.
                    self.repayment_start_date = prev_schedule.repayment_start_date
                    pending_prev_days = max(0, date_diff(self.posting_date, prev_schedule.posting_date))
                    previous_interest_amount = flt(
                        prev_balance_amount * self.get_contract_interest_rate() * pending_prev_days / 36000
                    )
                    additional_principal_amount = self.disbursed_amount

                if self.restructure_type == "Advance Payment":
                    adjusted_unaccrued_interest = frappe.db.get_value(
                        "Loan Restructure", self.loan_restructure, "adjusted_unaccrued_interest"
                    )

                    interest_amount = adjusted_unaccrued_interest

                    paid_principal_amount = self.monthly_repayment_amount - interest_amount
                    total_payment = paid_principal_amount + interest_amount
                    balance_principal_amount = self.current_principal_amount
                    previous_interest_amount = 0

                    if (
                        self.repayment_schedule_type == "Monthly as per cycle date"
                        and self.repayment_frequency == "Monthly"
                        and getdate(self.posting_date) < getdate(first_date)
                    ):
                        if not previous_broken_period_interest:
                            ignore_bpi = True
                        else:
                            ignore_bpi = False

                        next_emi_date = native_schedule.get_cyclic_date(
                            self.loan_product, prev_repayment_date, ignore_bpi=ignore_bpi
                        )
                    else:
                        next_emi_date = self.get_next_payment_date(prev_repayment_date)

                    self.repayment_start_date = frappe.db.get_value(
                        "Loan Restructure", self.loan_restructure, "repayment_start_date"
                    )
                    self.add_repayment_schedule_row(
                        next_emi_date,
                        paid_principal_amount,
                        interest_amount,
                        0,
                        total_payment,
                        balance_principal_amount,
                        pending_prev_days,
                        0,
                        repayment_schedule_field=schedule_field,
                        principal_share_percentage=principal_share_percentage,
                        interest_share_percentage=interest_share_percentage,
                    )

                    pending_prev_days = date_diff(next_emi_date, self.posting_date)

                    if pending_prev_days > 0:
                        previous_interest_amount += flt(
                            balance_principal_amount * self.get_contract_interest_rate() * pending_prev_days / (36000)
                        )

                    self.repayment_start_date = self.get_next_payment_date(next_emi_date)

                    completed_tenure += 1
                elif not self.restructure_type:
                    self.current_principal_amount = self.disbursed_amount + prev_balance_amount
                    balance_principal_amount = self.current_principal_amount

                if self.repayment_method == "Repay Over Number of Periods" and not self.restructure_type:
                    self.monthly_repayment_amount = native_schedule.get_monthly_repayment_amount(
                        balance_principal_amount,
                        self.rate_of_interest,
                        self.repayment_periods - completed_tenure,
                        self.repayment_frequency,
                    )

                if self.restructure_type == "Pre Payment" and self.repayment_frequency != "One Time":
                    interest_amount = 0
                    principal_amount = 0

                    # Pre payment made even before the first EMI
                    if getdate(self.posting_date) < getdate(first_date):
                        next_emi_date = native_schedule.get_cyclic_date(self.loan_product, self.posting_date, ignore_bpi=True)
                    else:
                        next_emi_date = self.get_next_payment_date(prev_repayment_date)

                    pending_prev_days = date_diff(next_emi_date, self.posting_date)

                    if pending_prev_days > 0:
                        interest_amount = flt(
                            self.current_principal_amount * self.get_contract_interest_rate() * pending_prev_days / (36000)
                        )

                        unaccrued_interest, adjusted_unaccrued_interest = frappe.db.get_value(
                            "Loan Restructure",
                            self.loan_restructure,
                            ["unaccrued_interest", "adjusted_unaccrued_interest"],
                        )

                        if adjusted_unaccrued_interest and adjusted_unaccrued_interest < unaccrued_interest:
                            previous_interest_amount = unaccrued_interest - adjusted_unaccrued_interest
                            interest_amount += previous_interest_amount

                    # This future due is still a regular DCR installment:
                    # zero principal during IO, then fixed original-basis 1%.
                    principal_amount = self.get_floorplan_principal_reduction(
                        len(self.get(schedule_field) or []), self.current_principal_amount
                    )

                    total_payment = principal_amount + interest_amount

                    balance_principal_amount = self.current_principal_amount - principal_amount
                    # A prior restructure (e.g. Advance Payment) may have already marked this same
                    # next_emi_date as demand_generated=1 on prev_schedule, meaning that EMI was
                    # already skipped and does not need a fresh demand. Carry that flag forward
                    # here instead of always starting at 0, otherwise this Pre Payment rebuild
                    # undoes the earlier skip and the EMI wrongly shows up as due again.
                    self.add_repayment_schedule_row(
                        next_emi_date,
                        principal_amount,
                        interest_amount,
                        0,
                        total_payment,
                        balance_principal_amount,
                        pending_prev_days,
                        self.get_prev_schedule_demand_generated(prev_schedule, schedule_field, next_emi_date),
                        repayment_schedule_field=schedule_field,
                        principal_share_percentage=principal_share_percentage,
                        interest_share_percentage=interest_share_percentage,
                    )

                    pending_prev_days = 0
                    previous_interest_amount = 0
                    additional_principal_amount = 0
                    self.repayment_start_date = self.get_next_payment_date(next_emi_date)

        return (
            previous_interest_amount,
            balance_principal_amount,
            additional_principal_amount,
            pending_prev_days,
        )


    def get_floorplan_principal_reduction(self, prior_periods, balance):
        interest_only = self.get_loan_product_value("custom_interest_only_months", "custom_interest_only_periods")
        if prior_periods < int(flt(12 if interest_only is None else interest_only)):
            return 0
        percent = self.get_loan_product_value("custom_monthly_principal_pct", "custom_monthly_principal_percent")
        original = flt(frappe.db.get_value("Loan", self.loan, "loan_amount")) or flt(self.loan_amount)
        return min(flt(balance), flt(original * flt(1 if percent is None else percent) / 100, 2))

    def make_repayment_schedule(self, schedule_field="repayment_schedule", *args, **kwargs):
        if not self.is_dcr_floorplan_structure():
            return super().make_repayment_schedule(schedule_field, *args, **kwargs)

        # The installed v16 caller has already reset this table and may have
        # copied prior rows. Keep those rows and consume its actual arguments.
        names = ("previous_interest_amount", "balance_amount", "additional_principal_amount",
                 "pending_prev_days", "rate_of_interest", "principal_share_percentage",
                 "interest_share_percentage", "partner_schedule_type")
        values = dict(zip(names, args))
        values.update(kwargs)
        self.make_dcr_repayment_schedule(schedule_field, **values)

    def is_dcr_floorplan_structure(self) -> bool:
        if not getattr(self, "loan_product", None):
            return False

        return self.get_dcr_schedule_type() == "Interest Only Then Percent Principal"

    def get_dcr_schedule_type(self) -> str | None:
        return frappe.db.get_value("Loan Product", self.loan_product, "custom_schedule_type")

    def get_loan_product_value(self, *fieldnames):
        """Return the first populated Loan Product field from the provided names."""
        for fieldname in fieldnames:
            if not self._loan_product_has_field(fieldname):
                continue
            value = frappe.db.get_value("Loan Product", self.loan_product, fieldname)
            if value not in (None, ""):
                return value
        return None

    def _loan_product_has_field(self, fieldname):
        try:
            return bool(frappe.db.has_column("Loan Product", fieldname))
        except Exception:
            return bool(frappe.get_meta("Loan Product").has_field(fieldname))

    def get_contract_interest_rate(self) -> float:
        """Use product-specific contract rate when configured, else loan rate."""
        val = self.get_loan_product_value(
            "custom_contract_interest_rate", "custom_rate_of_interest"
        )
        if flt(val) > 0:
            return flt(val)
        return flt(self.rate_of_interest)

    def get_default_interest_rate(self) -> float:
        """Expose default-rate config (used by downstream delinquency/default logic)."""
        product_default_rate = self.get_loan_product_value("custom_default_interest_rate")
        return flt(product_default_rate) if product_default_rate is not None else 0.0

    def make_dcr_repayment_schedule(self, schedule_field: str, **native_values) -> None:
        original = flt(self.loan_amount)
        if getattr(self, "loan", None):
            original = flt(frappe.db.get_value("Loan", self.loan, "loan_amount")) or original
        principal = native_values.get("balance_amount")
        if principal is None:
            principal = getattr(self, "current_principal_amount", None)
        if principal is None:
            principal = original
        existing = self.get(schedule_field) or []
        prior_periods = getattr(self, "_dcr_prior_periods", None)
        if prior_periods is None:
            prior_periods = len(existing)
        one_time = getattr(self, "repayment_frequency", None) == "One Time"
        if schedule_field == "colender_schedule" and native_values.get("partner_schedule_type") == "EMI (PMT) based":
            full_balance = flt(getattr(self, "current_principal_amount", 0))
            if full_balance > 0:
                original *= flt(principal) / full_balance
        rate = native_values.get("rate_of_interest") if schedule_field == "colender_schedule" else None
        if rate is None:
            rate = self.get_contract_interest_rate()
        start = getattr(self, "posting_date", None)
        if not start:
            frappe.throw("Invoice/funding date is required to calculate floorplan interest")
        # A native pre/advance-payment carry can append the next due row.
        # Future interest starts there, not again at the restructure posting date.
        if existing and getdate(existing[-1].payment_date) > getdate(start):
            start = existing[-1].payment_date
        interest_only = self.get_loan_product_value("custom_interest_only_months", "custom_interest_only_periods")
        principal_percent = self.get_loan_product_value("custom_monthly_principal_pct", "custom_monthly_principal_percent")
        try:
            rows = floorplan_schedule(
                original_principal=flt(principal) if one_time else original,
                outstanding_principal=flt(principal), annual_rate=rate,
                interest_start_date=start, first_payment_date=self.repayment_start_date,
                prior_periods=prior_periods,
                interest_only_periods=0 if one_time else int(flt(12 if interest_only is None else interest_only)),
                monthly_principal_percent=100 if one_time else flt(1 if principal_percent is None else principal_percent),
                carried_interest=flt(native_values.get("previous_interest_amount")) +
                    flt(getattr(self, "adjusted_interest", 0)),
            )
        except ValueError as error:
            frappe.throw(str(error))
        for row in rows:
            principal_share = flt(native_values.get("principal_share_percentage", 100)) / 100
            interest_share = flt(native_values.get("interest_share_percentage", 100)) / 100
            row["principal_amount"] = flt(row["principal_amount"] * principal_share, 2)
            row["interest_amount"] = flt(row["interest_amount"] * interest_share, 2)
            row["total_payment"] = flt(row["principal_amount"] + row["interest_amount"], 2)
            self._add_schedule_row(schedule_field=schedule_field, **row)
        if schedule_field == "repayment_schedule":
            self.repayment_periods = len(self.get(schedule_field) or [])
            self.monthly_repayment_amount = rows[0]["total_payment"] if rows else 0
        elif self.get(schedule_field):
            self.partner_monthly_repayment_amount = self.get(schedule_field)[0].total_payment

    def _add_schedule_row(self, **row_data):
        """Append the DCR-owned row shape directly.

        The upstream helper signature has changed across Lending releases; this
        custom schedule only needs the core child-table fields below.
        """
        if row_data["schedule_field"] != "colender_schedule":
            self.number_of_rows = (getattr(self, "number_of_rows", 0) or 0) + 1
        self.append(
            row_data["schedule_field"],
            {
                "payment_date": row_data["payment_date"],
                "principal_amount": row_data["principal_amount"],
                "interest_amount": row_data["interest_amount"],
                "total_payment": row_data["total_payment"],
                "balance_loan_amount": row_data["balance_loan_amount"],
                "number_of_days": row_data.get("number_of_days", row_data.get("days", 0)),
            },
        )
