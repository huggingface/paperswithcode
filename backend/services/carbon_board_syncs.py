"""Live syncs for the frontier boards added alongside Gemini 4 Carbon.

Each board parses its official leaderboard into ``LeaderboardEntry`` rows on
the board's metric scale and declares the reviewed name map that ties an
upstream model name to the catalog model and its introducing paper; the shared
``LiveLeaderboardSyncService`` does the rest. Parsers fail loudly on any layout
change so a redesign never silently rewrites a board.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup

from backend.services.carbon_board_identities import IDENTITIES
from backend.services.surge_chartography_sync_service import (
    USER_AGENT as SURGE_USER_AGENT,
)
from backend.services.live_leaderboard_sync import (
    USER_AGENT,
    LeaderboardEntry,
    LiveLeaderboard,
    check_entry_count,
    fetch_text,
    js_literal,
)

VALS_INDEX_URL = "https://www.vals.ai/benchmarks/vals_index"
SWE_SWEEP_URL = "https://swesweep.com/"
VENDING_BENCH_2_URL = "https://andonlabs.com/evals/vending-bench-2"
BLUEPRINT_BENCH_2_URL = "https://andonlabs.com/evals/blueprint-bench-2"
RIEMANN_BENCH_URL = "https://surgehq.ai/benchmarks/riemann-bench"
CWE_BENCH_URL = "https://cwe-bench.com/#leaderboard"
EXPLOITGYM_URL = "https://www.cybergym.io/exploitgym/"
EXPLOITGYM_DATA_URL = "https://www.cybergym.io/assets/data/exploitgym.json"
CYBERGYM_URL = "https://www.cybergym.io/cybergym/"
CYBERGYM_DATA_URL = "https://www.cybergym.io/assets/data/cybergym.json"
PATCHEVAL_VERIFIED_URL = "https://github.com/bytedance/PatchEval"
PATCHEVAL_VERIFIED_README_URL = (
    "https://raw.githubusercontent.com/bytedance/PatchEval/main/README.md"
)


def _text(node) -> str:
    return " ".join(node.get_text(" ").split())


def _percent(text: str, what: str) -> Decimal:
    """Parse "70.36%" into a Decimal in 0-100, failing on anything else."""
    if not text.endswith("%"):
        raise ValueError(f"{what} is not a percentage: {text!r}")
    try:
        value = Decimal(text[:-1].strip())
    except InvalidOperation as exc:
        raise ValueError(f"{what} is invalid: {text!r}") from exc
    if not 0 <= value <= 100:
        raise ValueError(f"{what} is outside 0-100: {text!r}")
    return value


def _unique(entries: list[LeaderboardEntry], what: str) -> None:
    labels = [entry.label for entry in entries]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError(f"{what} lists {duplicates!r} twice")


# --- Vals Index -------------------------------------------------------------

VALS_HEADER = ("Rank", "Model", "Accuracy")


def parse_vals_index(html: str) -> list[LeaderboardEntry]:
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Vals Index response must be non-empty HTML")
    # The page also has a per-sector breakdown table; the ranked table is
    # the one whose header starts with Rank / Model / Accuracy.
    tables = []
    for table in BeautifulSoup(html, "html.parser").find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = tuple(
            label
            for label in (_text(c) for c in rows[0].find_all(["th", "td"]))
            if label
        )
        if header[: len(VALS_HEADER)] == VALS_HEADER:
            tables.append(rows)
    if len(tables) != 1:
        raise ValueError(f"Vals Index page has {len(tables)} ranked tables; expected 1")
    rows = tables[0]
    header = tuple(_text(cell) for cell in rows[0].find_all(["th", "td"]))
    offset = header.index("Rank")
    entries = []
    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) != len(header):
            raise ValueError(f"Vals Index row has {len(cells)} columns")
        position, name, accuracy = (_text(cell) for cell in cells[offset : offset + 3])
        if not position.isdigit() or not name or len(name) > 200:
            raise ValueError(f"Vals Index row is malformed: {name!r}")
        value = _percent(accuracy, f"Vals Index accuracy for {name!r}")
        entries.append(LeaderboardEntry(name, float(value), f"{value}% Accuracy"))
    _unique(entries, "Vals Index")
    check_entry_count(entries, "Vals Index", 15, 400)
    return entries


# --- SWE-sweep --------------------------------------------------------------

SWE_SWEEP_HARNESS = "mini-SWE-agent"
_SWE_SWEEP_RESULTS = re.compile(r"(?<![\w.$])(\w+)\s*=\s*\[\s*\{\s*\"model\"")


def parse_swe_sweep(html: str) -> list[LeaderboardEntry]:
    """Read the results array the page script renders its table from."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("SWE-sweep response must be non-empty HTML")
    matches = list(_SWE_SWEEP_RESULTS.finditer(html))
    if len(matches) != 1:
        raise ValueError(f"SWE-sweep page has {len(matches)} results arrays")
    rows = js_literal(html, html.index("[", matches[0].start()), "SWE-sweep results")
    entries = []
    for row in rows:
        name, score = row.get("model"), row.get("score")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError(f"SWE-sweep row is malformed: {row!r}")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"SWE-sweep score is not a number for {name!r}")
        if not 0 <= score <= 1:
            raise ValueError(f"SWE-sweep score is outside 0-1 for {name!r}")
        percent = round(score * 100, 2)
        entries.append(
            LeaderboardEntry(
                name,
                percent,
                f"{percent}% of bugs resolved",
                harness=SWE_SWEEP_HARNESS,
                lab=str(row.get("provider") or "")[:200],
            )
        )
    _unique(entries, "SWE-sweep")
    check_entry_count(entries, "SWE-sweep", 5, 200)
    return entries


