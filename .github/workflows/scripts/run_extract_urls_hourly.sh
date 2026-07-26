#!/bin/sh
set -eu

exec sudo /usr/local/sbin/pwc-cron extract_urls "$@"
