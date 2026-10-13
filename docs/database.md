# Database Access & Security

## Overview

- Engine: PostgreSQL 16 (`paperswithcode_hf` database)
- Production application role: `paperswithcode_user`
- Staging role: `pwc_staging` (read-only `public`, owner of writable
  `staging` state through `search_path=staging,public`)
- Backup role: `pwc_backup` (`pg_read_all_data`, no application writes)
- Superuser (system managed): `postgres`
- Deployed connection settings are loaded from
  `/etc/paperswithcode/{production,staging}.env`; `backend/keys.env` is for
  explicit local development only.

Use `uv run --env-file backend/keys.env …` for any script that touches the database.

Production and staging share the live research catalog in `public`. Private
staging chat, bookmark, preference, pending-edit, and workflow state lives in
`staging` and is owned by the staging environment. Never grant `pwc_staging`
write access to `public`, and never qualify staging by reusing the production
application role.

Read-only isolation audit:

```bash
sudo python deploy/audit_staging_db.py
```

The audit proves catalog reads, rejects a catalog update, performs
transaction-rolled-back staging state writes, and verifies both search paths.

## Local Development Access

```bash
# Open psql as the application user
PGPASSWORD=$(grep PWC_DB_PASSWORD backend/keys.env | cut -d= -f2) \
  psql -h localhost -U paperswithcode_user -d paperswithcode_hf

# From Python
from backend.database.connection import get_database_session

with get_database_session() as db:
    papers = db.execute("SELECT id, arxiv_id FROM papers LIMIT 5").all()
```

## Remote Access (Whitelist Required)

The server allows remote connections only for explicit IPs using `scripts/manage_postgres_access.sh`.

```bash
# Add your public IP (requires sudo)
sudo ./scripts/manage_postgres_access.sh add 84.198.172.145 paperswithcode_user paperswithcode_hf

# Remove an IP
sudo ./scripts/manage_postgres_access.sh remove 84.198.172.145

# List current entries
./scripts/manage_postgres_access.sh list
```

After whitelisting, connect with:

```
Host: 167.235.148.241
Port: 5432
DB:   paperswithcode_hf
User: paperswithcode_user
Pass: use the value from `backend/keys.env`
SSL:  Optional (both host and hostssl rules exist)
```

> Rotate passwords promptly if this instance contains sensitive data.

## Security Posture

- `pg_hba.conf` contains per-IP `host` and `hostssl` entries for whitelisted addresses.
- UFW blocks port 5432 for everything except approved IPs.
- PostgreSQL listens on all interfaces (`listen_addresses='*'`) to support the whitelist.
- Check status:

```bash
sudo ufw status | grep 5432
sudo -u postgres psql -c "SELECT * FROM pg_hba_file_rules;"
sudo netstat -tlnp | grep 5432
```

## Common Operations

```bash
# Inspect active sessions
sudo -u postgres psql -c "SELECT pid, usename, client_addr, query FROM pg_stat_activity;"

# One-off update (example: set method image URL)
PGPASSWORD="$PWC_DB_PASSWORD" psql -h localhost -U paperswithcode_user -d paperswithcode_hf \
  -c "UPDATE methods SET image_url = 'https://example.com/image.png' WHERE name ILIKE 'function calling';"

# Grant permissions after creating production catalog tables as postgres.
# Do not grant these to pwc_staging.
sudo -u postgres psql -d paperswithcode_hf -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO paperswithcode_user;"
sudo -u postgres psql -d paperswithcode_hf -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO paperswithcode_user;"
```

## Troubleshooting

| Issue | What to check |
| --- | --- |
| `permission denied for table …` | Table/sequence ownership; re-run GRANTs above. |
| `no pg_hba.conf entry` | Ensure your IP was added via the manage script and reload Postgres: `sudo systemctl reload postgresql`. |
| Connection refused | Confirm firewall rule exists and PostgreSQL is running: `sudo systemctl status postgresql`. |
| Password auth failed | Compare credentials with `backend/keys.env`; beware of stale `.pgpass`. |

## References

- Schema reference: `docs/DATABASE_SCHEMA_UML.md`
- Keyword automation scripts: `backend/database/{tasks_setup,methods_setup}/`
- Remote access helper: `scripts/manage_postgres_access.sh`