# --- Andon Labs: Vending-Bench 2 and Blueprint-Bench 2 ------------------------

_SCRIPT_URL = re.compile(r'(?:href|src)="([^"]*/_app/immutable/[^"]+\.js)"')
_VB2_RUNS = re.compile(r"(?<![\w$])vb2:\{")


def parse_vending_bench_2(chunk: str) -> list[LeaderboardEntry]:
    """Read ``runs.vb2`` (final balance per model) from the site's data chunk."""
    matches = list(_VB2_RUNS.finditer(chunk or ""))
    if len(matches) != 1:
        raise ValueError(f"Vending-Bench 2 data has {len(matches)} vb2 objects")
    runs = js_literal(chunk, matches[0].end() - 1, "Vending-Bench 2 runs")
    if not isinstance(runs, dict):
        raise ValueError("Vending-Bench 2 runs layout changed")
    entries = []
    for name, run in runs.items():
        value = run.get("final_value") if isinstance(run, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Vending-Bench 2 final value missing for {name!r}")
        if not name.strip() or len(name) > 200:
            raise ValueError(f"Vending-Bench 2 model is malformed: {name!r}")
        count = run.get("num_final_values") or run.get("num_epochs")
        balance = round(float(value), 2)
        entries.append(
            LeaderboardEntry(
                name,
                balance,
                f"${balance:,.2f} mean final balance over {count} runs",
            )
        )
    check_entry_count(entries, "Vending-Bench 2", 20, 400)
    return entries


def fetch_vending_bench_2(client: httpx.Client | None = None) -> list[LeaderboardEntry]:
    """The page lists the top 10; the full board lives in a hashed JS chunk."""
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5), follow_redirects=True
    )
    try:
        page = fetch_text(VENDING_BENCH_2_URL, active_client)
        seen: set[str] = set()
        # Start from the page's route modules and follow their imports to
        # the shared chunk that holds the run data.
        queue = [
            httpx.URL(VENDING_BENCH_2_URL).join(url)
            for url in _SCRIPT_URL.findall(page)
            if "/nodes/" in url
        ]
        while queue and len(seen) < 150:
            url = queue.pop(0)
            if str(url) in seen:
                continue
            seen.add(str(url))
            source = fetch_text(str(url), active_client)
            if _VB2_RUNS.search(source) and "final_value" in source:
                return parse_vending_bench_2(source)
            queue.extend(
                url.join(path)
                for path in re.findall(
                    r'(?:from|import)\s*\(?"(\.{1,2}/[^"]+\.js)"', source
                )
            )
        raise ValueError("Vending-Bench 2 data chunk not found")
    finally:
        if owned_client:
            active_client.close()


BLUEPRINT_HEADER = ("", "Model", "Score")


