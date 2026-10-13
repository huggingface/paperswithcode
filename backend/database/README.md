# backend/database

Connection setup, schema migrations, and the few data scripts that are still
imported by services, CRON jobs, tests, or skills. Access rules and roles live
in [`docs/database.md`](../../docs/database.md); the schema reference is
[`docs/DATABASE_SCHEMA_UML.md`](../../docs/DATABASE_SCHEMA_UML.md).

- `connection.py`, `logging_config.py`: engine/session setup and script logging.
- `migrations/`: schema and data migrations (see its README).
- `paper_merge.py`: shared paper de-duplication used by imports and services.
- `import_entity_image.py`, `validate_evaluation_metrics.py`: tools used by the
  catalog skills under `.agents/skills/`.
- `*_setup/`: reusable linkers and importers (`tasks_setup/link_papers_by_task_keywords.py`,
  `methods_setup/link_papers_by_source_citations.py`,
  `repos_and_pages_setup/batch_extract.py`, `organizations_setup/organizations.py`, …)
  plus the example importers the skills cite.

New one-off catalog changes belong in a migration or go through the skills, not
in a new script here. Run any script with
`uv run --env-file backend/keys.env python -m backend.database.<module>`.
