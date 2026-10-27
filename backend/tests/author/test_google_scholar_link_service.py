from backend.services.google_scholar_link_service import (
    AuthorPaper,
    Evidence,
    WikidataPerson,
    candidate_people,
    decide,
    full_profile_evidence,
    index_people_by_name,
    names_compatible,
    parse_wikidata_tsv,
    s2_evidence,
)


def paper(paper_id: int, order: int = 1) -> AuthorPaper:
    return AuthorPaper(paper_id, f"Paper {paper_id}", None, f"s2-{paper_id}", order)


def test_names_compatible_accepts_initials_and_rejects_other_first_names():
    assert names_compatible("Xiangyu Zhang", "X. Zhang")
    assert names_compatible("Kaiming He", "Kaiming He")
    assert not names_compatible("Xiangyu Zhang", "Xiang Zhang")
    assert not names_compatible("Kaiming He", "Kaiming Hu")


def test_parse_wikidata_tsv_merges_rows_and_drops_invalid_scholar_ids():
    tsv = (
        "?p\t?g\t?s2\t?orcid\t?names\n"
        '<http://www.wikidata.org/entity/Q1>\t"VoxU11IAAAAJ"\t"111"\t"0000-0001"\t"Ada Lovelace|A. Lovelace"\n'
        '<http://www.wikidata.org/entity/Q1>\t"VoxU11IAAAAJ"\t"222"\t"0000-0001"\t"Ada Lovelace|A. Lovelace"\n'
        '<http://www.wikidata.org/entity/Q2>\t"0000-9990-0445"\t\t\t"George Brown"\n'
    )
    (person,) = parse_wikidata_tsv(tsv)
    assert person.qid == "Q1"
    assert person.s2_ids == {"111", "222"}
    assert person.names == ["Ada Lovelace", "A. Lovelace"]


def test_candidate_people_matches_without_middle_name():
    person = WikidataPerson("Q1", "VoxU11IAAAAJ", ["Christopher A. Armatas"])
    index = index_people_by_name([person])
    assert candidate_people("Christopher Armatas", index) == [person]
    assert candidate_people("Chris Armatas", index) == []


def test_s2_evidence_verifies_matching_orcid_and_flags_other_orcids():
    person = WikidataPerson("Q1", "VoxU11IAAAAJ", ["Ada Lovelace"], orcids={"A"})
    papers = [paper(1), paper(2), paper(3, order=2)]
    slots = {
        1: [{"name": "Ada Lovelace", "authorId": "9", "externalIds": {"ORCID": "A"}}],
        2: [{"name": "A. Lovelace", "authorId": "9", "externalIds": {"ORCID": "A"}}],
        3: [
            {"name": "Charles Babbage", "authorId": "7"},
            {"name": "Ada Lovelace", "authorId": "8", "externalIds": {"ORCID": "B"}},
        ],
    }
    evidence = s2_evidence("Ada Lovelace", papers, slots, person)
    assert evidence.matched_paper_ids == [1, 2]
    assert evidence.conflicting_paper_ids == [3]
    assert evidence.verdict == "partial"


def test_evidence_needs_two_papers_and_a_majority():
    assert Evidence("s", 1, [1]).verdict == "no_evidence"
    assert Evidence("s", 5, [1, 2]).verdict == "partial"
    assert Evidence("s", 3, [1, 2]).verdict == "verified"


class FakeScholar:
    """Serves a profile of article titles, `page_size` per page."""

    max_pages = 3

    def __init__(self, titles: list[str], page_size: int = 2):
        self.titles = titles
        self.page_size = page_size
        self.requests = 0

    def profile(self, scholar_id, start_page=0, max_pages=None):
        pages = max_pages or self.max_pages
        end = (start_page + pages) * self.page_size
        self.requests += pages
        return {
            "name": "Ada Lovelace",
            "affiliations": None,
            "cited_by": None,
            "complete": end >= len(self.titles),
            "articles": [
                {"title": t} for t in self.titles[start_page * self.page_size : end]
            ],
        }


def test_common_names_need_seventy_percent():
    papers = [paper(i) for i in range(10)]
    scholar = FakeScholar([f"Paper {i}" for i in range(6)], page_size=10)
    assert full_profile_evidence(scholar, "x", papers, False)[1].verdict == "verified"
    assert full_profile_evidence(scholar, "x", papers, True)[1].verdict == "partial"


def test_borderline_overlap_reads_the_rest_of_a_truncated_profile():
    papers = [paper(i) for i in range(10)]
    # The first 3 pages hold 5 of the author's papers; later pages hold 4 more.
    titles = (
        [f"Paper {i}" for i in range(5)]
        + ["Other"]
        + [f"Paper {i}" for i in range(5, 9)]
    )
    profile, evidence = full_profile_evidence(FakeScholar(titles), "x", papers, False)
    assert profile["complete"]
    assert len(evidence.matched_paper_ids) == 9


def candidate_row(author_id: int, qid: str, scholar_id: str) -> dict:
    verified = {"verdict": "verified"}
    return {
        "author_id": author_id,
        "qid": qid,
        "scholar_id": scholar_id,
        "s2": verified,
        "serpapi": verified,
    }


def test_decide_allows_two_wikidata_items_with_one_profile_for_one_author():
    rows = [
        candidate_row(1, "Q1", "VoxU11IAAAAJ"),
        candidate_row(1, "Q2", "VoxU11IAAAAJ"),
    ]
    decide(rows)
    assert {r["status"] for r in rows} == {"proposed"}


def test_decide_holds_back_a_profile_matched_by_two_authors():
    rows = [
        candidate_row(1, "Q1", "VoxU11IAAAAJ"),
        candidate_row(2, "Q1", "VoxU11IAAAAJ"),
    ]
    decide(rows)
    assert {r["status"] for r in rows} == {"shared_scholar_id"}
