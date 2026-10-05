# DCR home-page charts

Prepared October 5 for review before the October 6 controlled pilot. The seven charts are now deployed and visually verified on DCR Deals, Accounting, Contacts, Access, and grouped Overview pages. Existing site widgets were preserved.

## Layout

| Home page / Overview section | Charts |
| --- | --- |
| Deals | New Deals by Type; Deal Pipeline by Factory |
| Accounting | Inflows vs Outflows; Past-Due Aging; Repayment Breakdown |
| Contacts | New Dealers by Month |
| Access | Active Users Per Day |

Overview contains these seven charts under the corresponding section headings. Setup also repairs any additional valid charts configured on these home pages and includes them in their Overview section. A chart configured on multiple home pages appears once on Overview, under the first section in the table.

New Dealers by Month uses Frappe's native Count chart on Customer creation dates, filtered to enabled Customers in the Dealer group, monthly over the last year. It counts dealer records created, not deals, signatures, active logins, or borrowing accounts. Its source fields are standard Customer fields; no new financial calculation or custom data endpoint is introduced.

Existing cards, map blocks, links, and unrelated Overview charts are preserved. Existing section headings are reused. Workspace Chart rows and visual blocks are kept together, including custom row labels. Missing chart records are skipped rather than inserting broken links. Invalid layout JSON raises a visible setup error and is not overwritten. Repeated setup does not duplicate charts or save unchanged layouts.

The existing Frappe Cloud deployment runs setup after migration. All work is implemented in the custom app; no Server Scripts or local server commands are required. Source checks used Frappe's `version-16` Workspace and Dashboard Chart schemas. Hosted verification subsequently ran on Frappe 16.36.1.

## Local verification and hosted acceptance

The layout tests exercise provisioning, grouping, preserving unrelated blocks, label repair, missing chart records, invalid layout preservation, and repeat setup. Frappe is mocked. Tests do not verify SQL metrics, browser rendering, native chart date bucketing, or the live site configuration.

Hosted checks confirmed all seven placements, custom business-chart reconciliation against underlying records, Daily Active Users reconciliation, and denial of dealer access to custom chart/report APIs. Native New Dealers monthly values, date range and zero months also reconciled against enabled Dealer Customer creation dates using the serialized chart configuration used by the client. All intended staff-role combinations remain follow-up checks. Synthetic accepted deals may affect aggregate counts until removed or excluded under an approved cleanup procedure.

Acceptance procedure:

1. Record the deployed DCR commit and confirm migration/setup completed without errors. Capture each existing workspace layout before deploying so its prior arrangement can be restored if needed.
2. Open Deals, Accounting, Contacts, and Access, then Overview. Confirm all seven charts render and the Overview sections match the table. Verify any additional site-configured chart is present in its proper section.
3. Check existing cards, links, map blocks, and custom labels survived. Reload and return to each workspace; confirm no loading skeleton or duplicate chart blocks.
4. Run a second normal update/migration and confirm chart counts, layout, and workspace modification timestamps remain stable when no changes are required.
5. Check New Dealers by Month against filtered Customer creation dates. Verify native chart date-window behavior and zero-data display on the deployed version.
6. Check existing custom business charts against their underlying reports/records. Their calculation definitions are unchanged by this layout work. Access uses Daily Active Users, whose report requires System Manager; test with that role and verify other staff roles see the intended permitted state.
7. Confirm dealers remain on the scoped portal rather than gaining access to staff dashboards. The custom business-chart endpoints' authorization needs its own hosted check; layout placement does not establish endpoint security.

This batch targets DCR workspace home pages. Alumicraft home-page charts still need their own source/live inventory if the requested scope includes both clients.
