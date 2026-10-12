# Development guide

Keep the implementation as the documentation. Put business rules in services,
keep routers thin, and let FastAPI's generated `/docs` describe the endpoint
contract.

## Local workflow

```bash
# Backend
uv run --env-file backend/keys.env backend/run_server.py

# Frontend
cd frontend && npm run dev

# Checks
cd frontend && npm run lint
uv run --env-file backend/keys.env pytest backend/tests -q
```

Use an isolated backend port for local testing. Do not rebuild the frontend or
restart the production services during routine development; `frontend/dist` is
served by nginx in production.

## Backend

- Define request and response models in bounded modules under `backend/models/`;
  preserve `backend/models/api.py` as the compatibility re-export surface.
- Put persistence models in bounded modules under `backend/models/database/`;
  preserve `backend.models.database` as the compatibility re-export surface.
  Put schema changes in `backend/database/migrations/`.
- Put domain logic in the matching `backend/services/*_service.py`.
- Add the HTTP adapter in `backend/routers/` and register it in
  `backend/main.py`.
- Inject database sessions with `get_database_session`.
- Add focused tests under `backend/tests/`. Subsystem suites live in their own
  package with explicit `harness.py` or `*harness.py` modules for shared
  builders; run only the suite you touched:

  | Subsystem | Targeted command |
  | --- | --- |
  | Chat sessions, turns, streaming, admission, qualification | `uv run pytest backend/tests/chat -q` |
  | Chat sandbox, executor, worker, broker | `uv run pytest backend/tests/chat_sandbox -q` |
  | Chat gateway: provider lifecycle, OpenAI Responses, Anthropic Messages, turn fence, catalog tools | `uv run pytest backend/tests/chat_gateway -q` |
  | Chat budgets and billing: direct OpenAI, OpenRouter, HF inference | `uv run pytest backend/tests/chat_budget -q` |
  | Chat title generation and its budget | `uv run pytest backend/tests/chat_title -q` |
  | Hosted MCP: research catalog, deployment, nginx contract | `uv run pytest backend/tests/mcp -q` |
  | Deployment, releases, nginx, host environment | `uv run pytest backend/tests/deployment -q` |
  | Evaluations, ranks, leaderboard badges, leaderboard syncs | `uv run pytest backend/tests/evaluation -q` |
  | CRON registry, schedules, health, dashboard, logs | `uv run pytest backend/tests/cron -q` |

For scripts that mutate domain data, use the existing services where possible.
Run them with `uv run --env-file backend/keys.env …`.

## Frontend

- Keep routes in `frontend/src/App.tsx` and place new routes before the catch-all.
- Use `frontend/src/lib/api.ts` for backend calls and TanStack Query for server
  state.
- Reuse the components and design tokens under `frontend/src/components/`.
- Keep TypeScript strict and handle loading, empty, and error states.

## Isolated nginx tests

Run nginx tests as an unprivileged user, including `nginx -t` configuration
checks. On this host, nginx has absolute compiled-in temporary paths under
`/var/lib/nginx`. A separate port, config file, or `-p` prefix does not override
those paths. A root-owned test master can change their ownership to its worker
user and prevent production workers from buffering requests. This caused paper
chat requests and transcript saves to fail with HTTP 500 on September 15, 2026.

Prefer a disposable container or an unprivileged development account. Explicitly
isolate all five temporary paths (`client_body`, `proxy`, `fastcgi`, `uwsgi`,
and `scgi`), plus logs, PID, and lock files. Do not include the host's nginx
configuration or proxy test traffic to production services.

The following Bash script runs a minimal isolated server. First use `ss -ltn`
to confirm that port 18181 is free, or choose another unused unprivileged port
in the example. Run the script without `sudo`; its root check also protects
the configuration-check step.

```bash
#!/usr/bin/env bash
set -eu
if [ "$(id -u)" -eq 0 ]; then
    echo "Run nginx tests as an unprivileged user." >&2
    exit 1
fi

nginx_test_dir=$(mktemp -d /tmp/pwc-nginx-test.XXXXXXXX)
mkdir "$nginx_test_dir/body" "$nginx_test_dir/proxy" \
    "$nginx_test_dir/fastcgi" "$nginx_test_dir/uwsgi" "$nginx_test_dir/scgi"
cat > "$nginx_test_dir/nginx.conf" <<EOF
worker_processes 1;
pid $nginx_test_dir/nginx.pid;
lock_file $nginx_test_dir/nginx.lock;
error_log $nginx_test_dir/error.log notice;
events { worker_connections 64; }
http {
    access_log $nginx_test_dir/access.log;
    client_body_temp_path $nginx_test_dir/body;
    proxy_temp_path $nginx_test_dir/proxy;
    fastcgi_temp_path $nginx_test_dir/fastcgi;
    uwsgi_temp_path $nginx_test_dir/uwsgi;
    scgi_temp_path $nginx_test_dir/scgi;
    server {
        listen 127.0.0.1:18181;
        location / { return 200 "isolated nginx test\n"; }
    }
}
EOF

echo "Test files and logs: $nginx_test_dir"
nginx -p "$nginx_test_dir/" -c "$nginx_test_dir/nginx.conf" \
    -e "$nginx_test_dir/error.log" -t
nginx -p "$nginx_test_dir/" -c "$nginx_test_dir/nginx.conf" \
    -e "$nginx_test_dir/error.log" -g 'daemon off;'
```

From another terminal, check `curl --noproxy '*' http://127.0.0.1:18181/`.
Stop this foreground instance with Ctrl-C. Remove only its printed temporary
directory after the process has exited. Never use `pkill nginx`, the production
PID file, or a service restart to clean up a test.

The minimal `return` endpoint checks routing, not request-body buffering. For
tests of proxy or gateway changes, use an isolated upstream that consumes the
request body and send a synthetic body of at least 100 KiB. Verify that it
reaches the upstream and that production temporary-directory ownership remains
unchanged. Small GET health checks do not exercise this failure mode.

## Cron and operations

Follow `.github/workflows/scripts/README.md` for cron jobs. Test a job with:

```bash
uv run --env-file backend/keys.env \
  .github/workflows/scripts/manage_cron.py test <job_name>
```

The VPS has about 4 GB of RAM: stream large inputs, use bounded batches, and
keep heavy work out of request handlers. Use `docs/deployment.md` only for an
explicit production release.
