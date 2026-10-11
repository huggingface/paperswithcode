# Hourly CRON Jobs

This directory contains CRON jobs that run hourly to keep the PapersWithCode database fresh and up-to-date.

## Active Jobs

### 1. Hot GitHub Trending (`update_hot_github_trending.py`)

This staging-ready job is intended to run every 15 minutes and own official
repositories linked to latest papers aged 0–30 days. It fetches up to 500
normalized owner/name groups with a 250-millisecond delay, writes snapshots,
scores only touched repositories, and immediately propagates composite scores
to their linked latest papers.

Hot repositories prefer a snapshot baseline at least 30 minutes old. During
the first hour after their first observed snapshot, a 15-minute baseline is
accepted. Negative velocity is clamped to zero and the ordinary α=0.75 EMA and
maximum-score safeguard remain in force.

`PWC_GITHUB_TOKEN_HOT` is optional. Without it, `PWC_GITHUB_TOKEN` is used and
the job preserves at least `PWC_GITHUB_RATE_LIMIT_RESERVE=500` calls.

```bash
sudo pwc-cron update_hot_github_trending --dry-run
pwc cron health update_hot_github_trending --strict --json
```

The workflow is currently manual-only. To activate production, separately
authorize installation of the checked-in deploy tooling from the exact
production SHA, deploy that SHA to production, confirm the installed
`pwc-cron` allowlist contains the command, and then add the `*/15` schedule in a
separately reviewed commit.

### 2. GitHub Stars Update (`update_github_stars.py`)

**Purpose**: Fetch current GitHub star counts from the GitHub API and store historical snapshots.

**Frequency**: Every hour (0 * * * *)

**What it does**:
- Fetches GitHub star counts for repositories linked to papers
- Stores historical snapshots in `repository_star_history` table
- Selects only fresh papers aged 31 days through 6 months
- Groups repositories by owner/name to avoid duplicate API calls
- Runs fresh and weekly queues concurrently with separate GitHub accounts

**Queue System**:
- **HOT**: 0–30 days, exclusively owned by the 15-minute job
- **FRESH** (`PWC_GITHUB_TOKEN`): 31 days–6 months, oldest update first
- **WEEKLY** (`GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE`): older and
  never-updated repositories, oldest update first, refreshed every 7 days

The 30-day boundary is intentionally fixed so hot selection, fresh exclusion,
and health queries cannot drift through environment configuration.

**Configuration**:
- Max updates: up to 2,500 fresh and 1,000 weekly repositories/hour
- API delay: 1 second between calls
- Memory threshold: 200MB minimum

**Run manually**:
```bash
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars
```

**Required environment variables**:
- `PWC_GITHUB_TOKEN`: GitHub API token for authentication
- `GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE`: token from a separate GitHub
  account, used only for the weekly/backfill queue

---

### 3. Trending Scores Calculation (`calculate_trending_scores.py`)

**Purpose**: Calculate EMA-based trending scores from historical GitHub star data.

**Frequency**: Every hour (30 * * * *) - offset by 30 minutes from stars update

**What it does**:
- Reads historical star snapshots from `repository_star_history`
- Calculates star velocity (stars gained per hour)
- Applies Exponential Moving Average (EMA) to smooth out fluctuations
- Updates `repositories.trending_score` field

**Algorithm**:
```python
# Calculate raw velocity
rawStarsPerHour = (currentStars - previousStars) / hoursSinceLastSync

# Apply EMA (α = 0.75)
trendingScore = 0.75 × rawStarsPerHour + 0.25 × previousTrendingScore
```

**Configuration**:
- Batch size: 500 repositories per batch
- Update threshold: 1 hour (only update if score is > 1 hour old)
- Alpha (smoothing factor): 0.75
- Minimum snapshot interval: 0.5 hours

**Run manually**:
```bash
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores
```

**No environment variables required** (reads from database only)

---

## Setup Instructions

### 1. Install in Crontab

```bash
# Edit crontab
crontab -e

# Add these lines (adjust paths as needed)
0 * * * * cd /root/python_projects/paperswithcode && /usr/bin/flock -n /tmp/github_stars.lock PYTHONPATH=.github/workflows /usr/bin/uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars >> /var/log/cron/github_stars.log 2>&1

30 * * * * cd /root/python_projects/paperswithcode && /usr/bin/flock -n /tmp/trending_scores.lock PYTHONPATH=.github/workflows /usr/bin/uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores >> /var/log/cron/trending_scores.log 2>&1
```

**Notes**:
- `flock -n` prevents overlapping runs (exits if already running)
- Offset by 30 minutes to avoid resource contention
- Logs are written to `/var/log/cron/` (create directory first)

### 2. Create Log Directory

```bash
sudo mkdir -p /var/log/cron
sudo chown $(whoami):$(whoami) /var/log/cron
```

### 3. Test Jobs Manually

```bash
# Test GitHub stars update
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.update_github_stars

# Test trending calculation
PYTHONPATH=.github/workflows uv run --env-file backend/keys.env python -m scripts.hourly.calculate_trending_scores
```

---

## Monitoring

### Check if Jobs are Running

```bash
# Check for running processes
ps aux | grep "update_github_stars\|calculate_trending"

# Check recent log entries
tail -f /var/log/cron/github_stars.log
tail -f /var/log/cron/trending_scores.log
```

