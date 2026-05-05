"""Custom repayment schedule controller overrides for DCR floor-plan loans."""

from __future__ import annotations

import inspect

import frappe
from frappe.utils import add_months, flt
from lending.loan_management.doctype.loan_repayment_schedule.loan_repayment_schedule import (
    LoanRepaymentSchedule,
)


class CustomLoanRepaymentSchedule(LoanRepaymentSchedule):
    """Inject DCR repayment pattern for configured loan products.

    Pattern:
    - Interest-only for first N periods.
    - Then interest + principal as fixed % of outstanding balance.
    """

    def make_repayment_schedule(self, schedule_field="repayment_schedule", *args, **kwargs):
        if not self.is_dcr_floorplan_structure():
            return super().make_repayment_schedule(schedule_field, *args, **kwargs)

        self.set(schedule_field, [])
        self.make_dcr_repayment_schedule(schedule_field)

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

    def make_dcr_repayment_schedule(self, schedule_field: str) -> None:
        principal = flt(getattr(self, "current_principal_amount", None) or self.loan_amount)
        monthly_rate = self.get_contract_interest_rate() / 1200
        interest_only_months = int(
            flt(
                self.get_loan_product_value(
                    "custom_interest_only_months", "custom_interest_only_periods"
                )
            )
            or 12
        )
        monthly_principal_pct = flt(
            self.get_loan_product_value(
                "custom_monthly_principal_pct", "custom_monthly_principal_percent"
            )
        ) or 1

        payment_date = self.repayment_start_date
        max_periods = int(self.repayment_periods or 0)

        for period in range(1, max_periods + 1):
            interest_amount = flt(principal * monthly_rate, 2)
            principal_amount = 0.0

            if period > interest_only_months:
                principal_amount = flt(principal * (monthly_principal_pct / 100), 2)
                principal_amount = min(principal_amount, principal)

            total_payment = flt(interest_amount + principal_amount, 2)
            balance_loan_amount = flt(principal - principal_amount, 2)

            self._add_schedule_row(
                schedule_field=schedule_field,
                payment_date=payment_date,
                principal_amount=principal_amount,
                interest_amount=interest_amount,
                total_payment=total_payment,
                balance_loan_amount=balance_loan_amount,
                days=30,
            )

            principal = balance_loan_amount
            if principal <= 0:
                break

            payment_date = self.get_next_payment_date(payment_date) if hasattr(
                self, "get_next_payment_date"
            ) else add_months(payment_date, 1)

        self.repayment_periods = len(self.get(schedule_field) or [])
        if self.get(schedule_field):
            self.monthly_repayment_amount = self.get(schedule_field)[0].total_payment

    def _add_schedule_row(self, **row_data):
        """Call core helper with compatible args, or append directly as fallback."""
        add_row = getattr(self, "add_repayment_schedule_row", None)
        if callable(add_row):
            params = inspect.signature(add_row).parameters
            kwargs = {
                name: value
                for name, value in row_data.items()
                if name in params
            }
            if "demand_generated" in params and "demand_generated" not in kwargs:
                kwargs["demand_generated"] = 0
            if "is_accrued" in params and "is_accrued" not in kwargs:
                kwargs["is_accrued"] = 0
            return add_row(**kwargs)

        self.append(
            row_data["schedule_field"],
            {
                "payment_date": row_data["payment_date"],
                "principal_amount": row_data["principal_amount"],
                "interest_amount": row_data["interest_amount"],
                "total_payment": row_data["total_payment"],
                "balance_loan_amount": row_data["balance_loan_amount"],
            },
        )
