"""AI conference deadlines: the database is the source of truth.

The /ai-deadlines page reads ``conferences`` + ``conference_deadlines``. This
module owns everything that writes those deadline rows:

* parsing helpers shared by every writer (timezones, local deadline instants,
  slugs), originally from the legacy ai-deadlines YAML importer;
* the legacy YAML import itself (one-time catch-up from huggingface/ai-deadlines);
* series snapshots handed to the off-box research agent, and the priority order
  in which scheduled sweeps research them;
* a deterministic, guarded writer for the agent's change sets. It never deletes
  deadlines, never edits past editions or past deadlines, requires source URLs,
  and records every applied change with before/after values in the catalog
  mutation audit ledger;
* explicit admin edits through the API, which may replace an edition's list;
* the freshness metrics shown on the CRON dashboard.

A conference *series* is the slug prefix shared by its yearly editions, e.g.
``cvpr`` for ``cvpr-2026`` and ``cvpr-2027``.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from backend.models.database import Conference, ConferenceDeadline
from backend.services.catalog_mutation_service import CatalogMutationService

logger = logging.getLogger(__name__)

AOE = timezone(timedelta(hours=-12))

# Timezone abbreviations not covered by IANA / offset parsing.
TZ_ABBREVIATIONS = {
    "AOE": -12,  # Anywhere on Earth
    "PST": -8,
    "PDT": -7,
    "EST": -5,
    "EDT": -4,
}

# Deprecated / non-canonical IANA names seen in the source data.
TZ_IANA_ALIASES = {
    "Russia/Moscow": "Europe/Moscow",
}

# Legacy single-field YAML deadlines mapped to (type, default label).
LEGACY_DEADLINE_FIELDS = [
    ("abstract_deadline", "abstract", "Abstract Submission"),
    ("deadline", "submission", "Paper Submission"),
    ("commitment_deadline", "commitment", "Commitment"),
    ("review_release_date", "review_release", "Reviews Released"),
    ("rebuttal_period_start", "rebuttal_start", "Rebuttal Period Start"),
    ("rebuttal_period_end", "rebuttal_end", "Rebuttal Period End"),
    ("final_decision_date", "final_decision", "Final Decision"),
]

# Deadline types the research agent may emit (the admin API accepts any
# snake_case type, matching legacy rows such as ``author_response``).
AGENT_DEADLINE_TYPES = (
    "abstract",
    "paper",
    "submission",
    "supplementary",
    "registration",
    "commitment",
    "review_release",
    "rebuttal_start",
    "rebuttal_end",
    "rebuttal_and_revision",
    "notification",
    "final_decision",
    "camera_ready",
)

DEADLINE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
LOCAL_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$")
SERIES_SLUG_RE = re.compile(r"^(?P<series>[a-z0-9-]+?)-(?P<year>\d{4})$")

# A deadline moved by more than this is far likelier a wrong year or edition
# than an extension; the agent must not apply it without a human.
MAX_DEADLINE_SHIFT = timedelta(days=120)

# Series held every other year; most have too little history to detect it.
BIENNIAL_SERIES = ("iccv", "eccv")

# Sweep selection windows.
WEEKLY_UPCOMING_WINDOW = timedelta(days=120)
WEEKLY_EXPECTED_NEXT_WINDOW = timedelta(days=240)
DAILY_IMMINENT_WINDOW = timedelta(days=21)
DAILY_EXPECTED_NEXT_WINDOW = timedelta(days=45)

AGENT_ACTOR = {
    "source": "cron",
    "hf_subject": "system:conference-deadline-agent",
    "username": "conference-deadline-agent",
    "role": "admin",
}


class DeadlineValidationError(ValueError):
    """A deadline or edition edit failed validation."""


# --- Parsing ----------------------------------------------------------------


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def edition_slug(series: str, year: int) -> str:
    return f"{series}-{year}"


def series_of(slug: str) -> Optional[str]:
    match = SERIES_SLUG_RE.match(slug or "")
    return match.group("series") if match else None


def resolve_timezone(raw: Optional[str]) -> Optional[timezone | ZoneInfo]:
    """Resolve a source timezone string, or None when it is not recognised."""
    if not raw:
        return None
    # Normalise unicode dashes (e.g. ``UTC–12:00``) to ASCII hyphen.
    cleaned = raw.strip().replace("–", "-").replace("—", "-")
    cleaned = cleaned.replace("−", "-")

    upper = cleaned.upper()
    if upper in TZ_ABBREVIATIONS:
        return timezone(timedelta(hours=TZ_ABBREVIATIONS[upper]))
    if upper in ("UTC", "GMT"):
        return timezone(timedelta(0))

    offset_match = re.fullmatch(
        r"(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?", upper
    )
    if offset_match:
        sign = -1 if offset_match.group(1) == "-" else 1
        hours = int(offset_match.group(2))
        minutes = int(offset_match.group(3) or 0)
        if hours > 14 or minutes >= 60:
            return None
        return timezone(sign * timedelta(hours=hours, minutes=minutes))

    try:
        return ZoneInfo(TZ_IANA_ALIASES.get(cleaned, cleaned))
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return None


def parse_timezone(raw: Optional[str]) -> timezone | ZoneInfo:
    """Lenient legacy parsing: unknown or missing timezones default to AoE."""
    tzinfo = resolve_timezone(raw)
    if tzinfo is None:
        if raw:
            logger.warning("unknown timezone %r, defaulting to AoE (UTC-12)", raw)
        return AOE
    return tzinfo


def canonical_timezone(raw: str) -> str:
    """Validate a timezone for new writes; Anywhere on Earth is spelled ``AoE``."""
    cleaned = (raw or "").strip()
    compact = cleaned.upper().replace(" ", "").replace("−", "-")
    compact = compact.replace("–", "-")
    if compact in {"AOE", "UTC-12", "UTC-12:00", "GMT-12"}:
        return "AoE"
    if compact.startswith(("UTC+12", "GMT+12")):
        # Agents confuse AoE with UTC+12; a real UTC+12 deadline needs a human.
        raise DeadlineValidationError(
            f"ambiguous timezone {raw!r}: write AoE for Anywhere on Earth"
        )
    if resolve_timezone(cleaned) is None:
        raise DeadlineValidationError(f"unknown timezone {raw!r}")
    return cleaned


def parse_deadline_instant(date_str: Any, tz_str: Optional[str]) -> Optional[datetime]:
    """Parse a naive local date string in its timezone and return a UTC datetime."""
    if not date_str:
        return None
    raw = str(date_str).strip()
    if not raw or raw.upper() == "TBD":
        return None

    naive: Optional[datetime] = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if naive is None:
        logger.warning("could not parse deadline date %r, skipping", date_str)
        return None
    return naive.replace(tzinfo=parse_timezone(tz_str)).astimezone(timezone.utc)


def local_deadline_text(deadline_at: datetime, tz_str: Optional[str]) -> str:
    """Render a stored UTC instant back in its declared timezone."""
    return deadline_at.astimezone(parse_timezone(tz_str)).strftime("%Y-%m-%d %H:%M:%S")


def coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def join_location(city: Optional[str], country: Optional[str]) -> Optional[str]:
    return ", ".join([p for p in (city, country) if p]) or None


# --- Legacy YAML import (huggingface/ai-deadlines) -----------------------------


def build_yaml_deadlines(block: dict) -> list[dict]:
    """Mirror ai-deadlines getAllDeadlines: new list + legacy fields, deduped."""
    conf_tz = block.get("timezone")
    collected: list[dict] = []
    seen_types: set[str] = set()

    for entry in block.get("deadlines") or []:
        if not isinstance(entry, dict):
            continue
        dtype = entry.get("type")
        collected.append(
            {
                "type": dtype,
                "label": entry.get("label"),
                "date": entry.get("date"),
                "timezone": entry.get("timezone") or conf_tz,
            }
        )
        if dtype:
            seen_types.add(dtype)

    for yaml_field, dtype, label in LEGACY_DEADLINE_FIELDS:
        if block.get(yaml_field) and dtype not in seen_types:
            collected.append(
                {
                    "type": dtype,
                    "label": label,
                    "date": block.get(yaml_field),
                    "timezone": conf_tz,
                }
            )
            seen_types.add(dtype)

    # Resolve instants and dedupe by absolute time.
    resolved: list[dict] = []
    seen_instants: set[datetime] = set()
    for item in collected:
        instant = parse_deadline_instant(item["date"], item["timezone"])
        if instant is None or instant in seen_instants:
            continue
        seen_instants.add(instant)
        resolved.append(
            {
                "type": item["type"],
                "label": item["label"],
                "deadline_at": instant,
                "timezone": item["timezone"],
            }
        )
    return resolved


def upsert_yaml_conference(db: Session, block: dict) -> Optional[Conference]:
    title = (block.get("title") or "").strip()
    year = block.get("year")
    if not title or not year:
        logger.warning("skipping block missing title/year: %s", block.get("id"))
        return None

    slug = edition_slug(slugify(title), int(year))
    city = block.get("city") or None
    country = block.get("country") or None
    location = join_location(city, country)
    tags = [str(t) for t in (block.get("tags") or []) if t]
    tier = block.get("era_rating") or None
    url = block.get("link") or None
    venue = block.get("venue") or None
    start_date = coerce_date(block.get("start"))
    end_date = coerce_date(block.get("end"))

    conference = db.query(Conference).filter(Conference.slug == slug).first()
    if conference is None:
        conference = Conference(
            name=f"{title} {year}",
            slug=slug,
            short_name=title,
            year=int(year),
            url=url,
            start_date=start_date,
            end_date=end_date,
            venue=venue,
            location=location,
            tier=tier,
            tags=tags or None,
            country=country,
            city=city,
        )
        db.add(conference)
        db.flush()
    else:
        # Deadline feature owns these columns; always refresh them.
        conference.tier = tier
        conference.tags = tags or None
        conference.country = country
        conference.city = city
        # Fill in metadata only when missing so curated proceedings data
        # (descriptions, hero images, hf_url, etc.) is never clobbered.
        conference.url = conference.url or url
        conference.venue = conference.venue or venue
        conference.location = conference.location or location
        conference.start_date = conference.start_date or start_date
        conference.end_date = conference.end_date or end_date
    return conference


def import_yaml_directory(db: Session, data_dir: Path, dry_run: bool) -> dict[str, int]:
    """Import every ``*.yml`` file, replacing each imported edition's deadlines."""
    stats = {
        "files": 0,
        "blocks": 0,
        "conferences_upserted": 0,
        "deadlines_added": 0,
        "blocks_no_deadlines": 0,
        "skipped": 0,
    }
    for yaml_file in sorted(data_dir.glob("*.yml")):
        stats["files"] += 1
        with open(yaml_file, "r") as handle:
            blocks = yaml.safe_load(handle) or []
        if not isinstance(blocks, list):
            continue

        for block in blocks:
            if not isinstance(block, dict):
                continue
            stats["blocks"] += 1

            deadlines = build_yaml_deadlines(block)
            if not deadlines:
                stats["blocks_no_deadlines"] += 1
                continue
            if dry_run:
                stats["conferences_upserted"] += 1
                stats["deadlines_added"] += len(deadlines)
                continue

            conference = upsert_yaml_conference(db, block)
            if conference is None:
                stats["skipped"] += 1
                continue
            stats["conferences_upserted"] += 1

            db.query(ConferenceDeadline).filter(
                ConferenceDeadline.conference_id == conference.id
            ).delete()
            for item in deadlines:
                db.add(
                    ConferenceDeadline(
                        conference_id=conference.id,
                        deadline_type=item["type"],
                        label=item["label"],
                        deadline_at=item["deadline_at"],
                        timezone=item["timezone"],
                    )
                )
                stats["deadlines_added"] += 1

        if not dry_run:
            db.commit()
    return stats


