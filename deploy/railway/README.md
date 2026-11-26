# Deploying on Railway

The repository root holds a `Dockerfile` and `railway.toml`, so Railway builds this fork of
Odoo 18.0 Community together with the add-ons in `catering_addons/`.

## One-time setup

1. In Railway, create a project and add a **PostgreSQL** service.
2. Add a service from this GitHub repository, branch `18.0`.
3. On the Odoo service, add a **volume** mounted at `/var/lib/odoo` (attachments and sessions live there).
4. Set these variables on the Odoo service:

| Variable | Value |
| --- | --- |
| `PGHOST` | `${{Postgres.PGHOST}}` |
| `PGPORT` | `${{Postgres.PGPORT}}` |
| `PGUSER` | `${{Postgres.PGUSER}}` |
| `PGPASSWORD` | `${{Postgres.PGPASSWORD}}` |
| `PGDATABASE` | `${{Postgres.PGDATABASE}}` |
| `ODOO_ADMIN_PASSWD` | a long random string (master password; keep it secret) |

Optional: `ODOO_LANG` (default `vi_VN`), `ODOO_MODULES` (default `catering`),
`ODOO_WORKERS` (default `0`, threaded mode), `ODOO_UPDATE_MODULES` (e.g. `job_order,catering`
to upgrade modules on the next deploy; remove it afterwards).

5. Generate a public domain for the service (Settings > Networking).

## What happens on deploy

* First boot: the entrypoint installs `catering` (and its dependencies) without demo data,
  loads Vietnamese, sets the main company to Vietnam (VND, Vietnamese chart of accounts) and
  configures the catering accounts. This takes a few minutes; the health check waits up to 15.
* Later boots: the server starts directly. Set `ODOO_UPDATE_MODULES` when a deploy changes
  module data or fields.

Log in with `admin` / `admin` the first time and **change the password immediately**
(user menu > Preferences > Account Security). English stays available per user under
Preferences > Language.
