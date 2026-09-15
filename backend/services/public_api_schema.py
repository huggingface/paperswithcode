"""Explicit, read-only beta surface; keep the application's full schema intact."""

from copy import deepcopy

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

PUBLIC_SCHEMA_PATH = "/api/v1/openapi.json"
# Examples are small requests; path identifiers can be replaced with lookup results.
PUBLIC_ENDPOINTS = {
    "/api/v1/papers/": {"page_size": 5, "include_resources": True},
    "/api/v1/papers/search": {"q": "attention", "mode": "keyword", "page_size": 5},
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


def public_openapi(app: FastAPI) -> dict:
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path in PUBLIC_ENDPOINTS
        and "GET" in route.methods
    ]
    # Routes can also declare writes; explicitly project GET below.
    schema = get_openapi(
        title="Papers With Code public API",
        version="1.0.0-beta",
        description=(
            "Anonymous, read-only experimental beta. Keyword search and bounded "
            "lookups; not a bulk export service. Planned breaking changes are "
            "announced at least 14 days ahead at /docs/api#changelog."
        ),
        routes=routes,
        servers=[{"url": "https://paperswithcode.co"}],
    )
    for path, item in schema["paths"].items():
        operation = deepcopy(item["get"])
        operation["security"] = []
        operation["x-example-parameters"] = PUBLIC_ENDPOINTS[path]
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
        if path.endswith("/papers/search"):
            for parameter in operation.get("parameters", []):
                if parameter["name"] == "mode":
                    parameter["description"] = (
                        "Send keyword explicitly. Semantic and hybrid search are outside the public beta."
                    )
                    # No invented default: the existing endpoint defaults differently.
                    parameter["schema"] = {"type": "string", "enum": ["keyword"]}
                    parameter["required"] = True
        schema["paths"][path] = {"get": operation}
    return schema