def parse_blueprint_bench_2(html: str) -> list[LeaderboardEntry]:
    """Parse the score table; the human baseline and floor scores are skipped."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Blueprint-Bench 2 response must be non-empty HTML")
    tables = BeautifulSoup(html, "html.parser").find_all("table")
    if len(tables) != 1:
        raise ValueError(f"Blueprint-Bench 2 page has {len(tables)} tables")
    rows = tables[0].find_all("tr")
    header = tuple(_text(cell) for cell in rows[0].find_all(["th", "td"]))
    if header != BLUEPRINT_HEADER:
        raise ValueError(f"Blueprint-Bench 2 table header changed: {header!r}")
    entries = []
    for row in rows[1:]:
        cells = [_text(cell) for cell in row.find_all(["th", "td"])]
        if len(cells) != 3 or not cells[1] or len(cells[1]) > 200:
            raise ValueError(f"Blueprint-Bench 2 row is malformed: {cells!r}")
        _, name, score = cells
        # "Human*" is a 12-apartment baseline; "0.000**" marks scores at or
        # below the random baseline, which the board does not rank.
        if name.endswith("*") or score.endswith("**"):
            continue
        try:
            value = Decimal(score)
        except InvalidOperation as exc:
            raise ValueError(f"Blueprint-Bench 2 score is invalid: {score!r}") from exc
        if not 0 < value <= 1:
            raise ValueError(f"Blueprint-Bench 2 score is outside 0-1: {score!r}")
        entries.append(
            LeaderboardEntry(name, float(value), f"{value} similarity score")
        )
    _unique(entries, "Blueprint-Bench 2")
    check_entry_count(entries, "Blueprint-Bench 2", 10, 300)
    return entries


# --- Surge AI: Riemann-Bench ------------------------------------------------

RIEMANN_TITLE = "Riemann-bench Leaderboard"
_CONFIGURATION = re.compile(r"^(?P<model>.+?) \((?P<configuration>[^()]+)\)$")


def parse_riemann_bench(html: str) -> list[LeaderboardEntry]:
    """Parse Surge's server-rendered leaderboard block (Chartography layout)."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Riemann-Bench response must be non-empty HTML")
    soup = BeautifulSoup(html, "html.parser")
    titles = [
        node
        for node in soup.select(".lead-rank-table-title")
        if _text(node) == RIEMANN_TITLE
    ]
    if len(titles) != 1:
        raise ValueError(f"Riemann-Bench page has {len(titles)} leaderboard blocks")
    block = titles[0].find_parent(class_="lead-rank-table-list-inner")
    if block is None:
        raise ValueError("Riemann-Bench leaderboard block layout changed")
    entries = []
    for position, row in enumerate(block.select("[data-leaderboard-row]"), start=1):
        brand = row.select_one(".head-rank-table-brand")
        name = row.select_one(".head-rank-table-name")
        score = row.select_one("[data-score]")
        if brand is None or name is None or score is None:
            raise ValueError(f"Riemann-Bench row {position} layout changed")
        match = _CONFIGURATION.match(_text(name))
        model, configuration = (
            (match["model"], match["configuration"]) if match else (_text(name), "")
        )
        brand_text = _text(brand)
        # "Gemini" + "4 Argon" is Gemini 4 Argon; "Hy" + "Hy4 Preview" and
        # "Inkling" + "Inkling" already name the model.
        label = model if model.startswith(brand_text) else f"{brand_text} {model}"
        if not label or len(label) > 200:
            raise ValueError(f"Riemann-Bench row {position} is malformed")
        # The data-score attribute is empty on this board; the visible text
        # carries the percentage.
        value = _percent(
            _text(score.parent).replace(" ", ""), f"Riemann-Bench {label!r}"
        )
        setting = f" ({configuration})" if configuration else ""
        entries.append(
            LeaderboardEntry(
                label,
                float(value / 100),
                f"{value}% Pass@1{setting}",
                lab=brand_text[:200],
            )
        )
    _unique(entries, "Riemann-Bench")
    check_entry_count(entries, "Riemann-Bench", 15, 400)
    return entries


# --- Collinear AI: CWE-bench v1 ----------------------------------------------

CWE_LIST_NAME = "CWE-bench v1 leaderboard"
_CWE_DESCRIPTION = re.compile(
    r"^Programmatic pass@1 (?P<pass1>\d+(?:\.\d+)?)%, "
    r"pass@4 (?P<pass4>\d+(?:\.\d+)?%|not reported)\."
    r".*\brun in (?P<harness>[^.]+)\.$"
)


