#!/bin/sh
set -eu

# Compatibility entrypoint. All production jobs run through the installed,
# release-pinned allowlist and never through this checkout.
exec sudo /usr/local/sbin/pwc-cron update_citations "$@"
