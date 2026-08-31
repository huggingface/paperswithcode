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
- Put persistence models in `backend/models/database.py` and schema changes in
  `backend/database/migrations/`.
- Put domain logic in the matching `backend/services/*_service.py`.
- Add the HTTP adapter in `backend/routers/` and register it in
  `backend/main.py`.
- Inject database sessions with `get_database_session`.
- Add focused tests under `backend/tests/`.

For scripts that mutate domain data, use the existing services where possible.
Run them with `uv run --env-file backend/keys.env …`.

## Frontend

- Keep routes in `frontend/src/App.tsx` and place new routes before the catch-all.
- Use `frontend/src/lib/api.ts` for backend calls and TanStack Query for server
  state.
- Reuse the components and design tokens under `frontend/src/components/`.
- Keep TypeScript strict and handle loading, empty, and error states.

## Cron and operations

Follow `.github/workflows/scripts/README.md` for cron jobs. Test a job with:

```bash
uv run --env-file backend/keys.env \
  .github/workflows/scripts/manage_cron.py test <job_name>
```

The VPS has about 4 GB of RAM: stream large inputs, use bounded batches, and
keep heavy work out of request handlers. Use `docs/deployment.md` only for an
explicit production release.
