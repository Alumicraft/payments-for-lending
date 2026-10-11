# Accounting readiness audit

Updated October 11, 2026. Status: **not ready; configuration findings and posting reconciliation remain open**. This is part of the pilot checklist, not a certification of the ledger.

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

- PR #63 installation accepted: pipeline fa68dup533 succeeded October 9 11:00 AM in 5m 3s; refreshed site Updates reports Pull Success at 10:59 AM and Apps links exact c9c4eba5a07cf02b0257393cb7d59b04f2bfa14e. No metadata migration required. Private plaid-session-fix-installed.jpg retained. Fresh bank list still redirects to Login because the prior connection damaged the existing staff session. Requested renewed staff sign-in after deployment; consent is already satisfied. Actual session preservation, saved bank masks/default, fresh packet, signing and ledger reconciliation remain open.

Staff access restored via normal Cloud Options → Login As Administrator. Sandbox bank native readback confirms enabled/default, Active/POS, account 0000 and routing 1533. Fresh packet displays these masks and application 13, with agreed amounts/dates preserved. Fresh signing requires explicit test-send permission; loan, fees, accrual, repayments and reconciliation remain open. Accounting remains not ready.

Owner requested a pause after saving current results. Synthetic Cash request 28 passed missing-document admission and staff-waiver submission; PO 17 passed submission/cancellation with request Ordered → Pending rollback, and amended PO 17-1 passed closure/readback. These Purchase Orders do not prove ledger readiness: no Cash invoice/payment/receipt or new flooring loan/disbursement/fee invoice was posted. Resume the full application 13 financial workflow and reconciliation; accounting remains NOT READY.

## October 11 resumption

Fresh staff application 13 readback preserves the agreed trial basis and dates. The packet review was regenerated, but explicit Sandbox test-send permission remains unanswered; no new signature, loan, disbursement, charge invoice or payment was created. Closed/cancelled Purchase Order history and combined dealer/factory/status filtering passed as Administrator. These order-history checks add no ledger evidence. Backdesk later encountered a connection reset during the date-filter reload, while Cloud still reported the site Active. Accounting remains not ready.

### Scheduler execution evidence, October 11

Read-only native Scheduled Job Type and linked Scheduled Job Log inspection confirms the following. All four Stopped checkboxes are unchecked. No job was manually triggered, edited or saved. Times are America/Los_Angeles.

| Job | Frequency | Last execution | Latest log | Observed result |
| --- | --- | --- | --- | --- |
| Native loan accounting, 1547c74ssq | Daily Long | October 11 00:01:26 | d2m0shuov8 | Complete; all six listed logs Complete |
| Native interest accrual, h9avlsfpk1 | Daily Long | October 11 00:01:30 | 72n9het698 | Complete; all eight listed logs Complete |
| Native loan demand, h9at5rqcmp | Daily Long | October 11 00:01:28 | 52moiuklon | Complete; all eight listed logs Complete |
| DCR settlement reconciliation, 1o9r6r3aeb | Hourly | October 11 11:00:50 | c51qok22ok | Complete; latest three listed logs Complete, 143 total logs, older history not fully reviewed |

This proves enabled schedules and recent successful wrapper execution. It does not prove voucher creation, eligible-loan processing, accrual amounts, settlement allocation or GL reconciliation. Retained private screenshots oct11-accounting-job-complete.jpg, oct11-accrual-job-history.jpg and oct11-demand-job-history.jpg. Classification scheduler and downstream voucher reconciliation remain open.

Fresh Backdesk tab navigation recovered after the earlier tab encountered connection resets. Cloud Domains reports Backdesk and the Frappe hostname Active. No domain, certificate, network or security configuration changed.

### Signed trial and loan-date admission repair

Application 13 completed ordinary DocuSign Sandbox signing as SIG-0194 on October 11. Staff attachment and delivered executed-email attachment downloaded and matched byte-for-byte. Created draft Loan ACC-LOAN-2026-00025 through the ordinary application action, linked to First Platypus 0000. No new loan submission, funding or fee posting yet.

