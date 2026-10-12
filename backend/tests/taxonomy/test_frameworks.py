from types import SimpleNamespace

from backend.services.framework_service import FrameworkService


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def outerjoin(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def group_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, query_results):
        self.query_results = iter(query_results)
        self.query_count = 0

    def query(self, *args):
        self.query_count += 1
        return FakeQuery(next(self.query_results))


def test_framework_catalog_is_nested_and_database_backed():
    domain = SimpleNamespace(
        id=1, slug="llm", name="Large Language Models", description="LLM tools"
    )
    category = SimpleNamespace(
        id=2,
        domain_id=1,
        slug="inference",
        name="Inference",
        description="Serving tools",
        guide_url=None,
        guide_label=None,
    )
    framework = SimpleNamespace(
        id=3,
        category_id=2,
        slug="vllm",
        name="vLLM",
        organization_name="vLLM Project",
        description="Fast serving",
        when_to_use="GPU serving",
        docs_url="https://docs.vllm.ai/",
    )
    repository = SimpleNamespace(
        url="https://github.com/vllm-project/vllm",
        owner="vllm-project",
        name="vllm",
    )
    paper = SimpleNamespace(arxiv_id="2309.06180")
    platform = SimpleNamespace(framework_id=3, platform="gpu")
    session = FakeSession(
        [
            [domain],
            [category],
            [(framework, repository, paper)],
            [platform],
            [(framework.id, 7)],
        ]
    )
    service = FrameworkService(session)

    catalog = service.get_catalog()

    item = catalog.domains[0].categories[0].frameworks[0]
    assert item.slug == "vllm"
    assert item.github_url == repository.url
    assert item.repository == "vllm-project/vllm"
    assert item.paper_count == 7
    assert item.introducing_paper_arxiv_id == paper.arxiv_id
    assert item.platforms == ["gpu"]
    assert session.query_count == 5


def test_framework_catalog_count_query_is_grouped_and_latest_only():
    class RecordingQuery(FakeQuery):
        def __init__(self):
            super().__init__([])
            self.joins = []

        def outerjoin(self, *args, **kwargs):
            self.joins.append(args)
            return self

    class RecordingSession:
        def __init__(self):
            self.queries = []

        def query(self, *args):
            query = RecordingQuery()
            self.queries.append(query)
            return query

    session = RecordingSession()

    FrameworkService(session).get_catalog()

    assert len(session.queries) == 5
    count_query = session.queries[-1]
    join_sql = " ".join(
        str(argument) for join in count_query.joins for argument in join
    )
    assert "paper_repositories.repository_id = frameworks.repository_id" in join_sql
    assert "papers.is_latest_version" in join_sql
    assert "is_official" not in join_sql
