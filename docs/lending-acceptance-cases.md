# DCR lending acceptance cases

These worked cases turn the remaining pilot lending decisions into checks for the schedule, accrual, demands, payoff, and closure. They are illustrative fixtures, not live loans. The invoice basis, day-count convention, interest start date, and schedule-end behavior still need confirmation before changing production calculations.

## Curtailment boundary

Use an original factory invoice and starting principal of $220,000, an annual rate of 12%, and exactly 30 charged days per example period on the agreed 360-day denominator. Assume each payment clears at period end, with no other payments or fees. These equal invoice/principal inputs let us check the confirmed fixed 1% rule without deciding how fees affect its basis.

| Payment | Opening principal | Interest | Principal reduction | Total payment | Closing principal |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12 | $220,000.00 | $2,200.00 | $0.00 | $2,200.00 | $220,000.00 |
| 13 | $220,000.00 | $2,200.00 | $2,200.00 | $4,400.00 | $217,800.00 |
| 14 | $217,800.00 | $2,178.00 | $2,200.00 | $4,378.00 | $215,600.00 |

The principal reduction stays fixed while interest falls. Also exercise a balance smaller than $2,200: the final reduction must stop at the remaining principal, without creating a negative balance. A recalculated schedule must retain the original approved basis rather than silently resetting it to the reduced balance.

For the separate fee case, use a $220,000 factory invoice and $225,000 starting principal. The 1% reduction is either $2,200 or $2,250 depending on the pending basis decision. Do not select an expected result until that decision is recorded. Trace the approved amount from its authoritative document through loan creation and later schedule updates.

## Dated interest

At the same principal and rate, interest is $73.333333 per charged day before final rounding. A 28-charged-day period produces $2,053.33; 30 charged days produce $2,200.00. Use February 1 to March 1, 2027 as a non-leap-year example to expose the convention choice rather than silently treating every month as 30 days.

Agree expected results for February, a partial month, and which endpoint days are included. Test a principal reduction during a period, using the balance applicable to each date. Then compare the schedule forecast, actual accrual, demands, and payoff under the same approved convention.

For a late invoice, record shipment, invoice, and funding dates separately. Agree which date starts interest and check a delayed entry against that date. An offline-date estimate is not automatically an interest-start date.

## Early payoff and closure

After the example's payment 14, remaining principal is $215,600. If all interest through that payment is paid, a later payoff should use that remaining principal, unpaid interest accrued to the approved payoff date, and applicable charges. Future forecast interest must not become a payoff charge merely because it appears in a schedule total.

Reconcile the quoted payoff with native Lending balances, repayment allocation, and the resulting closure state. Check partial payments, unpaid demands, overpayment, and rounding residuals. Determine whether Dealer Flooring Loan Payoff is intended as a payoff quote or a settlement summary before changing its print calculations.

## Horizon and final invoice

A 36-period forecast with 12 interest-only periods and 24 fixed $2,200 reductions leaves $167,200 principal. Confirm whether the horizon should extend, leave a balance, or trigger a contractual balloon. A forecast's last row alone does not decide that rule.

Use a quote that differs from the final invoice. Verify the approved invoice amount reaches actual loan principal and funding, reconcile qualifying_amount with loan_amount on the installed Lending version, and confirm whether the changed amount requires a revised signed packet.

## Evidence required

For each approved case, retain the expected amounts and dates, source document references, actual schedule rows, accruals, demands, repayment allocations, and final loan status. Run accounting cases only in the agreed trial environment and under its approved reconciliation procedure. Local mocked tests and a correct PDF are separate from hosted accounting verification.