# --- Series snapshots -----------------------------------------------------------


@dataclass
class DeadlineState:
    id: Optional[int]
    type: Optional[str]
    label: Optional[str]
    deadline_at: datetime
    timezone: Optional[str]


@dataclass
class EditionState:
    slug: str
    year: int
    conference_id: Optional[int] = None
    short_name: Optional[str] = None
    url: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    venue: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    location: Optional[str] = None
    tier: Optional[str] = None
    tags: Optional[list[str]] = None
    deadlines: list[DeadlineState] = field(default_factory=list)

    def is_past(self, today: date) -> bool:
        reference = self.end_date or self.start_date
        if reference is not None:
            return reference <= today
        if self.deadlines:
            return self.year < today.year and all(
                d.deadline_at.date() < today for d in self.deadlines
            )
        return False


@dataclass
class SeriesState:
    series: str
    title: str
    tier: Optional[str]
    tags: Optional[list[str]]
    editions: list[EditionState]

    def edition(self, year: int) -> Optional[EditionState]:
        return next((e for e in self.editions if e.year == year), None)

    @property
    def deadline_editions(self) -> list[EditionState]:
        return [e for e in self.editions if e.deadlines]

    def next_deadline(self, now: datetime) -> Optional[datetime]:
        upcoming = [
            d.deadline_at
            for e in self.editions
            for d in e.deadlines
            if d.deadline_at > now
        ]
        return min(upcoming) if upcoming else None

    def cadence_years(self) -> int:
        """2 for the known biennial series (ICCV, ECCV), else 1.

        Not inferred from year gaps: one skipped or missing edition would make
        an annual series look biennial.
        """
        return 2 if self.series in BIENNIAL_SERIES else 1

    def expected_next_deadline(self) -> Optional[datetime]:
        """Last edition's first deadline, one cycle later."""
        editions = self.deadline_editions
        if not editions:
            return None
        latest = max(editions, key=lambda e: e.year)
        first = min(d.deadline_at for d in latest.deadlines)
        return first + timedelta(days=365 * self.cadence_years())


