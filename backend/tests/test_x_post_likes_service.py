"""X post like refreshes: reading schedule, velocity EMA, and source fallback."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest

from backend.models.database import XPostMetrics
from backend.services import x_post_likes_service as service

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def _metrics(tweet_id="1", *, age_hours=3.0, **values):
    return XPostMetrics(
        tweet_id=tweet_id,
        posted_at=NOW - timedelta(hours=age_hours),
        read_count=0,
        **values,
    )


def _refresh(monkeypatch, due, *, read_syndication, read_api=None, api_budget=300):
    monkeypatch.setattr(service, "enroll_posts", lambda _db, _now: 0)
    monkeypatch.setattr(service, "expire_posts", lambda _db, _now: 0)
    monkeypatch.setattr(service, "due_posts", lambda _db, _now, _limit: due)
    return service.refresh_likes(
        Mock(),
        now=NOW,
        read_syndication=read_syndication,
        read_api=read_api,
        api_budget=api_budget,
        max_posts=500,
    )


def test_schedule_reads_densely_at_first_and_stops_before_the_week_ends():
    posted = NOW - timedelta(minutes=30)
    assert service.next_read_at(posted, NOW) == posted + timedelta(hours=1)
    assert service.next_read_at(posted, posted + timedelta(hours=13)) == (
        posted + timedelta(hours=24)
    )
    assert service.next_read_at(posted, posted + timedelta(hours=144)) is None


def test_first_reading_uses_the_lifetime_average():
    metrics = _metrics(age_hours=4.0)
    assert service.like_velocity(metrics, 200, NOW) == 50.0


def test_first_reading_of_a_brand_new_post_counts_at_least_an_hour():
    metrics = _metrics(age_hours=0.1)
    assert service.like_velocity(metrics, 30, NOW) == 30.0


def test_later_readings_blend_the_new_rate_into_the_ema():
    metrics = _metrics(
        age_hours=10.0,
        like_count=100,
        like_velocity=20.0,
        last_read_at=NOW - timedelta(hours=2),
    )
    # 40 new likes over 2 hours = 20/h; EMA 0.75 * 20 + 0.25 * 20.
    assert service.like_velocity(metrics, 140, NOW) == pytest.approx(20.0)
    # Like counts can drop (unlikes, removed accounts); the rate never goes negative.
    assert service.like_velocity(metrics, 90, NOW) == pytest.approx(5.0)


def test_syndication_readings_are_stored_and_rescheduled(monkeypatch):
    post = _metrics(age_hours=3.0)
    report = _refresh(monkeypatch, [post], read_syndication=lambda _id: 60)

    assert report.syndication_reads == 1
    assert post.like_count == 60
    assert post.like_velocity == 20.0
    assert post.last_source == "syndication"
    assert post.read_count == 1
    assert post.next_read_at == post.posted_at + timedelta(hours=4)
    assert report.velocities == {"1": 20.0}


def test_posts_syndication_cannot_serve_fall_back_to_the_capped_api(monkeypatch):
    posts = [_metrics(str(n)) for n in range(4)]
    requested = []

    def read_api(ids):
        requested.append(ids)
        return {"1": 90}, {"2"}

    report = _refresh(
        monkeypatch,
        posts,
        read_syndication=lambda tweet_id: 30 if tweet_id == "0" else None,
        read_api=read_api,
        api_budget=2,
    )

    # Only two of the three fallback posts fit the remaining daily budget.
    assert requested == [["1", "2"]]
    assert report.api_reads == 2
    assert posts[1].last_source == "api" and posts[1].like_count == 90
    assert posts[2].gone_at == NOW and posts[2].next_read_at is None
    assert report.gone == 1
    # The post over budget stays due for the next run.
    assert posts[3].last_read_at is None
    assert report.unread == 1


def test_rate_limited_syndication_sends_the_rest_to_the_api(monkeypatch):
    posts = [_metrics(str(n)) for n in range(3)]

    def read_syndication(tweet_id):
        if tweet_id == "1":
            raise service.SyndicationRateLimited()
        return 10

    report = _refresh(
        monkeypatch,
        posts,
        read_syndication=read_syndication,
        read_api=lambda ids: ({tweet_id: 5 for tweet_id in ids}, set()),
    )

    assert report.syndication_reads == 1
    assert report.api_reads == 2
    assert [post.last_source for post in posts] == ["syndication", "api", "api"]


def test_without_an_api_reader_fallback_posts_wait(monkeypatch):
    post = _metrics()
    report = _refresh(monkeypatch, [post], read_syndication=lambda _id: None)

    assert report.api_reads == 0
    assert report.unread == 1
    assert post.read_count == 0


def test_api_failure_is_reported_without_losing_syndication_reads(monkeypatch):
    posts = [_metrics("0"), _metrics("1")]

    def read_api(_ids):
        raise httpx.HTTPStatusError(
            "402 Payment Required", request=Mock(), response=Mock()
        )

    report = _refresh(
        monkeypatch,
        posts,
        read_syndication=lambda tweet_id: 10 if tweet_id == "0" else None,
        read_api=read_api,
    )

    assert report.syndication_reads == 1
    assert "402" in report.api_error
    assert posts[0].like_count == 10
    assert posts[1].read_count == 0


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_syndication_reader_returns_favorite_count(monkeypatch):
    monkeypatch.setattr(service.time, "sleep", lambda _seconds: None)
    client = _client(
        lambda request: httpx.Response(
            200, json={"__typename": "Tweet", "favorite_count": 42}
        )
    )
    assert service.make_syndication_reader(client)("123") == 42


def test_syndication_reader_treats_tombstones_as_unavailable(monkeypatch):
    monkeypatch.setattr(service.time, "sleep", lambda _seconds: None)
    client = _client(
        lambda request: httpx.Response(200, json={"__typename": "TweetTombstone"})
    )
    assert service.make_syndication_reader(client)("123") is None


def test_syndication_reader_raises_on_rate_limit(monkeypatch):
    monkeypatch.setattr(service.time, "sleep", lambda _seconds: None)
    client = _client(lambda request: httpx.Response(429))
    with pytest.raises(service.SyndicationRateLimited):
        service.make_syndication_reader(client)("123")


def test_api_reader_batches_ids_and_reports_unavailable_posts():
    seen = {}

    def handler(request):
        seen["ids"] = request.url.params["ids"]
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "data": [{"id": "1", "public_metrics": {"like_count": 7}}],
                "errors": [{"resource_id": "2", "title": "Not Found Error"}],
            },
        )

    counts, unavailable = service.make_api_reader(_client(handler), "token")(["1", "2"])

    assert seen == {"ids": "1,2", "auth": "Bearer token"}
    assert counts == {"1": 7}
    assert unavailable == {"2"}
