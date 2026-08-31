"""Parser for the exact PwC read-only Hugging Face command subset."""

from __future__ import annotations

import argparse
import re
import sys

from restricted_hf_cli import (
    CLI_VERSION,
    GATEWAY_CONTRACT_VERSION,
    OFFICIAL_COMPAT_VERSION,
    PRODUCT_LABEL,
    WORKER_CONTRACT_VERSION,
)
from restricted_hf_cli.render import render
from restricted_hf_cli.transport import TransportError, query

REPO_MAX = 256
SLUG_MAX = 512
TEXT_MAX = 256
OWNER_MAX = 96
FILTER_MAX = 128
REVISION_MAX = 256
EXPAND_MAX = 32
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_REPO = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?$", re.ASCII
)
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$", re.ASCII)

EXPANDS = {
    "models": frozenset(
        (
            "author baseModels cardData childrenModelCount config createdAt disabled "
            "downloads downloadsAllTime evalResults gated gguf inference "
            "inferenceProviderMapping lastModified library_name likes mask_token "
            "model-index pipeline_tag private resourceGroup safetensors sha siblings "
            "spaces tags transformersInfo trendingScore usedStorage widgetData"
        ).split()
    ),
    "datasets": frozenset(
        (
            "author cardData citation createdAt description disabled downloads "
            "downloadsAllTime gated lastModified likes mainSize paperswithcode_id "
            "private resourceGroup sha siblings tags trendingScore usedStorage"
        ).split()
    ),
    "spaces": frozenset(
        (
            "author cardData createdAt datasets disabled lastModified likes models "
            "private resourceGroup runtime sdk sha siblings subdomain tags "
            "trendingScore usedStorage"
        ).split()
    ),
}
SORTS = {
    "models": ("created_at", "downloads", "last_modified", "likes", "trending_score"),
    "datasets": ("created_at", "downloads", "last_modified", "likes", "trending_score"),
    "spaces": ("created_at", "last_modified", "likes", "trending_score"),
}


class RestrictedParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(
            2,
            f"hf: error: {message}\n{PRODUCT_LABEL}; "
            "unsupported commands are unavailable\n",
        )


def _bounded(value: str, maximum: int, label: str) -> str:
    if not value.strip() or len(value) > maximum or _CONTROL.search(value):
        raise argparse.ArgumentTypeError(f"invalid {label}")
    return value


def repo_id(value: str) -> str:
    value = _bounded(value, REPO_MAX, "repository ID")
    if "://" in value or not _REPO.fullmatch(value):
        raise argparse.ArgumentTypeError("repository ID must be canonical, not a URL")
    return value


def slug(value: str) -> str:
    value = _bounded(value, SLUG_MAX, "collection slug")
    if "://" in value or not _SLUG.fullmatch(value):
        raise argparse.ArgumentTypeError("collection slug must be canonical, not a URL")
    return value


def _format(parser):
    parser.add_argument("--format", choices=("agent",), default="agent")