### Verify Database Updates

```sql
-- Check recent star updates
SELECT owner, name, num_stars, num_stars_updated_at
FROM repositories
WHERE num_stars_updated_at >= NOW() - INTERVAL '1 hour'
ORDER BY num_stars_updated_at DESC
LIMIT 20;

-- Check recent trending score updates
SELECT owner, name, num_stars, trending_score, trending_score_updated_at
FROM repositories
WHERE trending_score_updated_at >= NOW() - INTERVAL '1 hour'
ORDER BY trending_score DESC
LIMIT 20;

-- Check snapshot creation
SELECT COUNT(*), MAX(snapshot_at)
FROM repository_star_history
WHERE snapshot_at >= NOW() - INTERVAL '1 hour';
```

---

## Performance Metrics

### Expected Performance (per hourly run)

**GitHub Stars Update**:
- Repositories processed: up to 2,500 fresh groups
- API calls: up to 2,500 on the shared token
- Snapshots stored: one per duplicate repository row in successful groups
- Runtime: ~50-55 minutes
- Memory usage: ~200-400MB

**Trending Calculation**:
- Repositories processed: ~500-1000
- Trending scores updated: ~500-1000
- Runtime: ~5-15 minutes
- Memory usage: ~200-300MB

### GitHub API Rate Limits

- **Limit**: 5,000 requests/hour (authenticated)
- **Maximum shared usage**: 2,500 fresh plus 4×500 hot calls/hour
- **Reserve**: At least 500 calls; queues stop rather than consume it
- **Rate handling**: Honor `Retry-After`; bounded retries for transient 5xx
- **Metrics**: `api_calls` counts physical HTTP attempts, including retries
- **Token**: Set `PWC_GITHUB_TOKEN` in `backend/keys.env`

---

## Troubleshooting

### Problem: "PWC_GITHUB_TOKEN not set"

**Solution**: Configure the credential through the appropriate environment
tooling. Production automation reads `/etc/paperswithcode/production-cron.env`;
never put production tokens in command arguments or the checkout.

### Problem: "Rate limit hit"

**Solution**:
- Wait for rate limit to reset (checks hourly)
- Reduce `max_updates` in configuration
- Increase `delay` between API calls

### Problem: "Low memory - stopping"

**Solution**:
- Script automatically stops when < 200MB available
- Increase VPS memory if consistently hitting limit
- Reduce `batch_size` or `max_updates` in configuration

### Problem: "No more repositories to process"

**Solution**: This is normal! It means all repositories have been updated according to their priority thresholds.

### Problem: Trending scores not updating

**Solution**:
1. Check if star update script is running: `tail -f /var/log/cron/github_stars.log`
2. Verify snapshots are being created:
   ```sql
   SELECT COUNT(*) FROM repository_star_history
   WHERE snapshot_at >= NOW() - INTERVAL '24 hours';
   ```
3. Check for errors in trending log: `tail -f /var/log/cron/trending_scores.log`
4. Ensure repositories have at least 2 snapshots (needed for velocity calculation)

---

## Architecture Notes

### Why keep independent full reconciliation jobs?

**Benefits**:
1. **Separation of concerns**: API fetching vs. mathematical calculations
2. **Independent failures**: GitHub API issues don't break trending calculations
3. **Flexible scheduling**: Can run at different frequencies
4. **Scalability**: Trending calculation can process ALL repos, not just recently fetched

**Workflow**:
```
┌─────────────────────────────────────────────────────────────┐
│                    Hourly CRON Jobs                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────┐    │
│  │  update_github_stars.py (every hour, :00)          │    │
│  │  ↓                                                  │    │
│  │  1. Fetch GitHub star counts via API               │    │
│  │  2. Update repositories.num_stars                  │    │
│  │  3. Store snapshot in repository_star_history      │    │
│  └────────────────────────────────────────────────────┘    │
│                           ↓                                  │
│           (Historical data accumulates in DB)               │
│                           ↓                                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │  calculate_trending_scores.py (every hour, :30)    │    │
│  │  ↓                                                  │    │
│  │  1. Read snapshots from repository_star_history    │    │
│  │  2. Calculate star velocity (stars/hour)           │    │
│  │  3. Apply EMA smoothing (α=0.75)                   │    │
│  │  4. Update repositories.trending_score             │    │
│  └────────────────────────────────────────────────────┘    │
│                           ↓                                  │
│              (Trending scores available for API)            │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Migration from Old Scripts

If you're migrating from the previous two-script setup:

**Old scripts** (deprecated):
- ~~`update_github_stars_optimized.py`~~ → Replaced by `update_github_stars.py`
- ~~`update_github_stars_trending.py`~~ → Functionality split into both new scripts

**What changed**:
1. **Combined fetching**: Single script handles both recent and regular papers
2. **Pure calculation**: Trending calculation is now separate and database-only
3. **Better efficiency**: No duplicate API calls, cleaner architecture
4. **EMA-based**: Uses Exponential Moving Average instead of raw velocity

**Migration steps**: See `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md`

---

## Additional Resources

- **Detailed guide**: `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md`
- **Database schema**: `backend/database/migrations/add_trending_score.sql`
- **Service methods**: `backend/services/repository_service.py`
- **API models**: `backend/models/papers.py` (Repository model includes trending_score)
