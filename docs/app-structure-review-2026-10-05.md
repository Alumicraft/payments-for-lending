# Custom app structure review and ASW transfer

Reviewed October 5, 2026. Tomorrow's delivery is the DCR usable handoff and controlled pilot. This review covers source structure and GitHub ownership, not live provider configuration. The DCR installed-app snapshot is included below; Alumicraft and hosted email consumers still need inventory.

## Recommendation

Maintain one reusable shared app, with small client apps for business behavior. Consolidate responsibilities first; repository consolidation can follow. Independent forks of the entire stack would recreate the duplicate-maintenance problem: shared bug fixes would need to be copied to every client.

The shared app should own email delivery, common templates and branding, Desk/sidebar behavior, and reusable integration utilities. DCR should own lending, ACHQ, DocuSign, dealer permissions, and deal workflows. Alumicraft should own vehicle BOM, manufacturing behavior, and kiosk permissions. Provider adapters such as Stripe and QuickBooks should remain explicitly enabled integrations, with separate site credentials and schedules.

A single installable app is possible, but adds complexity around optional Lending dependencies, permissions, migrations, and hooks running on the wrong client's site. The smaller first step is a shared base plus the existing client apps. Client customization should extend the base rather than copy it. Forks are appropriate only when a client needs independent ownership and accepts maintaining upstream merges.

## What the source shows

| Repository | Installable app / service | Ownership today and proposed boundary |
| --- | --- | --- |
| `Alumicraft/payments-for-lending` | `dcr` | DCR business workflows and Lending overrides, plus common Desk/sidebar fixes. Keep business code here; extract common shell behavior. |
| `Alumicraft/alumicraft` | `alumicraft` | Vehicle BOM, Timesheet kiosk, server permissions, plus common sidebar behavior. Keep business code here. |
| `Alumicraft/theme` | `backdesk` | Workspace/sidebar shell, but also business-specific product and financial-report repair patches. Separate generic shell behavior from client migrations. |
| `Alumicraft/emails` | `emails` plus `templates/` service | Already a reusable Frappe email app with a React Email/Resend service in the same repo. Preserve one canonical implementation with per-site settings. |
| `Alumicraft/email-templates` | Separate React Email service | Overlaps the combined repo's template service. All 12 inspected email templates, `src/send.tsx`, and `package.json` differ by Git blob hash; `vercel.json` matches. Reconcile differences and identify live consumers before retirement. |
| `Alumicraft/payments` | `payments` | Stripe invoice/payment integration, Project dashboard, and residual write-offs. Treat payment/provider behavior as an explicit integration. |
| `Alumicraft/quickbooks` | `quickbook` | QuickBooks import/sync, accounting hooks, diagnostics, and scheduled jobs. Keep isolated from generic shell and unrelated clients. |
| `Alumicraft/items` | `items` | Item-master behavior and migration hook. Determine which rules are reusable versus Alumicraft-specific. |

The DCR Cloud snapshot contains Frappe, ERPNext, Lending, DCR and Emails. Backdesk, Payments, and QuickBooks were absent from that site's five-app list. This verifies the DCR combination only.

The user called the manufacturing client LumaCraft; the repository and Python app actually found are named Alumicraft. No separate LumaCraft repository was found in this source inventory.

### Concrete issues to address during consolidation

