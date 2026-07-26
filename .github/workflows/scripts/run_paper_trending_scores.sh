#!/bin/sh
set -eu

exec sudo /usr/local/sbin/pwc-cron calculate_paper_trending_scores "$@"