def _edition_from_row(row: Conference) -> EditionState:
    return EditionState(
        slug=row.slug,
        year=int(row.year),
        conference_id=row.id,
        short_name=row.short_name,
        url=row.url,
        start_date=row.start_date,
        end_date=row.end_date,
        venue=row.venue,
        city=row.city,
        country=row.country,
        location=row.location,
        tier=row.tier,
        tags=list(row.tags) if row.tags else None,
        deadlines=[
            DeadlineState(
                id=d.id,
                type=d.deadline_type,
                label=d.label,
                deadline_at=aware_utc(d.deadline_at),
                timezone=d.timezone,
            )
            for d in sorted(row.deadlines, key=lambda d: d.deadline_at)
        ],
    )


def aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _series_from_editions(series: str, editions: list[EditionState]) -> SeriesState:
    editions.sort(key=lambda e: e.year)
    with_deadlines = [e for e in editions if e.deadlines] or editions
    latest = with_deadlines[-1]
    title = latest.short_name or series.upper()
    return SeriesState(
        series=series,
        title=title,
        tier=latest.tier,
        tags=latest.tags,
        editions=editions,
    )


def load_deadline_series(
    db: Session, only: Optional[set[str]] = None
) -> list[SeriesState]:
    """Every series with at least one deadline, with all of its yearly editions."""
    deadline_slugs = (
        db.query(Conference.slug)
        .join(ConferenceDeadline, ConferenceDeadline.conference_id == Conference.id)
        .distinct()
        .all()
    )
    series_keys = {s for (slug,) in deadline_slugs if (s := series_of(slug))}
    if only is not None:
        series_keys &= only
    by_series: dict[str, list[EditionState]] = {key: [] for key in series_keys}
    if not series_keys:
        return []
    rows = (
        db.query(Conference)
        .filter(Conference.year.isnot(None))
        .filter(
            Conference.slug.op("~")(
                "^(" + "|".join(re.escape(k) for k in sorted(series_keys)) + r")-\d{4}$"
            )
        )
        .all()
    )
    for row in rows:
        key = series_of(row.slug)
        if key in by_series and int(row.year) == int(row.slug[-4:]):
            by_series[key].append(_edition_from_row(row))
    return [
        _series_from_editions(key, editions)
        for key, editions in sorted(by_series.items())
        if editions
    ]


