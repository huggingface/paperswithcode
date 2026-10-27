"""Evidence-gated Google Scholar profile links for authors.

Candidates come from Wikidata (P1960, "Google Scholar author ID"): a PwC author
and a Wikidata person are candidates when their names are compatible. A
candidate is only proposed when papers prove the two are the same person:

- Semantic Scholar: on the author's PwC papers, the matching S2 author slot
  carries the Wikidata person's ORCID or S2 author ID.
- SerpAPI (when a key is set): the Scholar profile itself lists the author's
  PwC papers.

Both checks also require most of the PwC author's papers to match, so authors
whose PwC row merges several same-name people are reported, never linked.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
SERPAPI_URL = "https://serpapi.com/search.json"
SERPAPI_ACCOUNT_URL = "https://serpapi.com/account.json"

# Scholar user IDs are 12 URL-safe characters; Wikidata also holds junk values.
SCHOLAR_ID_RE = re.compile(r"^[A-Za-z0-9_-]{12}$")

# One shard per first character of the Scholar ID keeps each query far below
# the Wikidata Query Service's 60 s limit (~2k people, under 20 s each).
WIKIDATA_QUERY = """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?p ?g ?s2 ?orcid (GROUP_CONCAT(DISTINCT ?n; SEPARATOR="|") AS ?names) WHERE {
  ?p wdt:P1960 ?g .
  FILTER(STRSTARTS(?g, "%s"))
  { ?p rdfs:label ?n } UNION { ?p skos:altLabel ?n }
  FILTER(LANG(?n) = "en" || LANG(?n) = "mul")
  OPTIONAL { ?p wdt:P4012 ?s2 }
  OPTIONAL { ?p wdt:P496 ?orcid }
}
GROUP BY ?p ?g ?s2 ?orcid
"""
SCHOLAR_ID_FIRST_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)

MIN_MATCHED_PAPERS = 2
MIN_MATCHED_SHARE = 0.5
# Names shared by several Wikidata researchers need a clearer majority.
COMMON_NAME_MIN_SHARE = 0.7
# An overlap in this range on a truncated profile is rechecked on the full one.
BORDERLINE_SHARE = (0.4, 0.7)


@dataclass
class WikidataPerson:
    qid: str
    scholar_id: str
    names: list[str]
    s2_ids: set[str] = field(default_factory=set)
    orcids: set[str] = field(default_factory=set)


@dataclass
class AuthorPaper:
    paper_id: int
    title: str
    arxiv_id: str | None
    s2_id: str | None
    author_order: int


@dataclass
class Evidence:
    source: str
    considered: int
    matched_paper_ids: list[int]
    conflicting_paper_ids: list[int] = field(default_factory=list)
    min_share: float = MIN_MATCHED_SHARE

    @property
    def share(self) -> float:
        return len(self.matched_paper_ids) / self.considered if self.considered else 0.0

    @property
    def verdict(self) -> str:
        matched = len(self.matched_paper_ids)
        if matched < MIN_MATCHED_PAPERS:
            return "no_evidence"
        if self.conflicting_paper_ids or self.share < self.min_share:
            return "partial"
        return "verified"


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z]+", " ", text).split())


def name_keys(name: str) -> set[str]:
    """Full normalized name plus first+last, so middle names don't block a match."""
    tokens = normalize_name(name).split()
    if len(tokens) < 2:
        return set()
    return {" ".join(tokens), f"{tokens[0]} {tokens[-1]}"}


def names_compatible(pwc_name: str, other: str) -> bool:
    """Same last name and compatible first name ('X. Zhang' fits 'Xiangyu Zhang')."""
    a, b = normalize_name(pwc_name).split(), normalize_name(other).split()
    if len(a) < 2 or len(b) < 2 or a[-1] != b[-1]:
        return False
    first_a, first_b = a[0], b[0]
    if len(first_a) == 1 or len(first_b) == 1:
        return first_a[0] == first_b[0]
    return first_a == first_b


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _strip_tsv(value: str) -> str:
    """Unwrap a QLever TSV cell: <iri>, "literal", or "literal"@lang."""
    value = value.strip()
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1].rsplit("/", 1)[-1]
    match = re.match(r'^"(.*)"(?:@[\w-]+|\^\^.*)?$', value, re.S)
    return match.group(1) if match else value


