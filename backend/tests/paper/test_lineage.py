from types import SimpleNamespace

import pytest

from backend import cli
from backend.services import paper_lineage_service
from backend.services.paper_lineage_service import (
    add_lineage_chain,
    remove_lineage_edge,
)


class FakeDb:
    def __init__(self, existing=()):
        self.relations = {tuple(edge): SimpleNamespace() for edge in existing}
        self.added = []
        self.deleted = []
        self.commits = 0

    def get(self, _model, key):
        return self.relations.get(tuple(key))

    def add(self, relation):
        key = (relation.source_paper_id, relation.target_paper_id)
        self.relations[key] = relation
        self.added.append(key)

    def delete(self, relation):
        key = next(key for key, value in self.relations.items() if value is relation)
        del self.relations[key]
        self.deleted.append(key)

    def commit(self):
        self.commits += 1


def install_paper_resolver(monkeypatch):
    papers = {
        "A": SimpleNamespace(id=1, arxiv_id="A", title="Paper A"),
        "B": SimpleNamespace(id=2, arxiv_id="B", title="Paper B"),
        "C": SimpleNamespace(id=3, arxiv_id="C", title="Paper C"),
    }
    monkeypatch.setattr(
        paper_lineage_service,
        "resolve_paper",
        lambda _db, reference: (papers[reference], reference),
    )


def test_add_lineage_chain_expands_adjacent_edges_idempotently(monkeypatch):
    install_paper_resolver(monkeypatch)
    db = FakeDb(existing=[(1, 2)])

    edges = add_lineage_chain(db, ["A", "B", "C"])

    assert [edge.status for edge in edges] == ["existing", "created"]
    assert db.added == [(2, 3)]
    assert db.commits == 1


def test_add_lineage_chain_rejects_short_or_repeated_chains(monkeypatch):
    install_paper_resolver(monkeypatch)
    with pytest.raises(ValueError, match="at least two"):
        add_lineage_chain(FakeDb(), ["A"])
    with pytest.raises(ValueError, match="same paper twice"):
        add_lineage_chain(FakeDb(), ["A", "B", "A"])


def test_remove_lineage_edge_is_directional(monkeypatch):
    install_paper_resolver(monkeypatch)
    db = FakeDb(existing=[(1, 2)])

    edge = remove_lineage_edge(db, "A", "B")

    assert edge.status == "removed"
    assert db.deleted == [(1, 2)]
    assert db.commits == 1


def test_lineage_cli_parses_chain_and_guards_removal():
    add = cli.build_parser().parse_args(
        ["paper", "lineage", "add", "2301.00001", "2302.00002", "--json"]
    )
    assert add.papers == ["2301.00001", "2302.00002"]
    assert add.json

    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["paper", "lineage", "remove", "2301.00001", "2302.00002"]
        )