def year_labels(series: SeriesState, today: date) -> dict[int, str]:
    """PAST / UPCOMING / UNKNOWN per edition, plus MISSING_NEXT_YEAR."""
    labels: dict[int, str] = {}
    for edition in series.editions:
        reference = edition.end_date or edition.start_date
        if reference is None and not edition.deadlines:
            labels[edition.year] = "UNKNOWN"
        else:
            labels[edition.year] = "PAST" if edition.is_past(today) else "UPCOMING"
    if labels:
        latest = series.edition(max(labels))
        all_deadlines_past = bool(latest.deadlines) and all(
            d.deadline_at.date() < today for d in latest.deadlines
        )
        if labels[latest.year] == "PAST" or all_deadlines_past:
            labels[latest.year + series.cadence_years()] = "MISSING_NEXT_YEAR"
    return dict(sorted(labels.items()))


def series_manifest(series: SeriesState, today: date) -> dict:
    """Compact JSON view of a series handed to the research agent.

    Past editions other than the most recent one are dropped: the agent only
    needs last year's calendar as a pattern and the full upcoming state.
    """
    labels = year_labels(series, today)
    past = [e for e in series.editions if labels.get(e.year) == "PAST"]
    keep = {e.year for e in series.editions if labels.get(e.year) != "PAST"}
    if past:
        keep.add(past[-1].year)
    editions = []
    for edition in series.editions:
        if edition.year not in keep:
            continue
        editions.append(
            {
                "year": edition.year,
                "status": labels[edition.year],
                "url": edition.url,
                "start_date": edition.start_date.isoformat()
                if edition.start_date
                else None,
                "end_date": edition.end_date.isoformat() if edition.end_date else None,
                "venue": edition.venue,
                "city": edition.city,
                "country": edition.country,
                "deadlines": [
                    {
                        "type": d.type,
                        "label": d.label,
                        "date": local_deadline_text(d.deadline_at, d.timezone),
                        "timezone": d.timezone or "AoE",
                    }
                    for d in edition.deadlines
                ],
            }
        )
    return {
        "series": series.series,
        "title": series.title,
        "tier": series.tier,
        "tags": series.tags or [],
        "today": today.isoformat(),
        "year_labels": {str(year): label for year, label in labels.items()},
        "editions": editions,
    }


# --- Sweep selection ----------------------------------------------------------------


TIER_ORDER = {"a": 0, "b": 1, "c": 2}