def fetch_wikidata_tsv(client: httpx.Client, attempts: int = 5) -> str:
    """All Wikidata people with a Scholar ID, as one TSV with a single header."""
    shards = [
        _fetch_wikidata_shard(client, char, attempts) for char in SCHOLAR_ID_FIRST_CHARS
    ]
    header = shards[0].partition("\n")[0]
    rows = [shard.partition("\n")[2].strip("\n") for shard in shards]
    return "\n".join([header, *filter(None, rows)])


def _fetch_wikidata_shard(client: httpx.Client, first_char: str, attempts: int) -> str:
    for attempt in range(attempts):
        response = client.get(
            WIKIDATA_SPARQL_URL,
            params={"query": WIKIDATA_QUERY % first_char},
            headers={
                "Accept": "text/tab-separated-values",
                # Wikimedia asks automated clients to identify themselves.
                "User-Agent": "PapersWithCode-ScholarLinks/1.0 (https://paperswithcode.co)",
            },
            timeout=120,
        )
        if response.status_code != 429 and response.status_code < 500:
            break
        if attempt + 1 < attempts:
            wait = 30 * 2**attempt
            logger.warning(
                "Wikidata HTTP %d for shard %r; retrying in %d s",
                response.status_code,
                first_char,
                wait,
            )
            time.sleep(wait)
    response.raise_for_status()
    return response.text


def parse_wikidata_tsv(tsv: str) -> list[WikidataPerson]:
    """One person per (item, Scholar ID); S2 and ORCID values are merged."""
    people: dict[tuple[str, str], WikidataPerson] = {}
    reader = csv.reader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    next(reader)
    for row in reader:
        qid, scholar_id, s2_id, orcid, names = (_strip_tsv(v) for v in row[:5])
        if not SCHOLAR_ID_RE.match(scholar_id):
            continue
        person = people.setdefault(
            (qid, scholar_id),
            WikidataPerson(qid=qid, scholar_id=scholar_id, names=names.split("|")),
        )
        if s2_id:
            person.s2_ids.add(s2_id)
        if orcid:
            person.orcids.add(orcid)
    return list(people.values())


def index_people_by_name(
    people: Iterable[WikidataPerson],
) -> dict[str, list[WikidataPerson]]:
    index: dict[str, list[WikidataPerson]] = defaultdict(list)
    for person in people:
        for key in set().union(*(name_keys(n) for n in person.names)):
            index[key].append(person)
    return index


def candidate_people(
    pwc_name: str, index: dict[str, list[WikidataPerson]]
) -> list[WikidataPerson]:
    seen: dict[tuple[str, str], WikidataPerson] = {}
    for key in name_keys(pwc_name):
        for person in index.get(key, []):
            if any(names_compatible(pwc_name, n) for n in person.names):
                seen[(person.qid, person.scholar_id)] = person
    return list(seen.values())


