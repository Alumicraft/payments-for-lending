# DCR lending acceptance cases

These worked cases turn the remaining pilot lending decisions into checks for the schedule, accrual, demands, payoff, and closure. They are illustrative fixtures, not live loans. The owner now confirms the financed purchase invoice total including freight and DCR fees, Actual/360 from invoice date, and continuing monthly payments past 36 months. Changed invoice amounts require a revised packet. Source math and hosted postings are separate acceptance gates.

## Curtailment boundary

Use an original factory invoice and starting principal of $220,000, an annual rate of 12%, and exactly 30 charged days per example period on the agreed 360-day denominator. Assume each payment clears at period end, with no other payments or fees. These equal financed invoice/principal inputs check the fixed 1% rule; the 30-day examples below isolate curtailment from calendar variation.

| Payment | Opening principal | Interest | Principal reduction | Total payment | Closing principal |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12 | $220,000.00 | $2,200.00 | $0.00 | $2,200.00 | $220,000.00 |
| 13 | $220,000.00 | $2,200.00 | $2,200.00 | $4,400.00 | $217,800.00 |
| 14 | $217,800.00 | $2,178.00 | $2,200.00 | $4,378.00 | $215,600.00 |

The principal reduction stays fixed while interest falls. Also exercise a balance smaller than $2,200: the final reduction must stop at the remaining principal, without creating a negative balance. A recalculated schedule must retain the original approved basis rather than silently resetting it to the reduced balance.

For the separate fee case, use a $220,000 factory invoice and $225,000 starting principal. The owner-approved 1% reduction is $2,250 because financed fees are included in the original basis. Trace the approved amount from its authoritative document through loan creation and later schedule updates.

## Dated interest

At the same principal and rate, interest is $73.333333 per charged day before final rounding. A 28-charged-day period produces $2,053.33; 30 charged days produce $2,200.00. Use February 1 to March 1, 2027 as a non-leap-year example to expose the convention choice rather than silently treating every month as 30 days.

Count interest from the invoice/period start through the day before payment, so consecutive periods do not overlap. Expected values: February 2027 has 28 days; February 2028 has 29; January 20–February 1 has 12. Test a principal reduction during a period, using the balance applicable to each date. Then compare the schedule forecast, actual accrual, demands, and payoff under the same approved convention.

For a late invoice, record shipment, invoice, and funding dates separately. Interest starts at invoice date, understood as funding/set-aside date; check delayed entry and later factory remittance against that date. An offline-date estimate is not automatically an interest-start date.

## Early payoff and closure

After the example's payment 14, remaining principal is $215,600. If all interest through that payment is paid, a later payoff should use that remaining principal, unpaid interest accrued to the approved payoff date, and applicable charges. Future forecast interest must not become a payoff charge merely because it appears in a schedule total.

Reconcile the quoted payoff with native Lending balances, repayment allocation, and the resulting closure state. Check partial payments, unpaid demands, overpayment, and rounding residuals. Determine whether Dealer Flooring Loan Payoff is intended as a payoff quote or a settlement summary before changing its print calculations.

## Horizon and final invoice

A 36-period forecast with 12 interest-only periods and 24 fixed $2,200 reductions leaves $167,200 principal. The agreed rule extends monthly payments beyond month 36, with no horizon-driven balloon. A forecast's last row alone does not decide that rule.

Use a quote that differs from the final invoice. Verify the approved invoice amount reaches actual loan principal and funding, reconcile qualifying_amount with loan_amount on the installed Lending version, and require a revised signed packet when the final amount changes.

## Evidence required

For each approved case, retain the expected amounts and dates, source document references, actual schedule rows, accruals, demands, repayment allocations, and final loan status. Run accounting cases only in the agreed trial environment and under its approved reconciliation procedure. Local mocked tests and a correct PDF are separate from hosted accounting verification.

## Current schedule regression evidence

A financed total of $225,000 at 12%, invoiced January 1, 2026 with first payment February 1, gives 112 monthly rows: 12 interest-only, then 100 fixed $2,250 reductions. Payment 12 (January 1, 2027) has $2,325 interest; payment 13 (February 1) has $2,325 interest plus $2,250 principal; payment 14 (March 1) has $2,079 interest plus $2,250 principal. Closing principal at 36 is $171,000, at 112 zero. Actual month lengths mean total payments can vary even as principal falls.

Local tests cover these amounts, leap/non-leap February, a partial first period, month-end anchoring, a final smaller reduction, zero outstanding principal, one-time carried interest, and the installed v16 argument shape retaining copied rows. Hosted accrual/demand/repayment reconciliation, original financed-invoice sourcing and restructure carry-forward remain open.
