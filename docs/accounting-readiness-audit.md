# Accounting readiness audit

Updated October 9, 2026. Status: **not ready; configuration findings and posting reconciliation remain open**. This is part of the pilot checklist, not a certification of the ledger.

## Initial configuration findings

Initially read from the signed-in Company and Standard Loan Product forms without saving. Subsequent authorized changes are recorded under **Authorized trial resumed** below: Actual/360 is saved, and Standard now has separate accrued-interest asset and interest-income mappings. The table retains the original findings for the historical posting investigation.

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

The native interest-accrual Scheduled Job Type is not stopped, runs Daily Long, and shows last execution October 8, 2026 at 00:00:59 America/Los_Angeles. Its linked log list contains eight retained executions, all Complete, with the latest October 8. This proves the job runs, not that its incorrect account mappings produce correct accounting. Daily demand execution is also confirmed: last execution October 8 at 00:01:36, with eight retained Complete logs. Classification and settlement-reconciliation execution evidence is recorded below; transaction-level correctness remains open. The enabled 2026 fiscal year covers January 1 through December 31.

## Purchasing trace and historical-state limitation

An existing cash order was traced through its completed Purchase Receipt and paid Purchase Invoice. The invoice's GL balances: trade payables is credited, and the stock-received clearing account and use-tax account are debited. The linked receipt returns no GL entries for its posting date or the widened January 1–October 8 range after reloading the report with the receipt voucher filter. The receipt Stock Ledger report also returns Nothing to show for its posting date and the widened year-to-date range. This does not establish that the purchasing clearing balance reconciles.

Current read-only configuration adds an important limitation: Manufactured Home has Maintain Stock disabled and Is Fixed Asset disabled. Its company-specific Item Defaults have no expense, provisional or inventory-account override. Company perpetual inventory is enabled, while provisional accounting for non-stock items is disabled. The item was last edited July 31, after the inspected July 30 receipt and invoice, so today's non-stock setting cannot establish the stock treatment used at submission.

