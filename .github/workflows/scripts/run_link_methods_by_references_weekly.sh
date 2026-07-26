#!/bin/sh
set -eu

exec sudo /usr/local/sbin/pwc-cron link_methods_by_references "$@"