def parse_cwe_bench(html: str) -> list[LeaderboardEntry]:
    """Read the leaderboard's JSON-LD ItemList, which the site generates from its table."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("CWE-bench response must be non-empty HTML")
    lists = []
    for script in BeautifulSoup(html, "html.parser").find_all(
        "script", type="application/ld+json"
    ):
        data = json.loads(script.string or "null")
        if isinstance(data, dict) and data.get("name") == CWE_LIST_NAME:
            lists.append(data)
    if len(lists) != 1:
        raise ValueError(f"CWE-bench page has {len(lists)} leaderboard lists")
    entries = []
    for item in lists[0].get("itemListElement") or []:
        name, description = item.get("name"), item.get("description")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError(f"CWE-bench item is malformed: {item!r}")
        match = _CWE_DESCRIPTION.match(description or "")
        if match is None:
            raise ValueError(f"CWE-bench description changed for {name!r}")
        pass1 = Decimal(match["pass1"])
        if not 0 <= pass1 <= 100:
            raise ValueError(f"CWE-bench pass@1 is outside 0-100 for {name!r}")
        entries.append(
            LeaderboardEntry(
                name,
                float(pass1 / 100),
                f"programmatic pass@1 {pass1}% (pass@4 {match['pass4']})",
                harness=match["harness"].strip(),
            )
        )
    _unique(entries, "CWE-bench")
    check_entry_count(entries, "CWE-bench", 5, 200)
    return entries


# --- ExploitGym ---------------------------------------------------------------

# Only full-set runs under the board's 6-hour budget are comparable.
EXPLOITGYM_PROTOCOLS = ("6h timeout", "rescaled 6h timeout")
_PARENTHETICAL = re.compile(r"\s*[\\]?\(.*$")


def parse_exploitgym(text: str) -> list[LeaderboardEntry]:
    data = json.loads(text)
    total = (
        (data.get("instances") or {}).get("total") if isinstance(data, dict) else None
    )
    if not isinstance(total, int) or total < 500:
        raise ValueError(f"ExploitGym instance total changed: {total!r}")
    entries = []
    for row in data.get("results") or []:
        if row.get("eval_note") not in EXPLOITGYM_PROTOCOLS:
            continue
        if row.get("version") not in (None, "v1"):
            continue
        name = _PARENTHETICAL.sub("", str(row.get("model") or "")).strip()
        solved = row.get("on_target")
        if not name or len(name) > 200:
            raise ValueError(f"ExploitGym row is malformed: {row!r}")
        if (
            isinstance(solved, bool)
            or not isinstance(solved, int)
            or not 0 <= solved <= total
        ):
            raise ValueError(f"ExploitGym solved count is invalid for {name!r}")
        harness = _PARENTHETICAL.sub("", str(row.get("agent") or "")).strip()
        rate = round(solved / total * 100, 1)
        entries.append(
            LeaderboardEntry(
                name,
                rate,
                f"{solved}/{total} intended-vulnerability exploits ({rate}%), "
                f"{row['eval_note']}, reported by {row.get('source') or 'unknown'}",
                harness=harness or "Not reported",
            )
        )
    _unique(entries, "ExploitGym")
    check_entry_count(entries, "ExploitGym", 4, 200)
    return entries


# --- CyberGym -----------------------------------------------------------------

# Feature labels the site's default "Model-focused" view leaves out: runs
# against the cleaned vulnerable image, or with a test-time knowledge base.
CYBERGYM_EXCLUDED_FEATURES = ("dynamic", "test-time mem.")


def parse_cybergym(text: str, now: datetime | None = None) -> list[LeaderboardEntry]:
    """Read the Level 1 rows the site ranks in its default model-focused view."""
    data = json.loads(text)
    rows = data.get("level1") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("CyberGym data has no level1 list")
    now = now or datetime.now(UTC)
    entries = []
    for row in rows:
        # The page ranks single-trial rows that are not held back.
        if row.get("trials") != 1 or row.get("hidden"):
            continue
        if (row.get("focus") or "model") != "model":
            continue
        features = row.get("features") or []
        if any(str(f).startswith(CYBERGYM_EXCLUDED_FEATURES) for f in features):
            continue
        visible_after = row.get("visible_after")
        if visible_after and datetime.fromisoformat(visible_after) > now:
            continue
        name = str(row.get("model") or "").strip()
        score = row.get("score_10")
        if not name or len(name) > 200:
            raise ValueError(f"CyberGym row is malformed: {row!r}")
        if isinstance(score, bool) or not isinstance(score, int | float):
            raise ValueError(f"CyberGym score is invalid for {name!r}")
        if not 0 <= score <= 1:
            raise ValueError(f"CyberGym score is outside 0-1 for {name!r}")
        rate = round(score * 100, 2)
        entries.append(
            LeaderboardEntry(
                name,
                rate,
                f"{rate}% Level 1 success rate, one trial, "
                f"reported by {row.get('source') or 'unknown'}",
                harness=str(row.get("agent") or "").strip() or "Not reported",
            )
        )
    _unique(entries, "CyberGym")
    check_entry_count(entries, "CyberGym", 20, 300)
    return entries


# --- PatchEval-Verified ---------------------------------------------------------

PATCHEVAL_HEADING = "## 📈 Results on PatchEval-Verified"
PATCHEVAL_HEADER = ("Agent", "Model", "Pass@1")
PATCHEVAL_CASES = 230
# README agent labels -> the CLI names used as harness on other boards.
PATCHEVAL_HARNESSES = {"codex": "Codex", "opencode": "OpenCode", "trae": "Trae CLI"}
_PATCHEVAL_SCORE = re.compile(r"(\d+)/(\d+) \(([\d.]+)%\)")


def parse_patcheval_verified(markdown: str) -> list[LeaderboardEntry]:
    """Read the results table under the README's PatchEval-Verified heading."""
    if not isinstance(markdown, str) or PATCHEVAL_HEADING not in markdown:
        raise ValueError("PatchEval README has no PatchEval-Verified results heading")
    section = markdown.split(PATCHEVAL_HEADING, 1)[1].split("\n## ", 1)[0]
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    table = [line for line in lines if line.startswith("|")]
    if len(table) < 3:
        raise ValueError("PatchEval-Verified results table is missing")
    cells = [[cell.strip() for cell in line.strip("|").split("|")] for line in table]
    if tuple(cells[0]) != PATCHEVAL_HEADER:
        raise ValueError(f"PatchEval-Verified header changed: {cells[0]!r}")
    entries = []
    for agent, name, result in cells[2:]:
        match = _PATCHEVAL_SCORE.fullmatch(result)
        if not match or not name or len(name) > 200:
            raise ValueError(f"PatchEval-Verified row is malformed: {name!r}")
        solved, total = int(match[1]), int(match[2])
        if total != PATCHEVAL_CASES or not 0 <= solved <= total:
            raise ValueError(f"PatchEval-Verified case count changed: {result!r}")
        rate = round(solved / total * 100, 2)
        entries.append(
            LeaderboardEntry(
                name,
                rate,
                f"{solved}/{total} CVEs repaired ({rate}%) with {agent}",
                harness=PATCHEVAL_HARNESSES.get(agent.lower(), agent),
            )
        )
    _unique(entries, "PatchEval-Verified")
    check_entry_count(entries, "PatchEval-Verified", 5, 200)
    return entries


