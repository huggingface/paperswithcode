"""Crawler-control documents that must never fall through to the SPA."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.config import get_settings

router = APIRouter()

# Commercial SEO and backlink crawlers send heavy traffic and bring no readers.
BLOCKED_SEO_CRAWLERS = (
    "AhrefsBot",
    "AhrefsSiteAudit",
    "DataForSeoBot",
    "SERankingBacklinksBot",
    "SemrushBot",
    "SemrushBot-BA",
    "MJ12bot",
    "Barkrowler",
)
SEO_CRAWLER_BLOCK = (
    "".join(f"User-agent: {name}\n" for name in BLOCKED_SEO_CRAWLERS)
    + "Disallow: /\n\n"
)


def robots_policy(environment: str) -> tuple[str, dict[str, str]]:
    if environment.lower() == "staging":
        return (
            "User-agent: *\nDisallow: /\n",
            {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"},
        )
    return (
        SEO_CRAWLER_BLOCK
        + "User-agent: *\nAllow: /\nSitemap: https://paperswithcode.co/sitemap.xml\n",
        {"Cache-Control": "public, max-age=300"},
    )


@router.api_route(
    "/robots.txt",
    methods=["GET", "HEAD"],
    response_class=PlainTextResponse,
    include_in_schema=False,
)
def get_robots() -> PlainTextResponse:
    body, headers = robots_policy(get_settings().environment)
    return PlainTextResponse(body, headers=headers)
