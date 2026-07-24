---
name: pwc-cli
description: Use the standalone read-only Papers With Code CLI for bounded public paper and benchmark research.
---

# Standalone Papers With Code CLI

This public client is anonymous and read-only. Run `pwc --help` or nested help
for the current bounded flags. Use compact output by default; add `--json` only
for programmatic filtering, joining, or transformation.

```bash
pwc search "small vision language models" --limit 10
pwc paper info 2501.01234 --include-resources
pwc paper read 2501.01234
pwc paper list --conference CVPR --page-size 20
pwc paper recent --limit 10
pwc paper trending --limit 20
pwc paper related 2501.01234 --limit 4
pwc paper lineage list 2501.01234
pwc benchmark list --task image-classification
pwc version
```

The standalone parser contains no authentication, mutation, ingestion,
publication, image, CRON, embedding, or infrastructure commands. Do not
substitute repository-maintenance commands into a public or sandbox workflow.