class SemanticScholarBatch:
    """Fetch S2 author slots for papers in small batches, backing off on 429.

    The key is shared with production CRONs, so batches stay small and a
    throttled request waits up to two minutes between attempts.
    """

    batch_size = 100

    def __init__(self, api_key: str, client: httpx.Client, pause: float = 2.0):
        self.api_key = api_key
        self.client = client
        self.pause = pause
        self.requests = 0

    def authors(self, papers: list[AuthorPaper]) -> dict[int, list[dict]]:
        keyed = {}
        for paper in papers:
            if paper.s2_id:
                keyed[paper.s2_id] = paper.paper_id
            elif paper.arxiv_id:
                keyed[f"ARXIV:{paper.arxiv_id}"] = paper.paper_id
        ids = list(keyed)
        result: dict[int, list[dict]] = {}
        for chunk in iter_chunks(ids, self.batch_size):
            for s2_key, data in zip(chunk, self._post(chunk), strict=True):
                if data:
                    result[keyed[s2_key]] = data.get("authors") or []
        return result

    def _post(self, ids: list[str]) -> list[dict | None]:
        for attempt in range(12):
            time.sleep(self.pause)
            self.requests += 1
            response = self.client.post(
                S2_BATCH_URL,
                params={"fields": "authors.name,authors.authorId,authors.externalIds"},
                json={"ids": ids},
                headers={"x-api-key": self.api_key},
                timeout=120,
            )
            if response.status_code != 429:
                response.raise_for_status()
                return response.json()
            wait = min(120, 10 * 2**attempt)
            logger.warning("Semantic Scholar 429; retrying in %d s", wait)
            time.sleep(wait)
        response.raise_for_status()
        return []


def s2_slot(pwc_name: str, paper: AuthorPaper, slots: list[dict]) -> dict | None:
    """The S2 author on this paper who is the PwC author, nearest to their position."""
    compatible = [
        (abs(i - (paper.author_order - 1)), slot)
        for i, slot in enumerate(slots)
        if names_compatible(pwc_name, slot.get("name") or "")
    ]
    return min(compatible, key=lambda pair: pair[0])[1] if compatible else None


def s2_evidence(
    pwc_name: str,
    papers: list[AuthorPaper],
    s2_authors: dict[int, list[dict]],
    person: WikidataPerson,
) -> Evidence:
    considered, matched, conflicting = 0, [], []
    for paper in papers:
        slot = s2_slot(pwc_name, paper, s2_authors.get(paper.paper_id, []))
        if slot is None:
            continue
        considered += 1
        orcid = (slot.get("externalIds") or {}).get("ORCID")
        if slot.get("authorId") in person.s2_ids or (orcid and orcid in person.orcids):
            matched.append(paper.paper_id)
        elif orcid and person.orcids:
            conflicting.append(paper.paper_id)
    return Evidence("semantic_scholar", considered, matched, conflicting)


class SerpApiQuotaExhausted(Exception):
    """SerpAPI refused with 429: the plan's monthly or hourly searches are used up."""


class SerpApiScholar:
    """Google Scholar author profiles through SerpAPI (one call per 100 articles)."""

    def __init__(self, api_key: str, client: httpx.Client, max_pages: int = 3):
        self.api_key = api_key
        self.client = client
        self.max_pages = max_pages
        self.requests = 0

    def searches_left(self) -> int:
        """Searches left this month; reading the account costs none."""
        response = self.client.get(
            SERPAPI_ACCOUNT_URL, params={"api_key": self.api_key}, timeout=60
        )
        if response.status_code != 200:
            raise RuntimeError(f"SerpAPI account HTTP {response.status_code}")
        return int(response.json().get("total_searches_left") or 0)

    def profile(
        self, scholar_id: str, start_page: int = 0, max_pages: int | None = None
    ) -> dict:
        articles: list[dict] = []
        first: dict = {}
        complete = False
        for page in range(start_page, start_page + (max_pages or self.max_pages)):
            self.requests += 1
            response = self.client.get(
                SERPAPI_URL,
                params={
                    "engine": "google_scholar_author",
                    "author_id": scholar_id,
                    "num": 100,
                    # PwC papers are mostly recent, so newest-first finds them
                    # within the first pages even on long profiles.
                    "sort": "pubdate",
                    "start": page * 100,
                    "api_key": self.api_key,
                },
                timeout=60,
            )
            # httpx errors quote the URL, which carries the API key.
            if response.status_code == 429:
                raise SerpApiQuotaExhausted(f"SerpAPI quota exhausted at {scholar_id}")
            if response.status_code != 200:
                raise RuntimeError(
                    f"SerpAPI HTTP {response.status_code} for {scholar_id}"
                )
            data = response.json()
            first = first or data
            articles.extend(data.get("articles") or [])
            if not (data.get("serpapi_pagination") or {}).get("next"):
                complete = True
                break
        return {
            "complete": complete,
            "name": (first.get("author") or {}).get("name"),
            "affiliations": (first.get("author") or {}).get("affiliations"),
            "cited_by": first.get("cited_by"),
            "articles": articles,
        }