def select_sweep_series(
    series: list[SeriesState],
    *,
    mode: Literal["weekly", "daily"],
    now: datetime,
    limit: int,
) -> list[SeriesState]:
    """Pick and order the series a sweep researches.

    Weekly: series with no upcoming deadline whose next cycle is due within
    ~8 months (next edition missing), then series with a deadline within ~120
    days (changes, extensions, new deadline types). Daily: deadlines within
    three weeks (extensions) and top-tier series whose next cycle is due within
    ~6 weeks but still has no deadline recorded.
    """
    picked: list[tuple[tuple, SeriesState]] = []
    for item in series:
        next_deadline = item.next_deadline(now)
        expected = item.expected_next_deadline()
        tier_rank = TIER_ORDER.get((item.tier or "").lower(), 3)
        if mode == "weekly":
            if next_deadline is None:
                if expected is None or expected > now + WEEKLY_EXPECTED_NEXT_WINDOW:
                    continue
                key = (0, tier_rank, expected)
            elif next_deadline <= now + WEEKLY_UPCOMING_WINDOW:
                key = (1, tier_rank, next_deadline)
            else:
                continue
        else:
            if (
                next_deadline is not None
                and next_deadline <= now + DAILY_IMMINENT_WINDOW
            ):
                key = (0, tier_rank, next_deadline)
            elif (
                next_deadline is None
                and tier_rank == 0
                and expected is not None
                and expected <= now + DAILY_EXPECTED_NEXT_WINDOW
            ):
                key = (1, tier_rank, expected)
            else:
                continue
        picked.append((key, item))
    picked.sort(key=lambda pair: (pair[0], pair[1].series))
    return [item for _key, item in picked[:limit]]


# --- Agent change sets ----------------------------------------------------------


def normalize_deadline_type(value: str) -> str:
    value = value.strip().lower().replace("-", "_")
    if not DEADLINE_TYPE_RE.match(value):
        raise ValueError(f"invalid deadline type {value!r}")
    return value


def normalize_local_datetime(value: str) -> str:
    value = value.strip()
    if not LOCAL_DATETIME_RE.match(value):
        raise ValueError("date must be 'YYYY-MM-DD HH:MM[:SS]' local time")
    return value if value.count(":") == 2 else f"{value}:00"


def local_instant(local: str, tz_name: str) -> datetime:
    naive = datetime.strptime(local, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=parse_timezone(tz_name)).astimezone(timezone.utc)


class DeadlineChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    label: str = Field(min_length=1, max_length=200)
    date: str
    timezone: str = "AoE"

    _type = field_validator("type")(normalize_deadline_type)
    _date = field_validator("date")(normalize_local_datetime)

    def instant(self) -> datetime:
        return local_instant(self.date, canonical_timezone(self.timezone))


class EditionChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    year: int
    url: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    venue: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    source_urls: list[str] = Field(default_factory=list)
    deadlines: list[DeadlineChange] = Field(default_factory=list, max_length=40)


class SeriesChangeSet(BaseModel):
    """Validated output of the research agent for one series."""

    model_config = ConfigDict(extra="ignore")

    requires_update: bool
    reasoning: str = ""
    source_urls: list[str] = Field(default_factory=list)
    editions: list[EditionChange] = Field(default_factory=list, max_length=4)


def _http_urls(urls: list[str]) -> list[str]:
    return [
        u.strip() for u in urls if re.match(r"^https?://[^\s/]+\.[^\s]+$", u.strip())
    ]


@dataclass
class PlannedChange:
    """One field- or deadline-level change, with before/after values."""

    kind: str  # create_edition | edition_field | add_deadline | update_deadline
    slug: str
    field: Optional[str] = None
    before: Any = None
    after: Any = None
    deadline_id: Optional[int] = None


@dataclass
class EditionPlan:
    series: str
    year: int
    slug: str
    create: bool
    changes: list[PlannedChange] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    # Values for a new edition (copied series metadata + agent fields).
    new_edition: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "series": self.series,
            "year": self.year,
            "slug": self.slug,
            "create": self.create,
            "changes": [_jsonable(asdict(c)) for c in self.changes],
            "rejections": self.rejections,
            "source_urls": self.source_urls,
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _deadline_value(deadline: DeadlineState | dict) -> dict:
    if isinstance(deadline, DeadlineState):
        deadline = asdict(deadline)
        deadline.pop("id", None)
    return _jsonable(deadline)


EDITION_FIELDS = ("url", "start_date", "end_date", "venue", "city", "country")


