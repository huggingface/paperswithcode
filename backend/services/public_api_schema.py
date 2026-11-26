"""Explicit, read-only beta surface; keep the application's full schema intact."""

from copy import deepcopy

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

PUBLIC_SCHEMA_PATH = "/api/v1/openapi.json"
PUBLIC_ENDPOINTS = {
    "/api/v1/papers/": {"page_size": 5, "include_resources": True},
    "/api/v1/papers/search": {"q": "attention", "page_size": 5},
    "/api/v1/papers/recent": {"limit": 5},
    "/api/v1/papers/trending": {"limit": 5},
    "/api/v1/papers/{paper_id}": {
        "paper_id": "1706.03762",
        "include_resources": True,
    },
    "/api/v1/papers/arxiv/{arxiv_id}": {
        "arxiv_id": "1706.03762",
        "include_resources": True,
    },
    "/api/v1/papers/{identifier:path}/public-metadata": {
        "identifier": "1706.03762",
    },
    "/api/v1/papers/public-metadata/search": {"title": "Deep learning"},
    "/api/v1/research/papers/{paper_id}/read": {
        "paper_id": "1706.03762",
        "offset": 0,
        "limit": 65536,
    },
    "/api/v1/tasks/": {"q": "image classification", "page_size": 5},
    "/api/v1/tasks/{task_id}": {"task_id": "image-classification"},
    "/api/v1/datasets/": {"q": "ImageNet", "page_size": 5},
    "/api/v1/datasets/{dataset_id}": {"dataset_id": "imagenet-1k"},
    "/api/v1/datasets/{dataset_id}/tasks/": {"dataset_id": "imagenet-1k"},
    "/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics": {
        "dataset_id": 72,
        "task_id": 1,
    },
    "/api/v1/evaluations/": {"page_size": 5},
    "/api/v1/evaluations/{evaluation_id}": {"evaluation_id": 1},
}


def schema_path(route_path: str) -> str:
    return route_path.replace(":path}", "}")


def public_openapi(app: FastAPI) -> dict:
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path in PUBLIC_ENDPOINTS
        and "GET" in route.methods
    ]
    schema = get_openapi(
        title="Papers With Code public API",
        version="1.0.0-beta",
        description=(
            "Anonymous, read-only experimental beta for paper search, bounded "
            "catalog lookups and paper full text. List papers past page 100 "
            "with `cursor`. Planned breaking changes are announced at least 14 "
            "days ahead at /docs/api#changelog. A Markdown guide is at "
            "/docs/api.md."
        ),
        routes=routes,
        servers=[{"url": "https://paperswithcode.co"}],
    )
    examples = {
        schema_path(path): example for path, example in PUBLIC_ENDPOINTS.items()
    }
    for path, item in schema["paths"].items():
        operation = deepcopy(item["get"])
        operation["tags"] = list(dict.fromkeys(operation.get("tags", [])))
        operation["security"] = []
        operation["x-example-parameters"] = examples[path]
        operation["responses"]["429"] = {
            "description": "IP traffic limit exceeded. Wait at least Retry-After seconds and retry with backoff.",
            "headers": {
                "Retry-After": {
                    "schema": {"type": "integer"},
                    "description": "Seconds to wait before retrying.",
                }
            },
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"detail": {"type": "string"}},
                    },
                    "example": {
                        "detail": "API traffic limit exceeded. Retry with backoff."
                    },
                }
            },
        }
        schema["paths"][path] = {"get": operation}
    return schema


def cached_public_openapi(app: FastAPI) -> dict:
    schema = getattr(app.state, "public_api_schema", None)
    if schema is None:
        schema = public_openapi(app)
        app.state.public_api_schema = schema
    return schema