def _parser() -> RestrictedParser:
    root = RestrictedParser(
        prog="hf", description=f"Hugging Face CLI — {PRODUCT_LABEL}"
    )
    sub = root.add_subparsers(dest="group", required=True)
    version = sub.add_parser("version", description=PRODUCT_LABEL)
    _format(version)
    collections = sub.add_parser("collections", description=PRODUCT_LABEL)
    csub = collections.add_subparsers(dest="command", required=True)
    cinfo = csub.add_parser("info", description=PRODUCT_LABEL)
    cinfo.add_argument("collection_slug", type=slug)
    _format(cinfo)
    clist = csub.add_parser("list", description=PRODUCT_LABEL)
    clist.add_argument("--owner", type=lambda v: _bounded(v, OWNER_MAX, "owner"))
    clist.add_argument("--item", type=lambda v: _bounded(v, TEXT_MAX, "item"))
    clist.add_argument("--sort", choices=("lastModified", "trending", "upvotes"))
    clist.add_argument("--limit", type=int, default=20)
    _format(clist)
    for group in ("models", "datasets", "spaces"):
        gp = sub.add_parser(group, description=PRODUCT_LABEL)
        gsub = gp.add_subparsers(dest="command", required=True)
        card = gsub.add_parser("card", description=PRODUCT_LABEL)
        card.add_argument("repo_id", type=repo_id)
        selectors = card.add_mutually_exclusive_group()
        selectors.add_argument("--metadata", action="store_true")
        selectors.add_argument("--text", action="store_true")
        _format(card)
        info = gsub.add_parser("info", description=PRODUCT_LABEL)
        info.add_argument("repo_id", type=repo_id)
        info.add_argument(
            "--revision", type=lambda v: _bounded(v, REVISION_MAX, "revision")
        )
        info.add_argument("--expand", action="append", default=[])
        _format(info)
        listing = gsub.add_parser("list", description=PRODUCT_LABEL)
        listing.add_argument("repo_id", nargs="?", type=repo_id)
        listing.add_argument("--search", type=lambda v: _bounded(v, TEXT_MAX, "search"))
        listing.add_argument(
            "--author", type=lambda v: _bounded(v, OWNER_MAX, "author")
        )
        listing.add_argument("--filter", action="append", default=[])
        if group == "models":
            listing.add_argument(
                "--pipeline-tag", type=lambda v: _bounded(v, FILTER_MAX, "pipeline tag")
            )
            listing.add_argument("--gated", action="store_true")
            listing.add_argument(
                "--apps", type=lambda v: _bounded(v, FILTER_MAX, "apps")
            )
            listing.add_argument(
                "--num-parameters", type=lambda v: _bounded(v, 64, "parameter range")
            )
        listing.add_argument("--sort", choices=SORTS[group])
        listing.add_argument("--limit", type=int, default=20)
        listing.add_argument("--expand", action="append", default=[])
        listing.add_argument("--human-readable", action="store_true")
        listing.add_argument("--tree", action="store_true")
        listing.add_argument("--recursive", action="store_true")
        listing.add_argument(
            "--revision", type=lambda v: _bounded(v, REVISION_MAX, "revision")
        )
        _format(listing)
    return root


def _operation_arguments(args, parser) -> tuple[str, dict]:
    values = vars(args).copy()
    group = values.pop("group")
    command = values.pop("command", None)
    values.pop("format", None)
    if group == "version":
        return "version", {}
    operation = f"{group[:-1] if group != 'spaces' else 'space'}_{command}"
    if group == "collections":
        operation = f"collection_{command}"
    if values.get("limit") is not None and not 1 <= values["limit"] <= 50:
        parser.error("--limit must be between 1 and 50")
    filters = values.get("filter", [])
    if len(filters) > 10 or any(
        len(v) > FILTER_MAX or not v.strip() or _CONTROL.search(v) for v in filters
    ):
        parser.error("--filter accepts at most 10 non-empty values of 128 characters")
    expands = values.get("expand", [])
    if (
        len(expands) > EXPAND_MAX
        or sum(len(v.encode()) for v in expands) > 2048
        or any(v not in EXPANDS.get(group, ()) for v in expands)
    ):
        parser.error("--expand contains an unsupported or oversized field")
    if command == "list" and group != "collections":
        file_flags = any(
            values.get(k) for k in ("tree", "recursive", "revision", "human_readable")
        )
        discovery_flags = any(
            values.get(k)
            for k in (
                "search",
                "author",
                "filter",
                "sort",
                "expand",
                "pipeline_tag",
                "gated",
                "apps",
                "num_parameters",
            )
        )
        if values.get("repo_id"):
            if discovery_flags:
                parser.error("discovery flags cannot be used with a repository ID")
            values.pop("limit", None)
        elif file_flags:
            parser.error("file-list flags require a repository ID")
    return operation, {
        key: value
        for key, value in values.items()
        if value not in (None, False, [], "")
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    operation, arguments = _operation_arguments(args, parser)
    if operation == "version":
        print(f"hf {CLI_VERSION} ({PRODUCT_LABEL})")
        print(f"official_compatibility: huggingface_hub {OFFICIAL_COMPAT_VERSION}")
        print(f"gateway_contract: {GATEWAY_CONTRACT_VERSION}")
        print(f"worker_contract: {WORKER_CONTRACT_VERSION}")
        return 0
    try:
        sys.stdout.write(render(query(operation, arguments)))
    except TransportError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
