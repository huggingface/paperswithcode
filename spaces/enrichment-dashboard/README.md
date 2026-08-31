---
title: PWC Daily Enrichment Dashboard
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
private: true
---

# PWC Daily Enrichment Dashboard

Read-only day-by-day view of Papers With Code HF daily-paper curation.

The Space reads `snapshot.json` from the private dataset configured by the
`SNAPSHOT_REPO_ID` Space variable. `HF_TOKEN` is used only to download that
snapshot.
