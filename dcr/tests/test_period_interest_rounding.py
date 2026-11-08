from datetime import date, timedelta
from decimal import Decimal

from dcr.lending_rules import elapsed_floorplan_interest, floorplan_interval_interest


def test_first_invoice_period_rounds_once():
    events = [('2026-10-11', 265000)]
    assert elapsed_floorplan_interest(events, '2026-10-11', '2026-11-01', 12) == Decimal('1855.00')


def test_exact_half_cent_rounds_up_after_accumulating_the_period():
    assert elapsed_floorplan_interest([('2026-01-01', 15)], '2026-01-01', '2026-01-04', 12) == Decimal('0.02')


def test_daily_accruals_sum_to_the_same_mid_period_principal_change_quote():
    events = [('2026-11-01', 225000), ('2027-12-01', -2250),
              ('2028-01-01', -2250), ('2028-01-15', -5000)]
    start = date(2028, 1, 1)
    amounts = [floorplan_interval_interest(events, '2026-12-01', start+timedelta(days=i),
                                          start+timedelta(days=i+1), 12) for i in range(31)]
    assert sum(amounts) == Decimal('2250.17')
    assert amounts[14:17] == [Decimal('71.83'), Decimal('71.84'), Decimal('71.83')]
    assert floorplan_interval_interest(events, '2026-12-01', '2028-01-17', '2028-02-01', 12) == Decimal('1077.50')


def test_period_boundary_resets_rounding_and_month_end_anchor_does_not_drift():
    events = [('2026-01-01', 100)]
    assert floorplan_interval_interest(events, '2026-01-31', '2026-02-01', '2026-03-01', 12) == Decimal('0.93')
    assert floorplan_interval_interest(events, '2026-01-31', '2026-02-28', '2026-03-31', 12) == Decimal('1.03')


def test_sub_cent_daily_interest_is_collected_without_losing_or_duplicating_cents():
    events = [('2026-01-01', 1)]
    start = date(2026, 1, 1)
    daily = [floorplan_interval_interest(events, '2026-02-01', start+timedelta(days=i),
                                        start+timedelta(days=i+1), 12) for i in range(31)]
    assert sum(daily) == Decimal('0.01')
    assert all(value in (Decimal('0.00'), Decimal('0.01')) for value in daily)
