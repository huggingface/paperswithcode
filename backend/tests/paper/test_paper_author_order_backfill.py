from __future__ import annotations

import httpx

from backend.services import paper_author_order_service
from backend.services.paper_author_order_service import (
    AuthorListClient,
    LinkedAuthor,
    ListedAuthor,
    match_author_order,
)


def _listed(*names: str) -> list[ListedAuthor]:
    return [ListedAuthor(name) for name in names]


def test_match_orders_links_by_listed_position() -> None:
    linked = [
        LinkedAuthor(10, "Sida Peng", "pengsida"),
        LinkedAuthor(20, "jinkai  zhang", None),
        LinkedAuthor(30, "Jingyi Xu", None),
    ]

    order, missing = match_author_order(
        linked, _listed("Jinkai Zhang", "Jingyi Xu", "Someone Unlinked", "Sida Peng")
    )

    assert missing == []
    assert order == {20: 1, 30: 2, 10: 3}


def test_match_prefers_hf_username_and_reports_unknown_names() -> None:
    linked = [
        LinkedAuthor(1, "HF Display Name", "ada"),
        LinkedAuthor(2, "Nobody Listed", None),
    ]
    listed = [ListedAuthor("Grace Hopper"), ListedAuthor("Ada Lovelace", "ada")]

    order, missing = match_author_order(linked, listed)

    assert order == {1: 1}
    assert missing == [linked[1]]


def test_duplicate_names_take_successive_positions() -> None:
    linked = [LinkedAuthor(1, "Wei Li", None), LinkedAuthor(2, "Wei Li", "weili")]

    order, missing = match_author_order(linked, _listed("Wei Li", "Other", "Wei Li"))

    assert missing == []
    assert order == {1: 1, 2: 2}


def test_duplicate_link_without_second_listing_is_unmatched() -> None:
    linked = [LinkedAuthor(1, "Wei Li", None), LinkedAuthor(2, "Wei Li", None)]

    order, missing = match_author_order(linked, _listed("Wei Li", "Other"))

    assert order == {1: 1}
    assert missing == [linked[1]]


ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2610.12126v2</id>
    <author><name>Jinkai Zhang</name></author>
    <author><name>Jingyi Xu</name></author>
  </entry>
</feed>"""


def test_clients_parse_arxiv_and_hf_author_lists(monkeypatch) -> None:
    monkeypatch.setattr(paper_author_order_service, "ARXIV_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(paper_author_order_service, "HF_DELAY_SECONDS", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "export.arxiv.org":
            assert request.url.params["id_list"] == "2610.12126"
            return httpx.Response(200, content=ATOM_FEED)
        if request.url.path.endswith("/missing"):
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "authors": [
                    {"name": "Jinkai Zhang", "user": {"user": "the0xka1"}},
                    {"name": "Jingyi Xu"},
                ]
            },
        )

    client = AuthorListClient(httpx.Client(transport=httpx.MockTransport(handler)))

    assert client.arxiv_authors(["2610.12126"]) == {
        "2610.12126": _listed("Jinkai Zhang", "Jingyi Xu")
    }
    assert client.hf_authors("2610.12126") == [
        ListedAuthor("Jinkai Zhang", "the0xka1"),
        ListedAuthor("Jingyi Xu"),
    ]
    assert client.hf_authors("missing") is None


def test_folded_names_match_only_after_exact_names() -> None:
    linked = [
        LinkedAuthor(1, "Lorenz K Muller", None),
        LinkedAuthor(2, "Lorenz K. Müller", None),
        LinkedAuthor(3, "Yifan Zhang", None),
    ]

    order, missing = match_author_order(
        linked, _listed("Lorenz K. Müller", "Yi-Fan Zhang", "Lorenz K. Muller")
    )

    assert missing == []
    assert order == {2: 1, 3: 2, 1: 3}


def test_client_backs_off_on_rate_limit(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(paper_author_order_service.time, "sleep", sleeps.append)
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "90"}),
            httpx.Response(503),
            httpx.Response(200, content=ATOM_FEED),
        ]
    )
    client = AuthorListClient(
        httpx.Client(transport=httpx.MockTransport(lambda _: next(responses)))
    )

    assert list(client.arxiv_authors(["2610.12126"])) == ["2610.12126"]
    backoffs = [
        s for s in sleeps if s >= paper_author_order_service.FIRST_BACKOFF_SECONDS
    ]
    assert backoffs == [90.0, 60.0]
