# Proposed operator response

I have not run any commands or inspected the hosts, so I cannot truthfully claim
the exact production/staging release IDs or CRON target yet. The repository
guidance says production is normally the backend on port 8000, staging is
normally the backend on port 8001, nginx serves each environment's
`current/frontend-dist`, and releases are immutable under `/srv/paperswithcode`.
Those are expected conventions, not a live-state finding.

The following sequence is read-only. It does not deploy, restart, reload, stop,
roll back, or alter a symlink. Run it on the server and retain the complete
output; secrets should be redacted before sharing. It establishes:

1. the release directory currently selected by each environment;
2. the backend executable, working directory, and unit definition actually in
   use;
3. the frontend directory nginx currently serves;
4. which immutable release directories and explicit rollback targets exist;
5. whether scheduled work runs from an immutable release, a mutable checkout,
   or GitHub Actions.

## Read-only command sequence

```bash
# 1. Supported consolidated status view. Do not follow this with deploy/rollback.
sudo pwc-status

# 2. Resolve the environment selectors without changing them.
sudo find /srv/paperswithcode -maxdepth 3 -type l \
  \( -name current -o -name previous \) -printf '%p -> %l\n'
sudo find /srv/paperswithcode -maxdepth 3 -type l \
  \( -name current -o -name previous \) -exec readlink -f {} \;

# 3. Confirm the running backend processes and their release paths.
systemctl status paperswithcode-backend@production --no-pager
systemctl status paperswithcode-backend@staging --no-pager
systemctl show paperswithcode-backend@production \
  -p ActiveState -p SubState -p MainPID -p ExecStart -p WorkingDirectory \
  -p FragmentPath -p DropInPaths
systemctl show paperswithcode-backend@staging \
  -p ActiveState -p SubState -p MainPID -p ExecStart -p WorkingDirectory \
  -p FragmentPath -p DropInPaths

# 4. Confirm the loaded unit definitions and nginx frontend roots.
systemctl cat paperswithcode-backend@production
systemctl cat paperswithcode-backend@staging
sudo nginx -T 2>&1 | rg -n \
  'server_name|listen|root |alias |proxy_pass|paperswithcode|frontend-dist'

# 5. Enumerate immutable release directories and their metadata.
# This lists only; it does not choose or activate a release.
sudo find /srv/paperswithcode -maxdepth 3 -mindepth 1 -type d \
  -printf '%TY-%Tm-%TdT%TH:%TM:%TS %p\n' | sort
sudo find /srv/paperswithcode -maxdepth 4 -type f \
  \( -name 'REVISION' -o -name 'VERSION' -o -name 'manifest.json' \
     -o -name 'release.json' \) -print

# 6. Discover host-managed schedules and show their exact execution paths.
systemctl list-timers --all --no-pager | rg -i 'paperswithcode|pwc|cron'
systemctl list-unit-files --type=timer --type=service --no-pager \
  | rg -i 'paperswithcode|pwc|cron'
sudo rg -n --no-messages \
  'paperswithcode|/srv/paperswithcode|pwc' \
  /etc/systemd/system /usr/lib/systemd/system /etc/cron.d /etc/crontab
crontab -l
sudo crontab -l

# 7. Inspect repository-defined scheduled workflows. This is source inspection,
# not proof that a particular workflow is enabled in GitHub.
rg -n 'schedule:|cron:|actions/checkout|ref:|working-directory:|pwc|/srv/' \
  .github/workflows
```

If step 6 identifies specific timer/service units, inspect each discovered unit
with `systemctl cat <exact-unit-name>` and
`systemctl show <exact-unit-name> -p ExecStart -p WorkingDirectory -p EnvironmentFiles`.
Do not guess unit names and do not invoke `start`, `stop`, `restart`, `reload`,
`enable`, `disable`, `daemon-reload`, `pwc-deploy`, or `pwc-rollback`.

## How to report the result

Use resolved paths, not just symlink text:

```text
Production
- selected release: <readlink -f result>
- backend: <active/inactive>; PID <pid>; ExecStart <value>
- frontend: <nginx root/alias>

Staging
- selected release: <readlink -f result>
- backend: <active/inactive>; PID <pid>; ExecStart <value>
- frontend: <nginx root/alias>

Rollback
- production explicit previous target: <resolved path or "none">
- staging explicit previous target: <resolved path or "none">
- other immutable releases present: <paths>
- rollback readiness: <confirmed only if the supported status output identifies
  a valid target; otherwise "candidate exists, compatibility not yet proven">

CRON
- scheduler: <systemd timer / host cron / GitHub Actions / combination>
- execution source: <absolute WorkingDirectory/ExecStart or workflow ref>
- release-pinned: <yes/no/mixed>
- evidence: <unit, crontab entry, or workflow and relevant ref>
```

“Release-pinned” should be reported **yes** only when every active scheduled
command resolves into one immutable release directory (or a workflow explicitly
pins an immutable commit SHA). A `current` symlink, mutable repository checkout,
default-branch GitHub Actions checkout, unpinned container tag, or path omitted
from the evidence is not release-pinned. If different schedulers use different
sources, report **mixed** and list each one separately.

The existence of an older release directory alone does not prove it is safe to
roll back: database compatibility and the supported `pwc-status` rollback view
must also agree. This request authorizes inspection only, so no rollback should
be attempted.