Loan draft exposed a first-payment-date mapping defect: October 11 and $750 preview instead of signed November 1 and $2,325. PR64 fixes native mapping integration, missing date-field projection, and invoice-backed draft date validation. It is merged with 617 Python tests, 40 subtests and 12 Node checks passing; Cloud pipeline 5p94d92s70 is running. Once installed, re-save draft 25 and verify persisted November 1 and $2,325 before submission. Then create normal disbursement for October 1 with $5,000 Billed Separately financed charge, reconcile actual fee invoice and GL, and proceed to accrual/demand/repayment/payoff/reversal trials. Accounting remains not ready.

### October 11 installed date fix and reconciled funding trial

- Cloud pipeline 5p94d92s70 succeeded at 3:19 PM in 5m15s. Fresh Site Apps links exact PR64 merge e83da0a38dd83b18fbe56cd39d111b76bfa2b38d; native app upgrades remained unselected. Private oct11-date-fix-installed.jpg retained.
- Normal Save of Draft Loan ACC-LOAN-2026-00025 corrected repayment start October 11 to November 1 and monthly payment $750 to $2,325. Posting date changed to October 11. Saved Version 8v180eanns proves all three changes. Loan submitted normally and became Sanctioned, Version 5v7e91o8q9. Private oct11-loan-date-corrected.jpg retained. Fresh unsaved Create Loan wrapper acceptance remains separate.
- Native Create Disbursement initially left fetched sanctioned amount/accounts blank. Clearing and reselecting the exact submitted Loan through its normal link control fetched $225,000, Funding Clearing and Loans Receivable correctly. Record as a workflow friction case; root cause is not yet diagnosed. Saved LM-DIS-00012 with posting October 11, disbursement/value date October 1, repayment November 1, PI ACC-PINV-2026-00009, $225,000 and one $5,000 DCR Financing Fee row, DCR Fee Receivable, Billed Separately. Normal Submit succeeded, Version 91g5l8istp. No provider transfer was initiated.
- Generated Sales Invoice ACC-SINV-2026-00006 is Paid, grand total $5,000, zero taxes and zero outstanding; linked to Loan25/Disbursement12, posting October 11/value October 1. Actual invoice GL: DR DCR Fee Receivable $5,000; CR 40110 Service/Fee Income $5,000. Actual consolidated disbursement GL: DR 10202 Loans Receivable $225,000; CR Funding Clearing $220,000; CR DCR Fee Receivable $5,000 against SI6. Combined with PI9's previously verified DR Funding Clearing $220,000/CR Trade Payables $220,000, trial clearing and fee AR net to zero. Financed fee is counted once.
- Normal PI Create Payment produced internal Payment Entry ACC-PAY-2026-00008, posting October 11, $220,000 allocated fully to PI9; reference DEMO-INTERNAL-ONLY-20261011. Normal Save/Submit succeeded. Actual GL DR Trade Payables $220,000, CR 10102 Chase General $220,000. This is a disposable ERP ledger entry, not a bank/provider payment. Across the four trial vouchers: Loans Receivable DR $225,000; Fee Income CR $5,000; General bank CR $220,000; Funding Clearing, Fee Receivable and Trade Payables all net zero. Private oct11-disbursement-submitted.jpg, oct11-disbursement-gl.jpg, oct11-fee-invoice-gl.jpg and oct11-factory-payment-gl.jpg retained.
- Accounting remains NOT READY overall. Accrual/demand, payments 12–14, early payoff, closure, reversals and deliberate mismatch rollback are still open; fresh dealer portal signed-copy download, revised-invoice signing and callback session acceptance also remain open.
### October 11 daily accrual and early payoff/reversal

