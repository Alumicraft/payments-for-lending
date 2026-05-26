# Project Context

## Deployment
- This app runs on **Frappe Cloud**. There is no local bench.
- Never suggest `bench` commands — the user cannot run them.
- Deployments happen via the Frappe Cloud dashboard (push to GitHub → deploy).
- `bench migrate` runs automatically on deploy.

## App Info
- App name: `dcr`
- Module: `DCR`
- Frappe Framework v16 on ERPNext with Lending module
- No Server Scripts — all logic lives in the custom app
- E-signing service: **DocuSign** (not AdobeSign)

## Playbooks
Before improvising on a recurring task, check `docs/playbooks/` — read the matching playbook and follow it. Current playbooks:
- `deploy-to-frappe-cloud.md` — pre-deploy checks, patches, what to watch on the FC dashboard
- `add-print-format.md` — single-file JSON pattern, Jinja conventions, DocuSign anchors
- `add-doctype.md` — schema, validation, fixtures, the `custom + is_standard` v16 trap

## Agents
Project-level agents live in `.claude/agents/`:
- `preflight` — pre-deploy sanity check. Run before any push to `main`.
- `v16-linter` — flags Frappe v16 anti-patterns in changed files.