# --- Board registry -----------------------------------------------------------


@dataclass(frozen=True)
class BoardSync:
    board: LiveLeaderboard
    fetch: Callable[[httpx.Client | None], list[LeaderboardEntry]]


def _fetching(
    url: str,
    parse: Callable[[str], list[LeaderboardEntry]],
    user_agent: str = USER_AGENT,
):
    return lambda client=None: parse(fetch_text(url, client, user_agent=user_agent))


BOARD_SYNCS: dict[str, BoardSync] = {
    "sync_vals_index": BoardSync(
        LiveLeaderboard(
            source="Vals AI Vals Index",
            provider="vals-index",
            url=VALS_INDEX_URL,
            task_slug="agents",
            dataset_slug="vals-index-v2-2",
            metric="Accuracy",
            identities=IDENTITIES["vals-index-v2-2"],
            min_selected=15,
            protocol="Vals Index v2.2: GDP-weighted average of finance, coding, legal and tax agent benchmarks.",
        ),
        _fetching(VALS_INDEX_URL, parse_vals_index),
    ),
    "sync_swe_sweep": BoardSync(
        LiveLeaderboard(
            source="SWE-sweep",
            provider="swe-sweep",
            url=SWE_SWEEP_URL,
            task_slug="coding-agents",
            dataset_slug="swe-sweep",
            metric="Resolved",
            identities=IDENTITIES["swe-sweep"],
            min_selected=5,
            excluded={
                # 11/116 is not a whole number of bugs out of 4,068, and the
                # site's FAQ says Astra 6 has not been evaluated: a partial run.
                "Astra 6": "partial run (about 93 of 100 repositories)",
            },
            protocol="Share of all 4,068 bugs resolved (hidden fix tests plus the existing suite), mini-SWE-agent, 1,000 steps / 12 h per repository.",
        ),
        _fetching(SWE_SWEEP_URL, parse_swe_sweep),
    ),
    "sync_vending_bench_2": BoardSync(
        LiveLeaderboard(
            source="Andon Labs Vending-Bench 2",
            provider="vending-bench-2",
            url=VENDING_BENCH_2_URL,
            task_slug="long-horizon-agents",
            dataset_slug="vending-bench-2",
            metric="Bank Balance ($)",
            identities=IDENTITIES["vending-bench-2"],
            min_selected=20,
            excluded={
                "Gemini 3.1 Pro Custom Tools": "non-standard custom-tools agent setup",
            },
            protocol="Mean money balance after one simulated year from a $500 start.",
        ),
        fetch_vending_bench_2,
    ),
    "sync_blueprint_bench_2": BoardSync(
        LiveLeaderboard(
            source="Andon Labs Blueprint-Bench 2",
            provider="blueprint-bench-2",
            url=BLUEPRINT_BENCH_2_URL,
            task_slug="spatial-understanding",
            dataset_slug="blueprint-bench-2",
            metric="Similarity Score",
            identities=IDENTITIES["blueprint-bench-2"],
            min_selected=10,
            protocol="Floor-plan connectivity similarity, normalized so random = 0 and a perfect plan = 1.",
        ),
        _fetching(BLUEPRINT_BENCH_2_URL, parse_blueprint_bench_2),
    ),
    "sync_riemann_bench": BoardSync(
        LiveLeaderboard(
            source="Surge AI Riemann-Bench",
            provider="riemann-bench",
            url=RIEMANN_BENCH_URL,
            task_slug="math",
            dataset_slug="riemann-bench",
            metric="Pass@1",
            identities=IDENTITIES["riemann-bench"],
            min_selected=15,
            excluded={
                # Its catalog paper was deleted; Chartography excludes it too.
                "DeepSeek V4 Flash Vision (experimental)": "experimental variant without a release",
            },
            protocol="25 private research-level problems with programmatic answer checks; agents have coding tools and web search.",
        ),
        # Surge's Webflow host rejects non-browser user agents.
        _fetching(RIEMANN_BENCH_URL, parse_riemann_bench, SURGE_USER_AGENT),
    ),
    "sync_cwe_bench": BoardSync(
        LiveLeaderboard(
            source="Collinear AI CWE-bench",
            provider="cwe-bench",
            url=CWE_BENCH_URL,
            task_slug="cybersecurity",
            dataset_slug="cwe-bench-v1",
            metric="Pass@1",
            identities=IDENTITIES["cwe-bench-v1"],
            min_selected=5,
            protocol="120 held-out audit-and-repair tasks; deterministic verifier pass@1 over four rollouts at high reasoning.",
        ),
        _fetching(CWE_BENCH_URL, parse_cwe_bench),
    ),
    "sync_exploitgym": BoardSync(
        LiveLeaderboard(
            source="ExploitGym",
            provider="exploitgym",
            url=EXPLOITGYM_URL,
            task_slug="cybersecurity",
            dataset_slug="exploitgym",
            metric="Success Rate",
            identities=IDENTITIES["exploitgym"],
            min_selected=4,
            protocol="Full 869-task v1 set, mitigations off, 6-hour budget; success requires the flag and a judge-confirmed intended vulnerability.",
        ),
        _fetching(EXPLOITGYM_DATA_URL, parse_exploitgym),
    ),
    "sync_cybergym": BoardSync(
        LiveLeaderboard(
            source="CyberGym",
            provider="cybergym",
            url=CYBERGYM_URL,
            task_slug="cybersecurity",
            dataset_slug="cybergym",
            metric="Success Rate",
            identities=IDENTITIES["cybergym"],
            min_selected=20,
            protocol="All 1,507 Level 1 tasks (vulnerability description plus unpatched codebase), one trial; success requires a PoC that reproduces the target vulnerability. Model-focused runs without the cleaned vulnerable image or test-time memory.",
        ),
        _fetching(CYBERGYM_DATA_URL, parse_cybergym),
    ),
    "sync_patcheval_verified": BoardSync(
        LiveLeaderboard(
            source="PatchEval-Verified",
            provider="patcheval-verified",
            url=PATCHEVAL_VERIFIED_URL,
            task_slug="cybersecurity",
            dataset_slug="patcheval-verified",
            metric="Accuracy",
            identities=IDENTITIES["patcheval-verified"],
            min_selected=5,
            protocol="230 real-world Go, JavaScript and Python CVEs, one patch per case, graded by each case's Docker validation entrypoint with the strengthened PatchEval-Verified PoC tests.",
        ),
        _fetching(PATCHEVAL_VERIFIED_README_URL, parse_patcheval_verified),
    ),
}