def plan_edition_change(
    series: SeriesState,
    change: EditionChange,
    *,
    fallback_sources: list[str],
    now: datetime,
) -> EditionPlan:
    """Diff one proposed edition against the current rows, applying every guard.

    Pure: no database access, so the guards are unit-testable. Rejected parts
    are listed in ``rejections`` and never applied; the rest still is.
    """
    today = now.date()
    slug = edition_slug(series.series, change.year)
    existing = series.edition(change.year)
    plan = EditionPlan(
        series=series.series, year=change.year, slug=slug, create=existing is None
    )
    plan.source_urls = _http_urls(change.source_urls) or _http_urls(fallback_sources)
    if not plan.source_urls:
        plan.rejections.append("no source URL supports this edition")
        return plan
    if not today.year - 1 <= change.year <= today.year + 2:
        plan.rejections.append(f"edition year {change.year} is out of range")
        return plan
    if existing is not None and existing.is_past(today):
        plan.rejections.append(f"edition {slug} has already taken place")
        return plan
    if change.start_date and change.end_date and change.end_date < change.start_date:
        plan.rejections.append("end_date is before start_date")
        return plan
    for name in ("start_date", "end_date"):
        value = getattr(change, name)
        if value and abs(value.year - change.year) > 1:
            plan.rejections.append(f"{name} {value} does not match year {change.year}")
            return plan

    proposed = {
        "url": change.url if change.url and _http_urls([change.url]) else None,
        "start_date": change.start_date,
        "end_date": change.end_date,
        "venue": change.venue or None,
        "city": change.city or None,
        "country": change.country or None,
    }
    if existing is None:
        if not change.deadlines:
            plan.rejections.append("a new edition needs at least one deadline")
            return plan
        plan.new_edition = {
            "name": f"{series.title} {change.year}",
            "short_name": series.title,
            "year": change.year,
            "tier": series.tier,
            "tags": series.tags,
            "location": join_location(proposed["city"], proposed["country"]),
            **proposed,
        }
        plan.changes.append(
            PlannedChange(kind="create_edition", slug=slug, after=_jsonable(proposed))
        )
        current_deadlines: list[DeadlineState] = []
    else:
        for name in EDITION_FIELDS:
            after = proposed[name]
            before = getattr(existing, name)
            if after is not None and after != before:
                plan.changes.append(
                    PlannedChange(
                        kind="edition_field",
                        slug=slug,
                        field=name,
                        before=_jsonable(before),
                        after=_jsonable(after),
                    )
                )
        current_deadlines = existing.deadlines

    _plan_deadlines(plan, current_deadlines, change, now)
    return plan


def _plan_deadlines(
    plan: EditionPlan,
    current: list[DeadlineState],
    change: EditionChange,
    now: datetime,
) -> None:
    # Submissions open up to a year ahead; camera-ready and other
    # post-conference deadlines can fall early in the following year. The
    # one-day margins keep AoE / UTC+14 times on the boundary days inside.
    year_start = datetime(change.year - 1, 1, 1, tzinfo=timezone.utc) - timedelta(
        days=1
    )
    year_end = datetime(change.year + 1, 7, 1, tzinfo=timezone.utc) + timedelta(days=1)
    matched_ids: set[int] = set()
    instants = {d.deadline_at for d in current}
    for proposal in change.deadlines:
        try:
            tz_name = canonical_timezone(proposal.timezone)
            instant = proposal.instant()
        except DeadlineValidationError as exc:
            plan.rejections.append(f"{proposal.type}: {exc}")
            continue
        if not year_start <= instant < year_end:
            plan.rejections.append(
                f"{proposal.type} {proposal.date} is outside the {change.year} cycle"
            )
            continue
        after = {
            "type": proposal.type,
            "label": proposal.label,
            "deadline_at": instant,
            "timezone": tz_name,
        }
        match = _match_deadline(current, proposal, matched_ids)
        if match is None:
            if instant in instants:
                continue  # Same instant under another type/label: a duplicate.
            instants.add(instant)
            plan.changes.append(
                PlannedChange(
                    kind="add_deadline", slug=plan.slug, after=_jsonable(after)
                )
            )
            continue
        matched_ids.add(match.id)
        if match.deadline_at == instant:
            continue
        if match.deadline_at <= now:
            plan.rejections.append(
                f"{proposal.type}: past deadline {match.deadline_at.isoformat()} is immutable"
            )
            continue
        if instant <= now:
            plan.rejections.append(
                f"{proposal.type}: moving a future deadline into the past needs a human"
            )
            continue
        if abs(instant - match.deadline_at) > MAX_DEADLINE_SHIFT:
            plan.rejections.append(
                f"{proposal.type}: shift from {match.deadline_at.date()} to "
                f"{instant.date()} is implausibly large"
            )
            continue
        plan.changes.append(
            PlannedChange(
                kind="update_deadline",
                slug=plan.slug,
                deadline_id=match.id,
                before=_deadline_value(match),
                after=_jsonable(after),
            )
        )


