---
name: remote-paper-curation
description: Safely curate one Papers With Code paper from a remote Hugging Face Job without direct database access.
---

# Remote Paper Curation

This Job has no PostgreSQL credentials. Never read `backend/keys.env`, run SQL,
or edit repository files. Fetch the job-scoped paper context with:

```bash
python jobs/curation_api.py context
```

Search existing task/method taxonomy with:

```bash
python jobs/curation_api.py taxonomy "image generation"
```

For every benchmark name found in an evaluation table, search the configured
leaderboards with:

```bash
python jobs/curation_api.py leaderboards "GenEval"
```

This returns the authorized task and dataset IDs, configured metrics, ranking
direction, canonical scale, harness support, and recent values for scale checks.
Try exact names and common spelling variants, but reject semantically different
datasets or splits even when their names are similar.

For `add-evals`, follow the conservative rules in `add-evals/SKILL.md`, but
write a JSON payload containing only `evaluations` (each has this job's
`paper_id`) and submit it with `python jobs/curation_api.py apply payload.json`.
Use only configured leaderboard IDs and exact metric names returned by the
`leaderboards` command; IDs from papers or web sources are not database IDs.
Evaluate every configured metric independently. When the source reports more
than one configured metric for the same task/dataset pair, submit one row per
metric (for example, both Word Accuracy and NED for CVTG), selecting the
paper's best eligible model variant for each metric.
Never invent IDs, create benchmark metadata, or import comparator rows. Submit
an empty evaluation list only when none of the paper's own results match a
configured leaderboard. The helper will report `no_changes`; do not describe
that outcome as an applied mutation.

For `enrich-paper`, preserve the existing task/method/link lists from context,
append only high-confidence additions, and submit an `enrich` payload with the
complete replacement list for each changed relation. Set `urls_extracted` only
when official artifacts were actually validated.

Finish with a concise audit report. The runner reports it to the VPS.