The installed [Purchase Receipt controller](https://github.com/frappe/erpnext/blob/af63cde4941570ec7b9e12422c68302762cfcf91/erpnext/stock/doctype/purchase_receipt/purchase_receipt.py) has a separate company-controlled provisional path for non-stock items. A receipt without GL is therefore not enough to diagnose a missing posting on its own. Next, inspect the historical stock/provisional conditions, stock-ledger evidence, invoice row account and all corresponding clearing entries. Determine whether the clearing debit has an offset before recommending any correction. No item or company field was edited or saved; no new financial transaction was entered. Raw voucher amounts and screenshots remain local and excluded from the public repository.

## Clearing balance and current invoice-default guard

The General Ledger was filtered to the stock-received clearing account for January 1–October 8, with no voucher filter. It shows zero opening balance, two Purchase Invoice debits, no credits and a nonzero debit closing balance. The inspected period therefore does not contain an offset for either invoice. Raw amounts and voucher captures remain local. Reconcile the underlying purchasing/funding model and any corrections with the accounting owner; a balanced individual invoice does not establish a cleared account.

A separate current source defect was reproduced in `ensure_purchase_invoice_expense_accounts`: a linked non-stock receipt row with no expense account is assigned stock clearing. Git history places that helper's introduction after the traced invoice's posting time, so this defect is not proof of that historical voucher's cause. Historical item classification and original defaults still need investigation.

PR #45, installed as `23b9e6d`, fills a blank account only for a qualifying stock item under perpetual inventory with an uncancelled positive receipt credit to the company's clearing account. Opening entries, stock-updating invoices, fixed assets, drop shipping, missing configuration and non-stock items retain native handling. Existing accounts are preserved. Missing non-stock account configuration can now produce ERPNext's required-account validation instead of being silently assigned to stock clearing. This is prevention for future defaulting, not a ledger correction.

The Products item group and its All Item Groups parent both have no Item Group Defaults rows. The previously inspected item and Company expense defaults are also blank. The approved invoice debit account must be selected for DCR's purchasing/funding model before a posting trial. A question requesting the approved account was sent to DCR; no setting or financial transaction was entered.

The second clearing debit was traced to a different home request, Purchase Order and Purchase Receipt. Its stored Expense Head is the same stock-received clearing account. The receipt-filtered year-to-date GL, with the account filter explicitly empty, returns only zero Opening/Total/Closing rows. The inspected pair is therefore not two invoices against the same inspected receipt; broader duplicate-billing checks remain open. No invoice field was edited.

## Existing disbursement readback

One submitted demo disbursement was isolated in the GL. It debits loans receivable and credits a bank account; the voucher's debits and credits balance. Its amount agrees with the Disbursed Amount on the disbursement and the linked Loan's Disbursed Amount and Pending Principal stats. This verifies this posting and principal readback, not bank ownership, actual money movement, the full loan ledger, unpaid interest or bank reconciliation. No transaction was created or changed.

PR #45 rollout: pipeline `3frnu0bt3f` succeeded in 3m57s; Update Site Pull `3i3rbfvbc5` succeeded in 5s. Cloud Apps confirms exact installed DCR `23b9e6d58aa8350ee253eb42fe0db9765511b6a0`. This Python-only change needed no metadata migration. The guard is regression-tested and installed; a hosted invoice-save/posting trial with approved account configuration remains open. The site Actions page provides no runtime console for an independent in-memory hook probe, and no financial document was saved to exercise it.

Hourly DCR settlement-reconciliation scheduler readback: Stopped is unchecked, last execution is October 8 at 18:00:56 America/Los_Angeles, and the filtered log list contains 78 of 78 retained executions, all Complete. This establishes scheduler execution only. The source routine retries accounting for Accounting Pending transactions using stored settlement evidence; no eligible transaction, resulting posting or real provider settlement was exercised during this check.

Native loan classification is enabled (Stopped unchecked), runs Daily Long, and last executed October 8 at 00:00:41 America/Los_Angeles. Its filtered list shows eight of eight retained logs, all Complete. No classification job was manually run. Accrual, demand, classification and DCR settlement-reconciliation scheduler execution are now observed; their accounting results still require the configured transaction cases and reconciliation.

## Authorized trial resumed

The user confirms this is resettable test data, permits normal-workflow transaction tests and directs Codex to select sensible mappings and reconcile postings. Principal/curtailment basis is the purchase invoice total including freight and financed DCR fees; interest is actual elapsed days / 360 from the invoice date; monthly payments continue after 36 months. Changed invoice amounts require a revised signed packet.

Company day-count convention is now saved as Actual/360, with Version `8un72gqin6` confirming Actual/365 → Actual/360. Historical entries were not changed. Custom schedule code still uses fixed 30-day interest and percent of remaining principal; its correction and dated posting reconciliation remain required. The mapping and historical findings above remain unresolved. Accounting is still not ready.

- Authorized mapping repair: created enabled leaf Asset/Balance Sheet `Accrued Flooring Interest - DCR` under Current Assets, with USD currency. Native Account rejects Current Asset as a leaf account type, so its leaf type is blank and its parent/root classify it. Standard product now maps interest_accrued_account to this asset and interest_income_account to existing `40102 - Flooring Interest Income - DCR`; Version `31esehnjfs` confirms both changes from Service/Fee Income. Other product mappings and historical vouchers remain to reconcile. No financial transaction was posted. Proof `docs/pilot-evidence/loan-product-interest-mapping-after.jpg` retained privately.
- Clean Company readback reconfirms Actual/360 and an empty IRAC table. An accidental empty row created by keyboard focus during proof capture was never saved; that temporary tab was discarded and the screenshot replaced with the clean persisted page.

- Native schedule carry defect reproduced against installed Lending `97f692e`, using its actual extracted method with a synthetic partial-disbursement fixture: 15 days on $100,000 at 12% gives $493.15 versus Actual/360 $500.00. Company configuration does not change that hardcoded native schedule path. Diagnostic `tools/diagnostics/floorplan_native_carry.py` verifies the upstream file hash and performs no database operations. Carry/restructure repairs remain a source release prerequisite; no trial posting can yet establish end-to-end schedule correctness.

- Local carry repair now makes the same diagnostic pass with `--dcr`, preserves previous balances and native adjustments, and prevents overlap between a pre/advance-payment due row and later interest periods. Normal restructure no longer restarts the IO phase. Full mocked Python suite: 513 tests and 40 subtests passed, 9 existing warnings. This repair has not been deployed; final invoice sourcing, revised-packet enforcement, previews, remaining account mappings and normal-document GL reconciliation remain open.

- Local final-invoice funding checks now use the submitted Purchase Invoice payable total, including its rounding treatment, plus only additional financed DCR fees outside that invoice. Supplier bill_date is the interest/funding start, falling back to posting_date. Before new disbursement submission, application/loan principal and interest rate must agree with a current signed financial snapshot; its private PDF must exist and the funding date must agree. Quote-only or older signed terms cannot pass this check. Source tests pass (534 Python, 40 subtests), but ordinary amendment/revision usability, previews, contract-rate consistency, deployment and actual GL reconciliation remain open. No financial trial transaction was posted during this source work.


## October 9 trial ledger plan — not posted or reconciled yet

PR #54 (`fe2d76c`) is installed with a successful site migration. Its invoice and signed-term admission checks are live; hosted accounting proof remains open. A follow-up is required to preserve original principal and payment phase across repeated native restructuring.

Pinned Loan Disbursement source `97f692e` debits the loan account and credits the disbursement account. Its charge Sales Invoice creates fee receivables/income, then a negative disbursement GL entry clears fee receivables and reduces net proceeds. This source trace is not voucher acceptance.

For a $220,000 factory invoice and $5,000 separately financed upfront DCR fee, test normal documents using an internal Funding Clearing asset account as the Loan Disbursement source. Expected postings:

| Normal document | Debit | Credit | Amount |
| --- | --- | --- | --- |
| Loan Disbursement | Loans Receivable | Funding Clearing | 225,000 |
| Native fee Sales Invoice | Fee Receivable | DCR Fee Income | 5,000 |
| Native charge offset | Funding Clearing | Fee Receivable | 5,000 |
| Factory Purchase Invoice | Funding Clearing | Factory Payables | 220,000 |
| Factory Payment Entry | Factory Payables | Bank | 220,000 |

Expected closing clearing, fee receivable and payable balances are zero; loan asset is $225,000 and fee income is $5,000. No provider transfer is needed for this internal trial. Using the actual bank as both loan disbursement source and factory-payment source would double count the cash outflow.

This mapping is a proposed trial configuration, not saved yet. Additional financed fees still need to be matched to native upfront charge invoices; Add to first repayment must not collect them twice. Native disbursement posting_date defaults to today while schedule/value dates use disbursement_date; verify dated GL/accrual behavior separately. Historical vouchers and bank reconciliation remain unresolved. Accounting remains **not ready**.

- Accounting trial configuration saved through native forms: enabled USD Asset/Balance Sheet Funding Clearing - DCR under Current Assets (Bank account type for native disbursement selection), and Flooring Interest Receivable - DCR under Accounts Receivable (Receivable type). Standard disbursement_account now uses Funding Clearing, Version `94puhvhhg0`; interest_receivable_account uses the separate receivable and broken-period recovery uses Flooring Interest Income, Version `45alk37pm1`; interest waiver also uses Flooring Interest Income, Version `a5j8nj423l`. Repayment still uses the existing trust bank. No financial transaction, provider movement or historical-voucher edit was performed. Native saves and Version readbacks passed; normal-document GL and bank reconciliation remain open.

- Company Default Cost Center now Main - DCR, native Version `985it84fq4`; the stale initial save was rejected and successfully retried after refreshing. Current factory-payable and bank defaults were inspected; receivable and purchase-invoice/item debit configuration still need completion. No financial trial transaction posted.

- PR #55 exact source `254f68a` installed; optimized pull succeeded, followed by explicit metadata migration `28rc1246es` Success in 20s. Hidden original-principal field appears in a fresh Loan form. No legacy basis/GL backfill. Normal-document funded schedules, repeated restructuring, fee linkage and GL/accrual/repayment/reversal reconciliation remain pending; accounting is still not ready.

## First normal-workflow trial posting

Synthetic request ACC-HBR-2026-00029 and PO PUR-ORD-2026-00016 are submitted. Staff waivers identify missing attachments as a test choice, not genuine factory evidence. Trial factory invoice ACC-PINV-2026-00009 is submitted for $220,000 including freight, with no tax in this bounded case. Its supplier invoice date is October 1 and GL posting date October 9. The default 6% tax template reappeared when mapping the order into an invoice; it was removed explicitly on this synthetic invoice. Tax-bearing financed invoices remain a separate accounting case.

The native GL shows debit Funding Clearing $220,000 and credit Trade Payables $220,000, cost center Main; voucher totals balance. Funding Clearing now has a $220,000 debit pending the corresponding loan funding. Fees, factory payment, accrual, demands, repayment, reversal and closure are not reconciled yet. No provider transfer occurred. Private screenshot accounting-trial-invoice-gl.jpg retained outside public Git.

Funding Clearing Account Type is now **Temporary**, Version 7i7ji8q5n1, superseding the earlier Bank classification. The installed ERPNext get_expense_account query admits Temporary assets but excludes Bank accounts; installed Lending Loan/Product queries admit leaf Asset accounts without requiring Bank type. Native account selection, invoice save and submission passed after this correction. USD, root Asset, Balance Sheet, Current Assets parent and Standard disbursement mapping remain unchanged.

Application ACC-LOAP-2026-00013 derives principal $225,000 from the submitted invoice plus $5,000 additional fees, with October 1 funding date and November 1 first payment. Hosted interest preview is $2,325 for 31 days at 12% / 360. Monthly insurance $123.45 is entered for PDF acceptance. Application is saved but not submitted/signed/funded. Additional fees still require matching native upfront charge documents.

A repeated Not Saved state was reproduced on this application: unknown numeric projections are cleared to null by the browser, then restored to zero on reload by Frappe. Client repair is prepared and regression-tested; release/readback remains pending. Accounting remains **not ready**.

### October 9 fee configuration and release acceptance

DCR Fee Receivable - DCR is saved as an enabled USD leaf Receivable account under Accounts Receivable. Standard Loan Product now contains DCR Financing Fee with Fixed Amount default zero, Service/Fee Income for income and waiver, and DCR Fee Receivable for receivable; native Version csm544jffu confirms these mappings. Actual per-loan fees, their native invoice postings and receivable clearing are not yet verified. Suspense and write-off remain unconfigured for this charge.

PR #56 is installed at 28721005a8eda0785da2d39fc565ffda18e27ac9 after successful pipeline 5mqiijgu3t. Fresh application assets are 20261009-18, but the trial application still becomes Not Saved after saving. Hosted save acceptance failed; application submission, signature, loan funding and accounting reconciliation remain open. Accounting remains **not ready**.

The remaining save loop is a credit-response mismatch: ordinary savedocs returns outstanding $124,561 and current status No, while the refresh endpoint returns zero outstanding and no current_yn when the MIFA limit is absent. That refresh rewrites saved fields. Numeric projection script repair is actually installed; the subsequent Version zero-to-null entries arise during server calculation. A source fix now preserves actual balance/status with available credit zero for absent/zero limits. 566 mocked Python tests plus 40 subtests and 12 Node files pass. Hosted acceptance awaits deployment; do not regard this as proof of the overall loan/accounting flow.

Company Default Receivable Account now DCR Fee Receivable - DCR, confirmed by Version 61d7dtn3rg, matching the product fee mapping and native charge-invoice fallback for this trial. Actual fee invoice/offset postings remain unverified. PR #57 merged at 25c533c; DCR-only pipeline 60tcqjb7c5 is running, with the site selected and skip-failed-patches off. Verify that exact release and hosted save behavior next.

PR #57 hosted acceptance passed: pipeline 60tcqjb7c5 and site Pull succeeded; installed exact 25c533cc4ee2944967ae515ef3fe1493896662c1 confirmed. Application 13 stays clean after Save/reload and is now Submitted (Version 84pb8p990t). Ordinary packet preview PDFs confirm $225,000 financed amount, October 1 interest start, $2,325 first scheduled interest, November 1 first payment and $123.45 insurance. All five generated pages were rendered and inspected privately. Packet remains unsent: receipt prose incorrectly states factory payment has already occurred, and bank account/routing masks are blank in the trial preview. Fee invoice linkage, actual loan funding and all subsequent postings/reconciliation remain open; accounting remains not ready.

Bank preview absence is a fixture/configuration gap: the existing linked native Bank Account has no recorded last-four account/routing identifiers or verification status. No fictitious identifiers were added and no provider settings changed. Prepared receipt text now follows invoice-date/set-aside timing with potentially later factory payment; quoted receipts remain estimates. Prepared ACH template excludes disabled accounts and makes missing identifiers explicit. 571 mocked Python tests and 40 subtests pass; standard Print Format import and live PDF acceptance remain pending deployment.

PR #58 is installed at 808f0ffce96a1b67474df7222c32dcefbc11da3e with successful pipeline 5fhh5qqt1n and site migration October 9 2:05 AM. Regenerated packet PDFs now follow set-aside funding timing and explicitly label absent bank masks; financial/insurance values remain correct. Bank modes are configured as ACHQ Sandbox and Plaid Sandbox, Controlled Pilot; no settings were changed and provider acceptance is not established.

Financed-fee guards are prepared after six failing admission cases: missing/excess/repeated fees, first-repayment duplicate collection and recharging invoice-included fees. The guards handle partial allocation, actual tax-inclusive invoice totals and currency, selected receivable consistency, native grand-total rounding and required loan accounting. They do not modify historical postings. 591 mocked Python tests and 40 subtests pass; real native posting, rollback and clearing reconciliation remain required. Accounting is still not ready.

PR #59 merged as cde9d663980e032e3f80c2bb251a09cff45ea45e; DCR-only Cloud pipeline 3gsidmtbqp started October 9 2:55 AM. Installation, native fee posting, rollback and clearing reconciliation remain pending. DocuSign environment is configured Sandbox (read-only observation). Accounting remains not ready.

PR #59 is installed at exact cde9d663980e032e3f80c2bb251a09cff45ea45e; pipeline 3gsidmtbqp and site migration October 9 3:01 AM succeeded. Real fee posting and reconciliation remain open. Dealer bank invitation stops on an incomplete enabled legacy record; explicit reconnect option prepared, with 594 mocked tests and 40 subtests passing. No bank account or provider connection has been changed.

Bank reconnect PR #60 is merged at 60554806e2b245f7189ada492d578155f442b2e5 and pipeline 9mebt5gb73 is running. A second source repair now retains the selected Plaid Auth routing mask instead of saving it empty; 600 mocked tests and 40 subtests pass. No provider transaction, connection or bank save has been performed. Native loan/fee/repayment acceptance remains pending.

PR #60 is installed as 6055480 with successful pipeline and site Pull. Normal invitation reaches Plaid Sandbox, with consent pending and no bank save. PR #61 is merged as c472ea0; pipeline fruj36n3oo is running from October 9 3:13 AM. Routing-mask readback and normal funded-loan/fee/repayment reconciliation remain open. Shared browser is now signed in as the dealer; staff sign-in is needed before further Desk transactions.

PR #61 is installed at exact c472ea0e73918b409b32cbd3361aa2667fea6950; its pipeline and site Pull 0vakch3ib7 succeeded. Native app pins unchanged. Actual bank save and masked-identifier readback remain pending consent. ACH application-reference correction PR #62 is merged as 70f3879 and pipeline 405skjp04s is running; hosted packet import/readback remains open. No normal loan funding or fee posting performed in this turn.

PR #62 is installed at exact 70f3879055a00270fcc331a8eb361d53eda06f77; pipeline and site migration succeeded October 9 3:26 AM. Fresh packet preview remains pending staff sign-in. Plaid consent remains unanswered, and fresh Desk navigation redirects to Login. No live loan funding, fee invoice or repayment was posted. Accounting remains not ready; resume through normal documents after access/consent, preserving the full reconciliation scope.

- Owner restored staff sign-in and explicitly approved Plaid consent. Normal Sandbox Link completed with First Platypus Bank ending 0000; automatic payments remain off. Opening fresh native bank records then redirected to Login. Pinned Frappe set_user resets sid and session data: both guest Plaid wrappers restored only the username, invalidating staff sessions. Four regression cases failed before repair; token verification precedes elevation and caller session/request state is now restored on success or provider failure. 606 mocked tests and 40 subtests pass. Saved bank masks, fresh packet and accounting postings remain unverified pending release and renewed staff sign-in. Private plaid-sandbox-connected.jpg retained.
