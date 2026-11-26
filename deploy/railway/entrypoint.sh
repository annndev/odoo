#!/usr/bin/env bash
# Builds odoo.conf from Railway variables, initialises the database on first boot, then serves Odoo.
set -euo pipefail

: "${PGHOST:?Set PGHOST (reference the Railway Postgres service variables)}"
: "${PGUSER:?Set PGUSER}"
: "${PGPASSWORD:?Set PGPASSWORD}"
: "${ODOO_ADMIN_PASSWD:?Set ODOO_ADMIN_PASSWD (master password for database management)}"

PGPORT="${PGPORT:-5432}"
ODOO_DB="${ODOO_DB:-${PGDATABASE:-odoo}}"
ODOO_MODULES="${ODOO_MODULES:-catering}"
ODOO_LANG="${ODOO_LANG:-vi_VN}"
ODOO_WORKERS="${ODOO_WORKERS:-0}"
DATA_DIR="${ODOO_DATA_DIR:-/var/lib/odoo}"
CONF=/tmp/odoo.conf
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"

mkdir -p "$DATA_DIR"

cat > "$CONF" <<CONF
[options]
addons_path = ${ODOO_DIR}/addons,${ODOO_DIR}/odoo/addons,${ODOO_DIR}/catering_addons
data_dir = ${DATA_DIR}
admin_passwd = ${ODOO_ADMIN_PASSWD}
db_host = ${PGHOST}
db_port = ${PGPORT}
db_user = ${PGUSER}
db_password = ${PGPASSWORD}
db_name = ${ODOO_DB}
dbfilter = ^${ODOO_DB}\$
list_db = False
proxy_mode = True
http_port = ${PORT:-8069}
workers = ${ODOO_WORKERS}
max_cron_threads = 1
limit_time_cpu = 600
limit_time_real = 1200
without_demo = all
CONF

export PGPASSWORD
installed=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$ODOO_DB" -tAc \
    "SELECT 1 FROM ir_module_module WHERE name = 'catering' AND state = 'installed'" 2>/dev/null || true)

if [ "$installed" != "1" ]; then
    echo "First boot: installing ${ODOO_MODULES} into ${ODOO_DB} with ${ODOO_LANG}"
    python3 "${ODOO_DIR}/odoo-bin" -c "$CONF" -d "$ODOO_DB" -i "$ODOO_MODULES" \
        --load-language="$ODOO_LANG" --stop-after-init
elif [ -n "${ODOO_UPDATE_MODULES:-}" ]; then
    echo "Updating ${ODOO_UPDATE_MODULES}"
    python3 "${ODOO_DIR}/odoo-bin" -c "$CONF" -d "$ODOO_DB" -u "$ODOO_UPDATE_MODULES" --stop-after-init
fi

exec python3 "${ODOO_DIR}/odoo-bin" -c "$CONF" "$@"
