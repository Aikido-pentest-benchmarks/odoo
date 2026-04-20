#!/bin/bash
set -euo pipefail

export EXTERNAL_URL="${EXTERNAL_URL:-http://127.0.0.1:54969}"

export PGHOST="${PGHOST:-db}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-odoo}"
export PGPASSWORD="${PGPASSWORD:-PgOd9mK4nQ8vR2wL6tY1cB5hF0jD3sA7eX9zK2pM}"
export PGDATABASE="${PGDATABASE:-odoo}"

until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
  sleep 1
done

needs_init=0
if ! psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
  "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ir_module_module'" \
  | grep -q 1; then
  needs_init=1
fi

if [[ "$needs_init" -eq 1 ]]; then
  python3 /opt/odoo/odoo-bin -c /etc/odoo/odoo.conf -d odoo -i base,web,mail --stop-after-init
fi

if ! psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
  "SELECT 1 FROM res_users WHERE login='internal.demo' LIMIT 1" 2>/dev/null | grep -q 1; then
  python3 /opt/odoo/odoo-bin shell -c /etc/odoo/odoo.conf -d odoo <<'PYTHON'
import os
external_url = os.environ.get("EXTERNAL_URL", "http://127.0.0.1:54969").rstrip("/")
admin_pw = "Odo0_ADM_k7Qx2mP9vL4nR8wT5bH1cF6jY3zA0eS"
internal_pw = "Odo0_INT_m3Kp8vR2wL6nQ9tY1cB5hF0jD4sA7eX"
portal_pw = "Odo0_POR_n8Qw2mK5vL9rT3yC7bH1fJ6dS0aE4xZ"
subsidiary_pw = "Odo0_SUB_p2M9kV5wL8nR3tY6cB1hF4jD7sA0eX"

icp = env["ir.config_parameter"].sudo()
icp.set_param("web.base.url", external_url)
icp.set_param("web.base.url.freeze", "True")

env.ref("base.user_admin").password = admin_pw

Users = env["res.users"].sudo()
Company = env["res.company"].sudo()

if not Users.search([("login", "=", "internal.demo")]):
    Users.create(
        {
            "name": "Internal Demo",
            "login": "internal.demo",
            "password": internal_pw,
            "group_ids": [(6, 0, [env.ref("base.group_user").id])],
        }
    )

if not Users.search([("login", "=", "portal.demo")]):
    Users.create(
        {
            "name": "Portal Demo",
            "login": "portal.demo",
            "password": portal_pw,
            "group_ids": [(6, 0, [env.ref("base.group_portal").id])],
        }
    )

main_co = env.ref("base.main_company")
subsidiary = Company.search([("name", "=", "Benchmark Subsidiary")], limit=1)
if not subsidiary:
    subsidiary = Company.create(
        {"name": "Benchmark Subsidiary", "parent_id": main_co.id}
    )

if not Users.search([("login", "=", "subsidiary.demo")]):
    Users.create(
        {
            "name": "Subsidiary Internal",
            "login": "subsidiary.demo",
            "password": subsidiary_pw,
            "company_id": subsidiary.id,
            "company_ids": [(6, 0, [subsidiary.id])],
            "group_ids": [(6, 0, [env.ref("base.group_user").id])],
        }
    )

env.cr.commit()
PYTHON
fi

exec python3 /opt/odoo/odoo-bin -c /etc/odoo/odoo.conf -d odoo
