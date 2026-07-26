#!/bin/sh
set -eu

exec sudo /usr/local/sbin/pwc-cron refresh_paper_embeddings "$@"
