# Deploy to Frappe Cloud

**Push to `main` = deploy to production.** There is no staging. There is no `bench`. Treat every push to `main` as a prod deploy.

## Pre-deploy

1. **Run preflight.** Ask Claude to "run preflight" — it spawns the `preflight` agent which catches the recurring failure modes (orphan workspace refs, debug code, unsafe migrations, Server Scripts, etc.).
2. **Run v16-linter on the diff.** "Lint for v16 issues." Catches `pluck="name"` misuse, `custom + is_standard` collisions, JS sidebar mutations.
3. **Review the diff yourself.** `git diff origin/main...HEAD` — does this match what you intend to ship?
4. **Tests.** If anything in `dcr/tests/` changed, run them. If schema/fixtures changed, run the test suite anyway as a sanity pass.

## Patches

If this push includes a **data migration** (renaming a field, moving data between tables, backfilling values):

1. Add the patch as `dcr/patches/<name>.py` with an `execute()` function.
2. Register it in `dcr/patches.txt` as `dcr.patches.<name>` (one entry per line, no extension).
3. Patches run **once** in the order listed during the post-deploy `bench migrate`. If a patch fails mid-deploy, the site is left half-migrated — write patches to be **idempotent** where possible (check before mutating).
4. Patches that touch large tables: keep them in pure SQL via `frappe.db.sql` rather than ORM loops (see `dcr/patches/rename_dcr_floored.py` for the pattern). Always `frappe.db.commit()` at the end.

## Fixtures

If this push modifies anything in `dcr/fixtures/` (`custom_field.json`, `property_setter.json`, `doctype_link.json`) **or** adds a new fixture entry to `hooks.py`:

- Confirm the fixture filters in `hooks.py` actually include what you added. New entries that aren't filter-matched won't export and won't deploy.
- Property setters live in `hooks.py` `fixtures = [...]` as an explicit `name IN (...)` list. Adding a new property setter means adding its name string there.

## The push

```bash
git status                         # sanity check
git diff origin/main...HEAD        # what's actually shipping
git push origin main               # deploys
```

Then open the Frappe Cloud dashboard → Bench → Deploys, and watch the build + migrate output.

## What to watch on Frappe Cloud

- **Build phase** — pip install errors, app import errors. Usually a `setup.py` / `requirements.txt` mistake or a syntax error in a top-level module.
- **Migrate phase** — this is where 90% of prod issues land. Watch for:
  - `LinkValidationError` from orphan workspace refs (see [fix-workspace-freeze.md](fix-workspace-freeze.md) when you write it)
  - `TypeLink.make()` indent property error → custom doctype shipped with `"custom": 1` AND `"is_standard": 1`
  - Patch failures (any line like `dcr.patches.X failed`) — the migrate aborts here; site is half-migrated
- **Post-deploy tour** — open the production site, navigate to:
  - The Workspace home — does it render or show the empty skeleton?
  - Any doctype list view you changed — do columns load?
  - One existing record of any modified doctype — does the form open without console errors?

## When a deploy goes wrong

- **Build failed** — push a fix to `main`. Nothing prod-side changed; just iterate.
- **Migrate failed mid-run** — the site may be partially migrated. Options, in order of preference:
  1. Push a fix-forward (a patch or hook change that resolves the failure). Frappe Cloud will retry migrate.
  2. If fix-forward isn't fast, roll back to the previous deploy from the FC dashboard (Deploys → previous → "Deploy") **only if** no patches in this deploy made destructive changes you can't reverse.
  3. If patches dropped data and the rollback would re-introduce schema the data no longer fits, you're in a manual recovery — open the FC bench console and triage.
- **Site renders but workspace is empty / freezes** — almost always orphan workspace refs. Run the auto-purge logic in `dcr/setup.py` (see commit d5936c3).

## Don't

- Don't tell the user to "run `bench migrate`" — they cannot.
- Don't push directly with `--no-verify` to bypass hooks. If a hook fails, fix the underlying issue.
- Don't ship a patch you haven't read line-by-line — patches run against prod data on the next deploy.
- Don't combine a destructive schema change (column drop, doctype rename, data migration) with unrelated feature work in the same push. If something fails, you want a narrow blast radius.