def serpapi_evidence(
    papers: list[AuthorPaper], profile: dict, common_name: bool = False
) -> Evidence:
    titles = {normalize_title(a.get("title") or "") for a in profile["articles"]}
    matched = [p.paper_id for p in papers if normalize_title(p.title) in titles]
    min_share = COMMON_NAME_MIN_SHARE if common_name else MIN_MATCHED_SHARE
    return Evidence("serpapi", len(papers), matched, min_share=min_share)


def full_profile_evidence(
    serp: SerpApiScholar,
    scholar_id: str,
    papers: list[AuthorPaper],
    common_name: bool,
    max_pages: int = 15,
) -> tuple[dict, Evidence]:
    """Read the newest pages; read on when a truncated profile is borderline."""
    profile = serp.profile(scholar_id)
    evidence = serpapi_evidence(papers, profile, common_name)
    low, high = BORDERLINE_SHARE
    if not profile["complete"] and low <= evidence.share < high:
        start = serp.max_pages
        rest = serp.profile(scholar_id, start_page=start, max_pages=max_pages - start)
        profile["articles"] += rest["articles"]
        profile["complete"] = rest["complete"]
        evidence = serpapi_evidence(papers, profile, common_name)
    return profile, evidence


def sample_papers(papers: list[AuthorPaper], size: int) -> list[AuthorPaper]:
    """An even sample of an author's papers, enough to judge an S2 match."""
    papers = sorted(papers, key=lambda p: p.paper_id)
    if len(papers) <= size:
        return papers
    step = len(papers) / size
    return [papers[int(i * step)] for i in range(size)]


def evidence_json(evidence: Evidence) -> dict:
    return {
        "verdict": evidence.verdict,
        "considered": evidence.considered,
        "matched": len(evidence.matched_paper_ids),
        "share": round(evidence.share, 2),
        "matched_paper_ids": evidence.matched_paper_ids,
        "conflicting_paper_ids": evidence.conflicting_paper_ids,
    }


def decide(rows: list[dict]) -> None:
    """Set each candidate's status; only a sole verified person is proposed.

    Rows carry `author_id`, `scholar_id`, `s2` and `serpapi` evidence (as from
    `evidence_json`, `serpapi` may be None).
    """
    for row in rows:
        # Scholar's own list is the stronger proof; it decides when present.
        row["status"] = (row["serpapi"] or row["s2"])["verdict"]
    by_author = defaultdict(list)
    for row in rows:
        by_author[row["author_id"]].append(row)
    for author_rows in by_author.values():
        verified = {r["scholar_id"] for r in author_rows if r["status"] == "verified"}
        for row in author_rows:
            if row["status"] == "verified":
                row["status"] = "proposed" if len(verified) == 1 else "ambiguous"
    by_scholar = defaultdict(list)
    for row in rows:
        if row["status"] == "proposed":
            by_scholar[row["scholar_id"]].append(row)
    for scholar_rows in by_scholar.values():
        # Two Wikidata items may carry one Scholar ID; only distinct authors count.
        if len({r["author_id"] for r in scholar_rows}) > 1:
            # Several PwC rows for one person: likely duplicates to merge first.
            for row in scholar_rows:
                row["status"] = "shared_scholar_id"


def iter_chunks(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
