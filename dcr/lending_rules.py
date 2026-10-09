"""Pure business rules shared by DCR Lending overrides."""


def has_material_outstanding_principal(
    loan_amount,
    total_principal_paid,
    current_principal_paid=0,
    write_off_amount=0,
    precision=2,
):
    """Return whether principal remains above the configured write-off limit."""
    remaining = round(
        float(loan_amount or 0)
        - float(total_principal_paid or 0)
        - float(current_principal_paid or 0),
        precision,
    )
    return remaining > float(write_off_amount or 0)


def floorplan_schedule(*, original_principal, outstanding_principal, annual_rate,
                       interest_start_date, first_payment_date, prior_periods=0,
                       interest_only_periods=12, monthly_principal_percent=1,
                       carried_interest=0):
    """Forecast actual/360 interest and fixed original-basis monthly principal.

    Interest covers [period start, payment date): invoice/funding day is charged,
    the payment day belongs to the next period. Continue past a display horizon
    until principal is paid; the last reduction is capped at the unpaid balance.
    """
    from calendar import monthrange
    from datetime import date
    from decimal import Decimal, ROUND_HALF_UP

    def number(value):
        result = Decimal(str(value or 0))
        if not result.is_finite():
            raise ValueError('Schedule amounts must be finite')
        return result

    def money(value):
        return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def day(value):
        return date.fromisoformat(str(value)[:10])

    original = money(number(original_principal))
    balance = money(number(outstanding_principal))
    rate = number(annual_rate)
    percent = number(monthly_principal_percent)
    carried = number(carried_interest)
    start = day(interest_start_date)
    first_due = day(first_payment_date)
    if original <= 0 or balance < 0 or rate < 0 or percent <= 0 or first_due < start:
        raise ValueError('Invalid floorplan schedule amount, rate, or dates')
    reduction = money(original * percent / 100)
    if reduction <= 0:
        raise ValueError('Monthly principal reduction must be at least one cent')
    prior = int(prior_periods)
    interest_only = int(interest_only_periods)
    if prior < 0 or interest_only < 0:
        raise ValueError('Schedule period counts cannot be negative')

    # Calculate from the first due date every time, preventing February from
    # moving subsequent payment dates permanently to the 28th/29th.
    month_end = first_due.day == monthrange(first_due.year, first_due.month)[1]
    result = []
    period = prior
    index = 0
    due = first_due
    while balance > 0:
        period += 1
        days = (due - start).days
        interest = money(balance * rate * days / Decimal(36000) + carried)
        principal = min(reduction, balance) if period > interest_only else Decimal(0)
        balance = money(balance - principal)
        result.append(dict(payment_date=due, principal_amount=float(principal),
                           interest_amount=float(interest), total_payment=float(money(principal + interest)),
                           balance_loan_amount=float(balance), number_of_days=days))
        carried = Decimal(0)
        start = due
        index += 1
        month_index = first_due.year * 12 + first_due.month - 1 + index
        year, month = divmod(month_index, 12)
        month += 1
        last_day = monthrange(year, month)[1]
        due = date(year, month, last_day if month_end else min(first_due.day, last_day))
    return result
