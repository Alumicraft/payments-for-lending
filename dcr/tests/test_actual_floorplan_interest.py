from decimal import Decimal

from dcr.lending_rules import elapsed_floorplan_interest, principal_on_day


EVENTS = [('2026-10-01', 225000), ('2027-11-01', -2250), ('2027-12-01', -2250)]


def test_payoff_after_curtailment_uses_posted_balance_and_excludes_payoff_day():
    assert elapsed_floorplan_interest(EVENTS, '2027-12-01', '2028-01-15', 12) == Decimal('3307.50')
    assert principal_on_day(EVENTS, '2028-01-01') == Decimal('220500')


def test_unpaid_scheduled_principal_never_reduces_accrual():
    assert elapsed_floorplan_interest([EVENTS[0]], '2027-11-01', '2027-12-01', 12) == Decimal('2250.00')


def test_partial_month_february_and_funding_day():
    assert elapsed_floorplan_interest(EVENTS, '2026-10-01', '2026-10-11', 12) == Decimal('750.00')
    assert elapsed_floorplan_interest(EVENTS, '2027-02-01', '2027-03-01', 12) == Decimal('2100.00')
    assert elapsed_floorplan_interest(EVENTS, '2026-10-01', '2026-10-01', 12) == 0


def test_daily_rounding_and_same_day_receipt():
    assert elapsed_floorplan_interest([('2026-01-01', 100), ('2026-01-02', -50)],
                                     '2026-01-01', '2026-01-03', 12) == Decimal('0.05')
