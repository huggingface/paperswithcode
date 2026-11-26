from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.routers import agent_discovery
from backend.routers.public_api import (
    PublicRateLimitMiddleware,
    PublicReadCorsMiddleware,
)
from backend.routers.public_error_handlers import register_public_error_handlers
from backend.services.public_rate_limit import (
    CATALOG_ZONE,
    LIST_ZONE,
    PublicRateLimiter,
    zones_for,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_zones_follow_the_nginx_key_maps():
    assert zones_for("GET", "/api/v1/papers/") == (CATALOG_ZONE, LIST_ZONE)
    assert zones_for("GET", "/api/v1/papers/search/feed") == (CATALOG_ZONE, LIST_ZONE)
    assert zones_for("GET", "/api/v1/papers/1706.03762") == (CATALOG_ZONE,)
    assert zones_for("POST", "/api/v1/papers/lookup") == (CATALOG_ZONE,)
    assert zones_for("HEAD", "/api/v1/papers/") == ()
    assert zones_for("POST", "/api/v1/papers/") == ()
    assert zones_for("GET", "/api/v1/methods/") == ()


def test_limiter_replays_the_nginx_leaky_bucket():
    clock = FakeClock()
    limiter = PublicRateLimiter(clock)
    zones = (CATALOG_ZONE,)

    assert limiter.take("203.0.113.5", zones) == '"catalog";r=60;t=0'
    for _ in range(59):
        limiter.take("203.0.113.5", zones)
    assert limiter.take("203.0.113.5", zones) == '"catalog";r=0;t=30'
    assert limiter.take("198.51.100.7", zones) == '"catalog";r=60;t=0'

    clock.now += 10
    assert limiter.take("203.0.113.5", zones) == '"catalog";r=19;t=21'
    clock.now += 3600
    assert limiter.take("203.0.113.5", zones) == '"catalog";r=60;t=0'


def test_limiter_reports_every_zone_of_a_list_request():
    limiter = PublicRateLimiter(FakeClock())
    zones = (CATALOG_ZONE, LIST_ZONE)
    limiter.take("203.0.113.5", zones)
    assert limiter.take("203.0.113.5", zones) == '"catalog";r=59;t=1, "list";r=19;t=1'


def test_limiter_prunes_drained_clients():
    clock = FakeClock()
    limiter = PublicRateLimiter(clock)
    buckets = limiter.buckets["catalog"]
    for _ in range(61):
        limiter.take("203.0.113.5", (CATALOG_ZONE,))
    for index in range(buckets.prune_at - 2):
        limiter.take(f"10.0.{index // 256}.{index % 256}", (CATALOG_ZONE,))
        limiter.take(f"10.0.{index // 256}.{index % 256}", (CATALOG_ZONE,))
    clock.now += 10
    limiter.take("198.51.100.7", (CATALOG_ZONE,))
    assert list(buckets.entries) == ["203.0.113.5"]
    assert limiter.take("203.0.113.5", (CATALOG_ZONE,)) == '"catalog";r=19;t=21'


def _client() -> TestClient:
    app = FastAPI()
    register_public_error_handlers(app)
    app.include_router(agent_discovery.router)

    @app.get("/api/v1/papers/stats")
    def private_stats():
        return {}

    @app.get("/api/v1/papers/{paper_id}")
    def detail(paper_id: str):
        if paper_id == "missing":
            raise HTTPException(404, "Paper not found")
        return {"id": paper_id}

    app.add_middleware(PublicReadCorsMiddleware)
    app.add_middleware(PublicRateLimitMiddleware)
    return TestClient(app, client=("127.0.0.1", 50000))


def test_public_reads_report_and_expose_the_remaining_quota():
    client = _client()
    headers = {"X-Real-IP": "203.0.113.5", "Origin": "https://research.example"}

    client.get("/api/v1/papers/stats", headers=headers)
    response = client.get("/api/v1/papers/1706.03762", headers=headers)

    assert response.headers["ratelimit-policy"] == '"catalog";q=120;w=60'
    assert response.headers["ratelimit"] == '"catalog";r=59;t=1'
    exposed = response.headers["access-control-expose-headers"].split(", ")
    assert {"RateLimit", "RateLimit-Policy"} <= set(exposed)
    private = client.get("/api/v1/papers/stats", headers=headers)
    assert "ratelimit" not in private.headers


def test_unknown_api_routes_carry_an_error_code():
    response = _client().get("/api/v1/nonexistent-route")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "not_found"}


def test_api_version_root_redirects_to_the_documentation():
    client = _client()
    for path in ("/api/v1", "/api/v1/", "/api/"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/docs/api"
