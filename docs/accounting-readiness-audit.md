# Accounting readiness audit

Updated October 8, 2026. Status: **not ready; configuration findings and posting reconciliation remain open**. This is part of the pilot checklist, not a certification of the ledger.

## Confirmed configuration

Read from the signed-in Company and Standard Loan Product forms without saving:

| Setting | Observed state | Required follow-up |
| --- | --- | --- |
| Company currency | USD | Reconcile company and account currencies |
| Loan accounting | Enabled | Verify each native voucher posts to the GL |
| Loan GL consolidation | Disabled | Expect individual voucher GL entries |
| Loan accrual frequency | Daily | Verify enabled scheduled jobs and successful recent executions |
| Interest day-count convention | Actual/365 | Conflicts with the agreed 360 denominator; settle elapsed-day convention and effective date before changing it |
| Collection offset sequences | Company has a DCR sequence; product overrides blank | Inspect inherited sequence and actual allocation before treating product blanks as defects |
| Standard product | Term loan; 12% annual interest; 12 interest-only months; 1% monthly principal | Current custom schedule still reduces remaining principal rather than original invoice; invoice basis remains open |
| Principal and interest receivable | Shared loans-receivable account | Reconcile loan-level balances and assess reporting separation |
| Interest accrued and interest income | Same service/fee income account | Correct mapping and assess historical postings |
| Default receivable, expense and cost center | Blank on Company form | Inspect item, customer and voucher-level defaults; determine which flows lack a reliable fallback |

## Accrued-interest mapping finding

The installed Lending commit is `97f692e908e92b3ce6737ab08c3ff9cb3cdcca44`. Its [Loan Interest Accrual controller](https://github.com/frappe/lending/blob/97f692e908e92b3ce6737ab08c3ff9cb3cdcca44/lending/loan_management/doctype/loan_interest_accrual/loan_interest_accrual.py) uses `interest_accrued_account` as the debit and `interest_income_account` as the credit for normal interest. Because both live mappings are the same account, this produces no net accrued-interest asset or income at accrual time. The live company enables accounting and disables consolidation, so the configuration is incompatible with recognizing accrued interest through that normal posting path.

The General Ledger report was then inspected for September 8 through October 8, 2026. One normal-interest accrual voucher was isolated using Voucher No and Reload Report: its debit and credit both hit the service/fee income account, with zero net balance. This confirms the issue affects a posted voucher, not just configuration. The unfiltered report also shows interest demands debiting loans receivable and crediting service/fee income. The complete historical extent, cutoff impact and repayment allocation remain unverified; trace these before prescribing reversals or reposting. Financial amounts and raw captures are retained locally outside the public repository.

PR #37, installed as `13d3efd`, removes the legacy setup fallback that assigned missing or receivable-type accrual mappings to the service/fee income account. The deployed fix preserves all accrual mappings, including blanks for native validation to identify. It does not correct an existing live mapping or historical voucher; both still require a separate repair. Select the proper accrued-interest asset account with the accounting owner, preserving the native controller's account-type requirements.

## Evidence still required

- Chart of accounts, enabled leaf accounts, account types, fiscal years, opening balances and posting controls.
- Scheduled Job Type and execution-log evidence for native accrual, demand, classification and DCR reconciliation jobs. Configuration alone is insufficient.
- One traced loan: disbursement debits principal receivable and credits the correct bank/clearing account; receipt/invoice postings clear the proper purchasing accounts.
- Accrual, demand and payment postings reconcile separately to principal and unpaid interest, with no duplicate recognition or missing GL.
- Boundary payments 12–14 use agreed original-invoice principal reduction and dated interest; fees and insurance use agreed accounts and amounts.
- Payoff includes accrued unpaid amounts, excludes future forecast interest, settles the GL and native balances, and closes only when the agreed residual is zero.
- Cancellation and reversal evidence, bank reconciliation, and accounting-owner review of any historical correction.

No accounting setting, payment, journal, loan closure or historical balance was changed during this audit.

## Chart and scheduler readback

The enabled chart was expanded in Desk. It contains a dedicated Flooring Interest Income account, while the inspected Standard product uses Service/Fee Income. No dedicated accrued-interest asset was visible among the enabled current-asset accounts; confirm the intended asset and any disabled accounts before selecting or creating one. No balance changes were made.

The native interest-accrual Scheduled Job Type is not stopped, runs Daily Long, and shows last execution October 8, 2026 at 00:00:59 America/Los_Angeles. Its linked log list contains eight retained executions, all Complete, with the latest October 8. This proves the job runs, not that its incorrect account mappings produce correct accounting. Daily demand execution is also confirmed: last execution October 8 at 00:01:36, with eight retained Complete logs. Classification and reconciliation execution evidence remain open. The enabled 2026 fiscal year covers January 1 through December 31.

## Purchasing trace and historical-state limitation

An existing cash order was traced through its completed Purchase Receipt and paid Purchase Invoice. The invoice's GL balances: trade payables is credited, and the stock-received clearing account and use-tax account are debited. The linked receipt returns no GL entries for its posting date or the widened January 1–October 8 range after reloading the report with the receipt voucher filter. The receipt Stock Ledger report also returns Nothing to show for its posting date and the widened year-to-date range. This does not establish that the purchasing clearing balance reconciles.

Current read-only configuration adds an important limitation: Manufactured Home has Maintain Stock disabled and Is Fixed Asset disabled. Its company-specific Item Defaults have no expense, provisional or inventory-account override. Company perpetual inventory is enabled, while provisional accounting for non-stock items is disabled. The item was last edited July 31, after the inspected July 30 receipt and invoice, so today's non-stock setting cannot establish the stock treatment used at submission.

The installed [Purchase Receipt controller](https://github.com/frappe/erpnext/blob/af63cde4941570ec7b9e12422c68302762cfcf91/erpnext/stock/doctype/purchase_receipt/purchase_receipt.py) has a separate company-controlled provisional path for non-stock items. A receipt without GL is therefore not enough to diagnose a missing posting on its own. Next, inspect the historical stock/provisional conditions, stock-ledger evidence, invoice row account and all corresponding clearing entries. Determine whether the clearing debit has an offset before recommending any correction. No item or company field was edited or saved; no new financial transaction was entered. Raw voucher amounts and screenshots remain local and excluded from the public repository.