- Submitted scoped normal Process Loan Interest Accrual LM-PLA-00359 for Loan25/Disbursement12 through October 11; Version 63vh43capf. Created eleven daily records LM-LIA-00595 through LM-LIA-00605 for October 1–11 inclusive. Latest daily record showed $225,000 basis, 12%, $75 interest and actual GL DR Accrued Flooring Interest/CR 40102 Flooring Interest Income $75, Main cost center. Native accrual end date includes the selected day.
- Normal Create Loan Repayment with Loan Closure quotes exactly $750 interest for ten elapsed days October 1 to October 11, total $225,750. Saved/submitted LM-REP-0007, reference DEMO-PAYOFF-REVERSAL-20261011, Version 2589s96emv. Actual payoff GL: DR Trust bank $225,750; CR Loans Receivable $225,000; CR Flooring Interest Receivable $750. Native generated submitted paid interest demand LM-LD-00091, $750 demand/$750 paid; actual GL DR Flooring Interest Receivable/CR Accrued Flooring Interest $750. Fresh Loan25 is Closed. Native automatically cancelled October 11's same-day accrual LM-LIA-00605, aligning the payoff to ten elapsed days. Insurance was not charged by this native repayment; insurance integration remains open.
- Normal cancellation of payoff LM-REP-0007 succeeded, Version 96d66a3n5j. Consolidated payoff GL contains equal debit/credit on each affected account: Trust $225,750 each, principal AR $225,000 each, interest AR $750 each, all net zero. Generated demand91 is Cancelled. Fresh Loan25 is Disbursed again with $225,000 pending principal. Remaining accrual/demand residual and regeneration behavior still need aggregate readback; do not infer those from the payoff reversal alone.
- Private oct11-daily-accrual-gl.jpg, oct11-payoff-gl.jpg, oct11-payoff-demand-gl.jpg, oct11-loan-closed.jpg, oct11-payoff-reversal-gl.jpg and oct11-loan-reopened.jpg retained. Early-payoff/closure and this payoff reversal passed; full accounting readiness and monthly repayment/curtailment acceptance remain open.

### October 11 monthly boundary trial in progress

- Saved native schedule LN-RS-2026-00014 verified: payment12 October1 2027 principal0/interest2250; payment13 November1 principal2250/interest2325/total4575/balance222750; payment14 December1 principal2250/interest2227.50/total4477.50/balance220500. Payment37 continues with principal2250, no month36 balloon; last payment112 February1 2036 principal2250/interest23.25/total2273.25/balance0. These are actual saved schedule rows, not posted payment acceptance.
- Submitted scoped native Process Loan Demand b88ptquufm through October1 2027 for Loan25/Disbursement12. Generated exactly12 interest demands LM-LD-00092–00103, with payment12 demand2250. Native demand processing also generated corresponding accruals. Scoped accrual repeat LM-PLA-00372 through September30 2027 submitted with no linked new accruals, indicating no new records from that repeat; full aggregate duplication check remains open.
- Normal repayment LM-REP-0008 saved/submitted with posting/value October1 2027, reference DEMO-INTEREST-PERIODS-1-12, amount27375. Saved allocation covered all twelve interest-only demands, principal0, interest27375, excess0. This combines periods1–12 in one catch-up settlement; it does not prove twelve separate on-time monthly receipts. Actual repayment GL and payments13–14 are next. All records are synthetic future-date trials; no provider debit.

### October 11 payments 12–14 and aggregate GL acceptance

