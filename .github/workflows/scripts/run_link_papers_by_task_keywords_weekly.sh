#!/bin/sh
set -eu

exec sudo /usr/local/sbin/pwc-cron link_papers_by_task_keywords "$@"
