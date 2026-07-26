#!/bin/sh
set -eu

exec sudo /usr/local/sbin/pwc-cron update_github_stars "$@"