- LM-REP-0008 actual GL DR Trust bank/CR Flooring Interest Receivable $27,375, with no principal entry. Native controller persisted posting date October11 2026 despite the attempted future posting-date input; value date remains October1 2027. Future periods in this trial use value dates; the receipt GL is booked October11. Earlier in-progress note's claim of a future posting date is superseded by this persisted readback.
- Scoped Process Loan Demand 2apf3nbto6 through November1 2027 generated interest demand104 $2,325 and principal demand105 $2,250. Normal LM-REP-0009 saved/submitted with value November1 2027, posting October11 2026 and reference DEMO-PAYMENT-13-20271101. Actual GL DR Trust $4,575; CR principal AR $2,250; CR interest AR $2,325. Fresh pending principal $222,750.
- Scoped Process Loan Demand 0c4l4spd33 through December1 2027 generated interest demand106 $2,227.50 and principal demand107 $2,250. Normal LM-REP-0010 saved/submitted with value December1 2027, posting October11 2026 and reference DEMO-PAYMENT-14-20271201. Actual GL DR Trust $4,477.50; CR principal AR $2,250; CR interest AR $2,227.50. Fixed original-basis principal is preserved after the first curtailment; total declines as interest falls.
- Downloaded the complete native General Ledger CSV with Company Dealer Capital Resources, October1 2026–December1 2027, Against Voucher No Loan25, Categorize by Account. It contains932 rows including filters/header/subtotals. Local Decimal reconciliation verifies: Trust receipts DR $36,427.50; principal AR DR225000/CR4500/netDR220500; flooring interest income CR31927.50; service fee income CR5000; accrued interest DR31927.50/CR31927.50/net0; interest receivable DR31927.50/CR31927.50/net0; funding clearing CR220000 on loan-linked side. Trial PI9's separately verified DRclearing220000 and Payment8's DRpayables220000/CRGeneral220000 complete the funding chain. Fee AR against SI6 is separately zero. Total loan-linked DR and CR both325282.50. Exact active voucher counts:3 repayments,1 disbursement,426 daily accruals,1 fee invoice,14 demands. Interest matches365days×75 +31days×75 +30days×74.25 =31927.50; no residual accrued/receivable balance or extra active interest amount remains at this cutoff.
- Private oct11-interest-only-repayment-gl.jpg, oct11-payment13-gl.jpg, oct11-payment14-gl.jpg, oct11-loan25-aggregate-gl.csv and oct11-loan25-reconciliation.json retained. This proves the funded schedule, aggregate interest-only allocation, first two curtailment receipts and aggregate GL. Separate on-time payments1–12, insurance accounting, provider settlement, other reversals, mismatch rollback, repeated restructuring, historical opening balances and accounting-owner review remain open. Accounting is not yet ready overall.

### October 11 dealer readback and staff restoration

- Normal sign-out and fresh email-link login as send2tristan@gmail.com opened Portal Test's owned request29. Dealer request shows Signed Flooring Packet SIG-0194, funded Loan25 and outstanding principal220500. Download signed Flooring Packet succeeds; dealer PDF is344601bytes and matches staff/Gmail SHA2564d063cca2ad062352eaae792394922f106c73a81bbc5fc77b9ec964a56b6feb9. Three actual downloads match exactly.
- Show all101payments contains three Paid receipts27375,4575 and4477.50 on their actual October11 posting date. Cancelled payoff225750 is excluded. Future scheduled payments begin January1 2028; next payment4528.50, reflecting settled value periods throughDecember2027. Portal readback confirms amounts and history, not asynchronous transition without reload.
- Restored staff session using Cloud Options → Login As Administrator → Confirm. Fresh Desk Loan25 opens as Administrator, Disbursed with pending principal220500. User's unrelated unsaved PO tab was preserved. Private oct11-dealer-signed-copy.jpg and oct11-loan-current.jpg retained.


### October 11: post-curtailment payoff defect

A fresh unsaved Loan Closure for Loan 25, value date January 15, 2028, quotes $3,369.75 interest on $220,500 outstanding principal. Actual elapsed interest from December 1 through January 14 is 45 days × $73.50 = $3,307.50, so the native quote is $62.25 high. No incorrect repayment was saved or submitted. The native path reduces principal for an unpaid January schedule row and charges the payoff day. Private evidence: `docs/pilot-evidence/oct11-post-curtailment-payoff-mismatch.jpg`.

The proposed correction uses submitted funding and principal receipts dated by value date, preserves native permissions and allocation, and books missing daily accrual through the day before closure within submission. Legacy and unrelated loans retain native behavior. Source tests cover quotes, draft allocation, actual accrual balances, payoff-day exclusion and restoration after failure. Deployment and hosted quote/save/posting/reversal acceptance remain pending; accounting is not ready.

PR #65 source head `f9fdf7f0a076c4341dd90b0d3cda019cd0e63472` passed 635 Python tests and 40 subtests (nine existing datetime warnings), all 12 Node checks, diff whitespace, preflight and v16 hook-target checks. No GitHub CI checks are configured for this PR. Merged as `61c93b57e9d8cc608044873c49a59ab73a67517d`. Cloud deployment started October 11 at 4:11 PM with only DCR selected, the existing site selected, and skip-failed-patches unchecked. No schema, fixture, provider or historical-data migration is included. Installation and hosted acceptance are pending.