1. **Three owners for sidebar/boot behavior.** DCR, Alumicraft, and Backdesk register boot hooks and global sidebar assets. DCR and Backdesk also override the same desktop-layout and workspace-save endpoints. These overlaps are demonstrated in source; the combinations currently installed on each live site still need checking. Frappe collects assets and uses hook resolution order for overrides, so a shared app must have one deliberate owner for each behavior. [Frappe hook documentation](https://docs.frappe.io/framework/user/en/python-api/hooks)
2. **Email duplication is narrower than two complete email apps.** The `emails` app already supports client settings. The clear second implementation is the standalone `email-templates` service. Determine which source each hosted email project deploys before choosing a canonical version.
3. **An undeclared dependency.** `dcr/api/dcr_email.py` imports `emails.email_service` but DCR's `required_apps` lists only Frappe, ERPNext, and Lending. The pilot completion batch adds `emails` to `required_apps`. Extracted shared-base imports will still need compatibility during a later migration.
4. **Broad email interception.** Emails overrides Payment Request, the communication send method, and `frappe.sendmail` at session creation and before requests. Stripe also hooks Payment Request. Test the combined behavior, background-job email, attachments, retries, and duplicate suppression before changing ownership.
5. **Client migration code in the theme app.** Backdesk contains product/catalog and financial-report repair patches. Generic installation must not silently apply those rules to another client. Scope future patches and preserve historical patch identities so completed changes do not replay.
6. **Client security boundaries must remain explicit.** Kiosk server permissions and DCR dealer scoping cannot become generic branding switches. Test each site's enabled integrations and denied API paths.

## Transfer scope

Move all eight repositories from `Alumicraft` to `American-Signal-Works`, keeping repository names and visibility initially. GitHub ownership transfer and app refactoring are separate operations. Keep Python app names, DocType names, API URLs, and asset paths stable for the ownership move.

| Source | Target | Visibility |
| --- | --- | --- |
| `Alumicraft/alumicraft` | `American-Signal-Works/alumicraft` | Public |
| `Alumicraft/payments-for-lending` | `American-Signal-Works/payments-for-lending` | Public |
| `Alumicraft/theme` | `American-Signal-Works/theme` | Public |
| `Alumicraft/emails` | `American-Signal-Works/emails` | Public |
| `Alumicraft/email-templates` | `American-Signal-Works/email-templates` | Private |
| `Alumicraft/payments` | `American-Signal-Works/payments` | Public |
| `Alumicraft/quickbooks` | `American-Signal-Works/quickbooks` | Private |
| `Alumicraft/items` | `American-Signal-Works/items` | Public |

**Execution blocker:** live GitHub API checks identify the connected account as `Buddalish`, with active admin/owner membership in `American-Signal-Works`, but `permissions.admin=false` on every source repository. There are no matching repository names in the target organization inventory. GitHub requires source repository Admin access for a transfer. Grant that access, authenticate a source-admin account, or have the source owner execute the transfers. No transfer has been attempted. [GitHub transfer requirements](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository)

### Transfer and deployment verification

1. Record each live site's installed apps, hook order, deployed commit, branch, and Frappe Cloud source association. Record both clients' hosted email services and source/root directory; resolve whether `email-templates` has any active consumers.
2. Ensure Frappe Cloud and the email hosting integration have access to the ASW repositories, including both private repos. Check ASW organization policies and branch protection before the move.
3. Transfer the original repositories with their history, issues, and PRs. Preserve visibility. Verify destination ownership, repository identity, branches/tags, collaborators, protection/rulesets, and integrations after each transfer.
4. Update local remotes and hosting source associations to ASW. GitHub redirects old Git URLs, but deployment integrations still need verification. GitHub documents that repository webhooks, secrets, and deploy keys stay associated; that does not prove a hosting GitHub App has destination-org access.
5. Build from the same tested commit through the Frappe Cloud dashboard and verify the deployed revision. Deploy each email service from its recorded source and configuration. Do not uninstall/reinstall apps just to change GitHub ownership.
6. Check login, workspace/sidebar navigation, DCR dealer portal permissions and one controlled deal, Alumicraft kiosk restrictions and BOM access, branded email rendering and approved test delivery. Verify provider webhook routing and scheduler configuration without enabling new live financial effects.
7. Keep database/file backups and the previous deployment reference. A repository transfer-back is a separate ownership operation; a deployment rollback does not require moving repository ownership back.

This scope moves GitHub source ownership. Moving Frappe Cloud teams, email hosting accounts, domains, billing, or provider accounts is a separate operation and has not been inferred from the request.

## Sequence around tomorrow's handoff

- Finish DCR pilot blockers and setup using [the delivery checklist](delivery-checklist-2026-10-06.md). ACHQ wiring and accounting-result verification remain required before calling that path ready.
- Prepare the ownership move now; execute once source Admin access and hosting access are available. Preserve the existing tested application behavior.
- After the handoff, establish one canonical email service, then extract shared shell behavior one responsibility at a time.
- Preserve old module/API import paths during migration. Move DocTypes, fixtures, custom fields, and patches through explicit compatible migrations; changing repository ownership does not migrate app ownership in the database.
- Verify the shared base on two separate test sites: DCR with Lending and Alumicraft without DCR-only requirements. Test upgrade of existing data as well as a fresh install, repeated migration, scheduler jobs, email, permissions, and one representative workflow per client.

## Evidence snapshot

GitHub source revisions read October 5, 2026 (DCR subsequently advanced through merged PRs #10/#11 and the pilot completion delivery):

| Repository | Commit |
| --- | --- |
| `alumicraft` | `8693aea300fb75ad228feb18fa457be987ea608b` |
| `payments-for-lending` | `a9a636f` after PRs #10/#11; final pilot merge receipt in delivery update |
| `theme` | `c917c3b09523b56c0847ed8ddcfbf40f228973f2` |
| `emails` | `f50f47eb91f50e1336258cbebb841537c1a32dfe` |
| `email-templates` | `6ff9d065ab7e2928e4bd214f02ccce2ed3727bd6` |
| `payments` | `d739862660732e42d96d3ba496cc009860cb409c` |
| `quickbooks` | `3997ce1ab171612911ab7119e3b21362996229fc` |
| `items` | `45202e98dbe591b8486e884185a9d34bb7e0d127` |

The local Alumicraft branch is one commit ahead and 21 behind refreshed `origin/main`; it was not merged or reset. Theme, Payments, and QuickBooks local HEADs also differ from remote `main`; their remote hook files were compared for this review. Existing QuickBooks edits and Payments untracked fixtures were preserved. No application code, credentials, live configuration, or production records were changed by this review.
