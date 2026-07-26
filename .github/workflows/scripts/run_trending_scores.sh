#!/bin/sh
set -eu

exec sudo /usr/local/sbin/pwc-cron calculate_trending_scores "$@"
