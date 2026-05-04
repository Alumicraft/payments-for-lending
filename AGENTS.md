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
