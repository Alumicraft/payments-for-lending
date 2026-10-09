"""Read the same configured floorplan terms for reviews and schedules."""
import math
import frappe


def product_terms(loan_product, fallback_rate=0):
    def first(*names):
        if not loan_product:
            return None
        for field in names:
            try:
                available = frappe.db.has_column('Loan Product',field)
            except Exception:
                available = frappe.get_meta('Loan Product').has_field(field)
            if available:
                value = frappe.db.get_value('Loan Product',loan_product,field)
                if value not in (None,''):
                    return value
        return None

    schedule_type = first('custom_schedule_type') if loan_product else 'Interest Only Then Percent Principal'
    if schedule_type != 'Interest Only Then Percent Principal':
        return dict(schedule_type=schedule_type)
    contract = first('custom_contract_interest_rate','custom_rate_of_interest')
    rate = float(contract) if contract is not None and float(contract) > 0 else float(fallback_rate or 0)
    periods = first('custom_interest_only_months','custom_interest_only_periods')
    percent = first('custom_monthly_principal_pct','custom_monthly_principal_percent')
    periods = float(12 if periods is None else periods)
    percent = float(1 if percent is None else percent)
    if (not all(math.isfinite(value) for value in (rate,periods,percent)) or
            rate < 0 or periods < 0 or not periods.is_integer() or percent <= 0 or percent > 100):
        frappe.throw('Invalid floorplan product interest, interest-only periods or principal percentage.')
    return dict(annual_rate=rate,interest_only_periods=int(periods),monthly_principal_percent=percent,
                day_count='Actual/360',
                schedule_type=schedule_type)
