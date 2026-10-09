"""Custom repayment schedule controller overrides for DCR floor-plan loans."""

from __future__ import annotations

import frappe
from frappe.utils import flt
from dcr.lending_rules import floorplan_schedule
from lending.loan_management.doctype.loan_repayment_schedule.loan_repayment_schedule import (
    LoanRepaymentSchedule,
)


class CustomLoanRepaymentSchedule(LoanRepaymentSchedule):
    """Inject DCR repayment pattern for configured loan products.

    Pattern:
    - Interest-only for first N periods.
    - Then dated interest + principal as a fixed % of original financed principal.
    """

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
        interest_only = self.get_loan_product_value("custom_interest_only_months", "custom_interest_only_periods")
        principal_percent = self.get_loan_product_value("custom_monthly_principal_pct", "custom_monthly_principal_percent")
        try:
            rows = floorplan_schedule(
                original_principal=flt(principal) if one_time else original,
                outstanding_principal=flt(principal), annual_rate=rate,
                interest_start_date=start, first_payment_date=self.repayment_start_date,
                prior_periods=len(existing),
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