def _match_deadline(
    current: list[DeadlineState], proposal: DeadlineChange, used: set[int]
) -> Optional[DeadlineState]:
    candidates = [d for d in current if d.id not in used and d.type == proposal.type]
    exact = [d for d in candidates if (d.label or "") == proposal.label]
    if len(exact) == 1:
        return exact[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def plan_series_change_set(
    series: SeriesState, change_set: SeriesChangeSet, *, now: datetime
) -> list[EditionPlan]:
    if not change_set.requires_update:
        return []
    return [
        plan_edition_change(
            series, edition, fallback_sources=change_set.source_urls, now=now
        )
        for edition in change_set.editions
    ]


# --- Writing --------------------------------------------------------------------


def conference_snapshot(db: Session, slug: str) -> Optional[dict]:
    row = db.query(Conference).filter(Conference.slug == slug).first()
    if row is None:
        return None
    return {
        "slug": row.slug,
        "name": row.name,
        "year": row.year,
        "url": row.url,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "venue": row.venue,
        "city": row.city,
        "country": row.country,
        "location": row.location,
        "tier": row.tier,
        "tags": list(row.tags) if row.tags else None,
        # Query rather than use the relationship: writers bulk-delete rows.
        "deadlines": [
            {
                "id": d.id,
                "type": d.deadline_type,
                "label": d.label,
                "deadline_at": d.deadline_at,
                "timezone": d.timezone,
            }
            for d in db.query(ConferenceDeadline)
            .filter(ConferenceDeadline.conference_id == row.id)
            .order_by(ConferenceDeadline.deadline_at, ConferenceDeadline.id)
        ],
    }


def _apply_plan_rows(db: Session, plan: EditionPlan) -> None:
    conference = db.query(Conference).filter(Conference.slug == plan.slug).first()
    if conference is None:
        conference = Conference(slug=plan.slug, **(plan.new_edition or {}))
        db.add(conference)
        db.flush()
    for change in plan.changes:
        if change.kind == "edition_field":
            value = change.after
            if change.field in ("start_date", "end_date"):
                value = date.fromisoformat(value)
            derived = join_location(conference.city, conference.country)
            setattr(conference, change.field, value)
            if change.field in ("city", "country") and conference.location in (
                None,
                derived,
            ):
                conference.location = join_location(conference.city, conference.country)
        elif change.kind == "add_deadline":
            db.add(
                ConferenceDeadline(
                    conference_id=conference.id,
                    deadline_type=change.after["type"],
                    label=change.after["label"],
                    deadline_at=datetime.fromisoformat(change.after["deadline_at"]),
                    timezone=change.after["timezone"],
                )
            )
        elif change.kind == "update_deadline":
            row = db.get(ConferenceDeadline, change.deadline_id)
            if row is None or row.conference_id != conference.id:
                raise DeadlineValidationError(
                    f"deadline {change.deadline_id} no longer belongs to {plan.slug}"
                )
            row.deadline_at = datetime.fromisoformat(change.after["deadline_at"])
            row.label = change.after["label"]
            row.timezone = change.after["timezone"]


def apply_edition_plan(
    db: Session,
    plan: EditionPlan,
    *,
    actor: dict = AGENT_ACTOR,
    request_id: str,
) -> bool:
    """Apply the accepted part of a plan atomically with an audit event."""
    if not plan.changes:
        return False
    CatalogMutationService(db).mutate(
        actor=actor,
        operation="deadline_agent_create" if plan.create else "deadline_agent_update",
        entity_type="conference",
        entity_id=plan.slug,
        request_payload=plan.to_dict(),
        idempotency_key=None,
        expected_version=None,
        snapshot=lambda: conference_snapshot(db, plan.slug),
        apply=lambda: _apply_plan_rows(db, plan),
        request_id=request_id,
    )
    for change in plan.changes:
        logger.info(
            "conference_deadline_change %s",
            {**_jsonable(asdict(change)), "sources": plan.source_urls},
        )
    return True


def apply_series_change_set(
    db: Session,
    series_key: str,
    change_set: SeriesChangeSet,
    *,
    now: Optional[datetime] = None,
    dry_run: bool = False,
    request_id: Optional[str] = None,
) -> list[EditionPlan]:
    """Plan against fresh rows (an admin may have edited since launch), then apply."""
    now = now or datetime.now(timezone.utc)
    loaded = load_deadline_series(db, only={series_key})
    if not loaded:
        raise DeadlineValidationError(f"unknown conference series {series_key!r}")
    plans = plan_series_change_set(loaded[0], change_set, now=now)
    if dry_run:
        return plans
    for plan in plans:
        apply_edition_plan(
            db,
            plan,
            request_id=request_id or f"conference-deadline-agent:{uuid.uuid4()}",
        )
    return plans


# --- Admin edits ----------------------------------------------------------------


class AdminDeadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    label: str = Field(min_length=1, max_length=200)
    date: str = Field(description="Local time, 'YYYY-MM-DD HH:MM[:SS]'")
    timezone: str = Field(default="AoE", max_length=60)

    _type = field_validator("type")(normalize_deadline_type)
    _date = field_validator("date")(normalize_local_datetime)


class AdminEditionDeadlines(BaseModel):
    """Full replacement of one edition's deadlines plus optional metadata."""

    model_config = ConfigDict(extra="forbid")

    short_name: Optional[str] = Field(default=None, max_length=50)
    url: Optional[str] = Field(default=None, max_length=500)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    venue: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    tier: Optional[str] = Field(default=None, pattern=r"^[abc]$")
    tags: Optional[list[str]] = None
    deadlines: list[AdminDeadline] = Field(max_length=40)


def admin_replace_edition(
    db: Session, slug: str, body: AdminEditionDeadlines, *, context: dict
) -> dict:
    """Admin path: replace an edition's deadlines (creating the edition if needed)."""
    match = SERIES_SLUG_RE.match(slug)
    if not match:
        raise DeadlineValidationError("slug must look like '<series>-<year>'")
    year = int(match.group("year"))
    resolved = []
    for item in body.deadlines:
        tz_name = canonical_timezone(item.timezone)
        resolved.append(
            {
                "type": item.type,
                "label": item.label,
                "deadline_at": local_instant(item.date, tz_name),
                "timezone": tz_name,
            }
        )
    if len({d["deadline_at"] for d in resolved}) != len(resolved):
        raise DeadlineValidationError("two deadlines share the same instant")
    if body.start_date and body.end_date and body.end_date < body.start_date:
        raise DeadlineValidationError("end_date is before start_date")

    existing = db.query(Conference).filter(Conference.slug == slug).first()
    if existing is None and not body.short_name:
        raise DeadlineValidationError("short_name is required to create an edition")

    def apply() -> None:
        conference = db.query(Conference).filter(Conference.slug == slug).first()
        if conference is None:
            conference = Conference(
                slug=slug,
                name=f"{body.short_name} {year}",
                short_name=body.short_name,
                year=year,
            )
            db.add(conference)
            db.flush()
        for name in (
            "short_name",
            "url",
            "start_date",
            "end_date",
            "venue",
            "city",
            "country",
            "tier",
            "tags",
        ):
            value = getattr(body, name)
            if value is not None:
                setattr(conference, name, value or None)
        if body.city is not None or body.country is not None:
            conference.location = join_location(conference.city, conference.country)
        db.query(ConferenceDeadline).filter(
            ConferenceDeadline.conference_id == conference.id
        ).delete()
        for item in resolved:
            db.add(
                ConferenceDeadline(
                    conference_id=conference.id,
                    deadline_type=item["type"],
                    label=item["label"],
                    deadline_at=item["deadline_at"],
                    timezone=item["timezone"],
                )
            )

    after, _event, _replayed = CatalogMutationService(db).mutate(
        actor=context["actor"],
        operation="replace_deadlines",
        entity_type="conference",
        entity_id=slug,
        request_payload=body.model_dump(mode="json"),
        idempotency_key=context.get("idempotency_key"),
        expected_version=context.get("expected_version"),
        snapshot=lambda: conference_snapshot(db, slug),
        apply=apply,
        request_id=context["request_id"],
    )
    return after


# --- Freshness ------------------------------------------------------------------


# Shared by the CRON dashboard and the CLI ``status`` command. A top-tier
# series is "overdue" when nothing upcoming is recorded although, by last
# cycle's calendar, its first deadline is less than 30 days away or past.
FRESHNESS_SQL = r"""
WITH editions AS (
    SELECT regexp_replace(c.slug, '-\d{4}$', '') AS series,
           c.year,
           lower(c.tier) AS tier,
           min(d.deadline_at) AS first_deadline,
           max(d.deadline_at) AS last_deadline
    FROM conferences c
    JOIN conference_deadlines d ON d.conference_id = c.id
    WHERE c.slug ~ '-\d{4}$'
    GROUP BY 1, 2, 3
),
ranked AS (
    SELECT *,
           row_number() OVER (PARTITION BY series ORDER BY year DESC) AS rn
    FROM editions
),
series AS (
    SELECT r.series,
           bool_or(r.tier = 'a') AS top_tier,
           bool_or(r.last_deadline > now()) AS has_upcoming,
           max(r.first_deadline + make_interval(
               days => 365 * CASE
                   WHEN r.series IN ('iccv', 'eccv')
                   THEN 2 ELSE 1 END
           )) FILTER (WHERE r.rn = 1) AS expected_next
    FROM ranked r
    GROUP BY r.series
)
SELECT
    (SELECT max(finished_at) FROM conference_deadline_sweeps
      WHERE status = 'applied') AS last_write,
    (SELECT count(*) FROM conference_deadline_sweeps
      WHERE status = 'applied'
        AND finished_at > now() - interval '8 days') AS recent_writes,
    (SELECT max(launched_at) FROM conference_deadline_sweeps) AS last_launch,
    (SELECT count(*) FROM conference_deadline_sweeps
      WHERE status = 'running') AS sweeps_running,
    count(*) AS deadline_series,
    count(*) FILTER (WHERE top_tier) AS top_tier_series,
    count(*) FILTER (WHERE top_tier AND NOT has_upcoming) AS top_tier_without_upcoming,
    count(*) FILTER (
        WHERE top_tier AND NOT has_upcoming
          AND expected_next < now() + interval '30 days'
    ) AS top_tier_overdue
FROM series
"""
