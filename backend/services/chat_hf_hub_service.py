"""Anonymous, normalized, bounded Hugging Face catalog access for chat."""

from __future__ import annotations

import json
import re
import tempfile
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

HF_OPERATIONS = frozenset(
    {
        "collection_info",
        "collection_list",
        "dataset_card",
        "dataset_info",
        "dataset_list",
        "model_card",
        "model_info",
        "model_list",
        "space_card",
        "space_info",
        "space_list",
    }
)
REPO_TYPES = {"model": "model", "dataset": "dataset", "space": "space"}
MAX_REPO_ID = 256
MAX_COLLECTION_SLUG = 512
MAX_SEARCH = 256
MAX_OWNER = 96
MAX_FILTER = 128
MAX_FILTERS = 10
MAX_REVISION = 256
MAX_EXPANDS = 32
MAX_EXPAND_BYTES = 2048
MAX_DISCOVERY_LIMIT = 50
DEFAULT_DISCOVERY_LIMIT = 20
MAX_FILES = 200
MAX_DEPTH = 10
MAX_CARD_METADATA_BYTES = 32 * 1024
MAX_CARD_TEXT_BYTES = 192 * 1024
MAX_CARD_TOTAL_BYTES = 224 * 1024
# Only MAX_CARD_TOTAL_BYTES of a card is read; refuse to download far larger
# files, which would fill the backend's disk before any limit applied.
MAX_CARD_DOWNLOAD_BYTES = 1024 * 1024
MAX_LIST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_CACHE_ENTRIES = 512
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_UPSTREAM_SECONDS = 10.0
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_REPO = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?$", re.ASCII
)
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$", re.ASCII)

EXPAND_FIELDS = {
    "model": frozenset(
        (
            "author baseModels cardData childrenModelCount config createdAt disabled "
            "downloads downloadsAllTime evalResults gated gguf inference "
            "inferenceProviderMapping lastModified library_name likes mask_token "
            "model-index pipeline_tag private resourceGroup safetensors sha siblings "
            "spaces tags transformersInfo trendingScore usedStorage widgetData"
        ).split()
    ),
    "dataset": frozenset(
        (
            "author cardData citation createdAt description disabled downloads "
            "downloadsAllTime gated lastModified likes mainSize paperswithcode_id "
            "private resourceGroup sha siblings tags trendingScore usedStorage"
        ).split()
    ),
    "space": frozenset(
        (
            "author cardData createdAt datasets disabled lastModified likes models "
            "private resourceGroup runtime sdk sha siblings subdomain tags "
            "trendingScore usedStorage"
        ).split()
    ),
}
SORT_FIELDS = {
    "model": frozenset(
        ("created_at", "downloads", "last_modified", "likes", "trending_score")
    ),
    "dataset": frozenset(
        ("created_at", "downloads", "last_modified", "likes", "trending_score")
    ),
    "space": frozenset(("created_at", "last_modified", "likes", "trending_score")),
}


class ChatHfHubError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _bounded_text(value: Any, maximum: int, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or _CONTROL.search(value)
    ):
        raise ChatHfHubError(422, "hf_invalid_request", f"Invalid {label}")
    return value


def _repo_id(value: Any) -> str:
    value = _bounded_text(value, MAX_REPO_ID, "repository ID")
    if "://" in value or not _REPO.fullmatch(value):
        raise ChatHfHubError(
            422, "hf_invalid_request", "Repository ID must be canonical"
        )
    return value


def _slug(value: Any) -> str:
    value = _bounded_text(value, MAX_COLLECTION_SLUG, "collection slug")
    if "://" in value or not _SLUG.fullmatch(value):
        raise ChatHfHubError(
            422, "hf_invalid_request", "Collection slug must be canonical"
        )
    return value


def validate_hf_request(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the complete trusted-boundary command matrix."""
    if operation not in HF_OPERATIONS or not isinstance(arguments, dict):
        raise ChatHfHubError(422, "hf_invalid_request", "Unsupported HF operation")
    allowed_common = {
        "repo_id",
        "revision",
        "expand",
        "search",
        "author",
        "filter",
        "sort",
        "limit",
        "human_readable",
        "tree",
        "recursive",
        "metadata",
        "text",
        "pipeline_tag",
        "gated",
        "apps",
        "num_parameters",
        "collection_slug",
        "owner",
        "item",
    }
    if not set(arguments) <= allowed_common:
        raise ChatHfHubError(422, "hf_invalid_request", "Unsupported HF argument")
    args = dict(arguments)
    if operation == "collection_info":
        if set(args) != {"collection_slug"}:
            raise ChatHfHubError(
                422, "hf_invalid_request", "Invalid collection info arguments"
            )
        args["collection_slug"] = _slug(args["collection_slug"])
        return args
    if operation == "collection_list":
        if not set(args) <= {"owner", "item", "sort", "limit"}:
            raise ChatHfHubError(
                422, "hf_invalid_request", "Invalid collection list arguments"
            )
        for key, maximum in (("owner", MAX_OWNER), ("item", 256)):
            if key in args:
                args[key] = _bounded_text(args[key], maximum, key)
        if args.get("sort") not in {None, "lastModified", "trending", "upvotes"}:
            raise ChatHfHubError(422, "hf_invalid_request", "Invalid collection sort")
        args["limit"] = _limit(args.get("limit", DEFAULT_DISCOVERY_LIMIT))
        return args
    repo_type, command = operation.split("_", 1)
    if command in {"card", "info"}:
        permitted = (
            {"repo_id", "metadata", "text"}
            if command == "card"
            else {"repo_id", "revision", "expand"}
        )
        if not set(args) <= permitted or "repo_id" not in args:
            raise ChatHfHubError(
                422, "hf_invalid_request", f"Invalid {command} arguments"
            )
        args["repo_id"] = _repo_id(args["repo_id"])
        if command == "card":
            if args.get("metadata") and args.get("text"):
                raise ChatHfHubError(
                    422, "hf_invalid_request", "Card selectors are mutually exclusive"
                )
            args["metadata"] = bool(args.get("metadata"))
            args["text"] = bool(args.get("text"))
        else:
            _validate_revision_expand(args, repo_type)
        return args
    permitted = {
        "repo_id",
        "search",
        "author",
        "filter",
        "sort",
        "limit",
        "expand",
        "human_readable",
        "tree",
        "recursive",
        "revision",
    }
    if repo_type == "model":
        permitted |= {"pipeline_tag", "gated", "apps", "num_parameters"}
    if not set(args) <= permitted:
        raise ChatHfHubError(422, "hf_invalid_request", "Invalid list arguments")
    if "repo_id" in args:
        args["repo_id"] = _repo_id(args["repo_id"])
        forbidden = {
            "search",
            "author",
            "filter",
            "sort",
            "limit",
            "expand",
            "pipeline_tag",
            "gated",
            "apps",
            "num_parameters",
        }
        if set(args) & forbidden:
            raise ChatHfHubError(
                422, "hf_invalid_request", "Discovery flags cannot be used in file mode"
            )
        if "revision" in args:
            args["revision"] = _bounded_text(args["revision"], MAX_REVISION, "revision")
        for flag in ("human_readable", "tree", "recursive"):
            args[flag] = bool(args.get(flag))
    else:
        if set(args) & {"human_readable", "tree", "recursive", "revision"}:
            raise ChatHfHubError(
                422, "hf_invalid_request", "File flags require a repository ID"
            )
        for key, maximum in (
            ("search", MAX_SEARCH),
            ("author", MAX_OWNER),
            ("pipeline_tag", MAX_FILTER),
            ("apps", MAX_FILTER),
            ("num_parameters", 64),
        ):
            if key in args:
                args[key] = _bounded_text(args[key], maximum, key)
        filters = args.get("filter", [])
        if not isinstance(filters, list) or len(filters) > MAX_FILTERS:
            raise ChatHfHubError(422, "hf_invalid_request", "Invalid filters")
        args["filter"] = [_bounded_text(v, MAX_FILTER, "filter") for v in filters]
        if args.get("sort") not in SORT_FIELDS[repo_type] | {None}:
            raise ChatHfHubError(422, "hf_invalid_request", "Invalid sort")
        args["limit"] = _limit(args.get("limit", DEFAULT_DISCOVERY_LIMIT))
        _validate_revision_expand(args, repo_type, revision_allowed=False)
        if "gated" in args:
            args["gated"] = bool(args["gated"])
    return args


def _limit(value: Any) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= MAX_DISCOVERY_LIMIT
    ):
        raise ChatHfHubError(
            422, "hf_invalid_request", "Limit must be between 1 and 50"
        )
    return value


def _validate_revision_expand(
    args: dict, repo_type: str, *, revision_allowed: bool = True
) -> None:
    if "revision" in args:
        if not revision_allowed:
            raise ChatHfHubError(
                422, "hf_invalid_request", "Revision is unavailable in discovery mode"
            )
        args["revision"] = _bounded_text(args["revision"], MAX_REVISION, "revision")
    expands = args.get("expand", [])
    if (
        not isinstance(expands, list)
        or len(expands) > MAX_EXPANDS
        or sum(len(str(v).encode()) for v in expands) > MAX_EXPAND_BYTES
        or any(v not in EXPAND_FIELDS[repo_type] for v in expands)
    ):
        raise ChatHfHubError(422, "hf_invalid_request", "Unsupported expand field")
    args["expand"] = expands


class _TtlLruCache:
    def __init__(self, max_entries: int, max_bytes: int):
        self.max_entries = min(max_entries, MAX_CACHE_ENTRIES)
        self.max_bytes = min(max_bytes, MAX_CACHE_BYTES)
        self._lock = threading.Lock()
        self._values: OrderedDict[str, tuple[float, float, bytes]] = OrderedDict()
        self._bytes = 0

    def get(self, key: str) -> tuple[dict, int] | None:
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            hit = self._values.get(key)
            if hit is None:
                return None
            inserted, _expires, raw = hit
            self._values.move_to_end(key)
        return json.loads(raw), max(0, int(now - inserted))

    def put(self, key: str, value: dict, ttl: int) -> None:
        raw = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        if len(raw) > self.max_bytes:
            return
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            old = self._values.pop(key, None)
            if old:
                self._bytes -= len(old[2])
            self._values[key] = (now, now + ttl, raw)
            self._bytes += len(raw)
            while len(self._values) > self.max_entries or self._bytes > self.max_bytes:
                _, (_, _, evicted) = self._values.popitem(last=False)
                self._bytes -= len(evicted)

    def configure(self, max_entries: int, max_bytes: int) -> None:
        with self._lock:
            self.max_entries = min(max_entries, MAX_CACHE_ENTRIES)
            self.max_bytes = min(max_bytes, MAX_CACHE_BYTES)
            while len(self._values) > self.max_entries or self._bytes > self.max_bytes:
                _, (_, _, evicted) = self._values.popitem(last=False)
                self._bytes -= len(evicted)

    def _purge(self, now: float) -> None:
        expired = [
            key
            for key, (_inserted, expires, _) in self._values.items()
            if now >= expires
        ]
        for key in expired:
            _, _, raw = self._values.pop(key)
            self._bytes -= len(raw)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()
            self._bytes = 0


class ChatHfHubService:
    _cache = _TtlLruCache(MAX_CACHE_ENTRIES, MAX_CACHE_BYTES)
    _flights_lock = threading.Lock()
    _flights: dict[str, threading.Event] = {}

    def __init__(self, settings, api: HfApi | None = None):
        self.settings = settings
        self.api = api or HfApi(token=False)
        self.deadline_seconds = min(
            float(
                getattr(
                    settings, "chat_hf_catalog_timeout_seconds", MAX_UPSTREAM_SECONDS
                )
            ),
            MAX_UPSTREAM_SECONDS,
        )
        self._deadline = threading.local()
        self._cache.configure(
            int(getattr(settings, "chat_hf_cache_max_entries", MAX_CACHE_ENTRIES)),
            int(getattr(settings, "chat_hf_cache_max_bytes", MAX_CACHE_BYTES)),
        )

    @classmethod
    def reset_cache_for_tests(cls) -> None:
        cls._cache.reset()

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict:
        args = validate_hf_request(operation, arguments)
        configured_limit = min(
            int(
                getattr(
                    self.settings, "chat_hf_discovery_max_limit", MAX_DISCOVERY_LIMIT
                )
            ),
            MAX_DISCOVERY_LIMIT,
        )
        if "limit" in args and args["limit"] > configured_limit:
            raise ChatHfHubError(
                422,
                "hf_invalid_request",
                "Requested limit exceeds the configured maximum",
            )
        key_args = dict(args)
        if operation.endswith("_card"):
            key_args.pop("metadata", None)
            key_args.pop("text", None)
        key = json.dumps(
            [operation, key_args],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if hit := self._cache.get(key):
            value, age = hit
            value["cache"] = "hit"
            value["cache_age_seconds"] = age
            return self._project_card(value, args)
        with self._flights_lock:
            event = self._flights.get(key)
            leader = event is None
            if leader:
                event = threading.Event()
                self._flights[key] = event
        if not leader:
            if not event.wait(self.deadline_seconds):
                raise ChatHfHubError(
                    503, "hf_unavailable", "Hugging Face is unavailable"
                )
            if hit := self._cache.get(key):
                value, age = hit
                value["cache"] = "hit"
                value["cache_age_seconds"] = age
                return self._project_card(value, args)
            raise ChatHfHubError(503, "hf_unavailable", "Hugging Face is unavailable")
        try:
            started = time.monotonic()
            self._deadline.value = started + self.deadline_seconds
            envelope = self._dispatch(operation, args)
            envelope["cache"] = "miss"
            self._ensure_response_bound(envelope)
            self._cache.put(key, envelope, self._ttl(operation, args))
            return self._project_card(deepcopy(envelope), args)
        except HfHubHTTPError as error:
            status = getattr(error.response, "status_code", 503)
            if isinstance(error, RepositoryNotFoundError) or status == 404:
                raise ChatHfHubError(
                    404, "hf_not_found", "Public Hugging Face resource was not found"
                ) from None
            if status == 403:
                raise ChatHfHubError(
                    403,
                    "hf_access_denied",
                    "Resource is unavailable to anonymous access",
                ) from None
            if status == 429:
                raise ChatHfHubError(
                    429, "hf_upstream_rate_limit", "Hugging Face rate limit reached"
                ) from None
            raise ChatHfHubError(
                503, "hf_unavailable", "Hugging Face is unavailable"
            ) from None
        except (OSError, TimeoutError, httpx.TimeoutException):
            raise ChatHfHubError(
                503, "hf_unavailable", "Hugging Face is unavailable"
            ) from None
        finally:
            with self._flights_lock:
                self._flights.pop(key, None)
                event.set()

    def _remaining_seconds(self) -> float:
        remaining = getattr(self._deadline, "value", 0.0) - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        return remaining

    def _check_deadline(self) -> None:
        self._remaining_seconds()

    def _dispatch(self, operation: str, args: dict) -> dict:
        self._check_deadline()
        if operation.startswith("collection_"):
            return self._collection(operation, args)
        repo_type, command = operation.split("_", 1)
        if command == "card":
            return self._card(repo_type, args)
        if command == "info":
            return self._info(repo_type, args)
        if "repo_id" in args:
            return self._files(repo_type, args)
        return self._discover(repo_type, args)

    def _collection(self, operation: str, args: dict) -> dict:
        if operation == "collection_info":
            item = self.api.get_collection(args["collection_slug"], token=False)
            self._check_deadline()
            if bool(getattr(item, "private", False)):
                raise ChatHfHubError(
                    403,
                    "hf_access_denied",
                    "Resource is unavailable to anonymous access",
                )
            data = _normalize_collection(item)
            source = {
                "provider": "huggingface_hub",
                "url": f"https://huggingface.co/collections/{args['collection_slug']}",
            }
            return _envelope(operation, data, source=source)
        items = []
        for item in self.api.list_collections(**args, token=False):
            self._check_deadline()
            if not bool(getattr(item, "private", False)):
                items.append(item)
            if len(items) > args["limit"]:
                break
        more = len(items) > args["limit"]
        items = items[: args["limit"]]
        return self._bound_list_envelope(
            _envelope(
                operation,
                [_normalize_collection(v) for v in items],
                result_set=_result_set(args["limit"], len(items), more),
            )
        )

    def _info(self, repo_type: str, args: dict) -> dict:
        method = getattr(self.api, f"{repo_type}_info")
        info = method(
            args["repo_id"],
            revision=args.get("revision"),
            expand=args.get("expand") or None,
            timeout=self._remaining_seconds(),
            token=False,
        )
        self._check_deadline()
        if bool(getattr(info, "private", False)):
            raise ChatHfHubError(
                403, "hf_access_denied", "Resource is unavailable to anonymous access"
            )
        data = _normalize_repo(info, repo_type, args.get("expand", []))
        source = _source(repo_type, args["repo_id"], data.get("sha"))
        return _envelope(f"{repo_type}_info", data, source=source)

    def _discover(self, repo_type: str, args: dict) -> dict:
        method = getattr(self.api, f"list_{repo_type}s")
        kwargs = {
            k: v
            for k, v in args.items()
            if k not in {"human_readable", "tree", "recursive", "repo_id"}
            and v not in ([], None)
        }
        limit = kwargs["limit"]
        kwargs["limit"] = limit + 1
        items = []
        for item in method(**kwargs, token=False):
            self._check_deadline()
            if not bool(getattr(item, "private", False)):
                items.append(item)
            if len(items) > limit:
                break
        more = len(items) > limit
        items = items[:limit]
        data = [_normalize_repo(v, repo_type, args.get("expand", [])) for v in items]
        return self._bound_list_envelope(
            _envelope(
                f"{repo_type}_list",
                data,
                result_set=_result_set(limit, len(data), more),
            )
        )

    def _files(self, repo_type: str, args: dict) -> dict:
        recursive = args.get("recursive", False)
        entries = []
        truncated_reason = None
        iterator = self.api.list_repo_tree(
            args["repo_id"],
            recursive=recursive,
            revision=args.get("revision"),
            repo_type=repo_type,
            token=False,
        )
        max_files = min(
            int(getattr(self.settings, "chat_hf_max_files", MAX_FILES)), MAX_FILES
        )
        max_depth = min(
            int(getattr(self.settings, "chat_hf_max_depth", MAX_DEPTH)), MAX_DEPTH
        )
        for entry in iterator:
            self._check_deadline()
            path = str(getattr(entry, "path", ""))
            if path.count("/") + 1 > max_depth:
                truncated_reason = "maximum_depth"
                continue
            entries.append(
                {
                    "path": path,
                    "type": "directory"
                    if entry.__class__.__name__.lower().endswith("folder")
                    else "file",
                    "size": getattr(entry, "size", None),
                    "oid": getattr(entry, "oid", None),
                }
            )
            if len(entries) >= max_files:
                truncated_reason = "maximum_entries"
                break
        info = self.api.repo_info(
            args["repo_id"],
            revision=args.get("revision"),
            repo_type=repo_type,
            timeout=self._remaining_seconds(),
            token=False,
        )
        self._check_deadline()
        if bool(getattr(info, "private", False)):
            raise ChatHfHubError(
                403, "hf_access_denied", "Resource is unavailable to anonymous access"
            )
        source = _source(repo_type, args["repo_id"], getattr(info, "sha", None))
        return self._bound_list_envelope(
            _envelope(
                f"{repo_type}_list",
                entries,
                source=source,
                result_set=_result_set(max_files, len(entries), bool(truncated_reason)),
                truncation={
                    "truncated": bool(truncated_reason),
                    "reason": truncated_reason,
                },
            )
        )

    def _card(self, repo_type: str, args: dict) -> dict:
        info = getattr(self.api, f"{repo_type}_info")(
            args["repo_id"], timeout=self._remaining_seconds(), token=False
        )
        if bool(getattr(info, "private", False)):
            raise ChatHfHubError(
                403, "hf_access_denied", "Resource is unavailable to anonymous access"
            )
        sha = getattr(info, "sha", None)
        if not sha:
            raise ChatHfHubError(
                404, "hf_not_found", "Repository has no resolved revision"
            )
        [card_info] = self.api.get_paths_info(
            args["repo_id"],
            ["README.md"],
            repo_type=repo_type,
            revision=sha,
            token=False,
        ) or [None]
        if card_info is None:
            raise ChatHfHubError(404, "hf_not_found", "Repository has no card")
        if (getattr(card_info, "size", 0) or 0) > MAX_CARD_DOWNLOAD_BYTES:
            raise ChatHfHubError(
                413, "hf_card_too_large", "Repository card is too large"
            )
        self._check_deadline()
        with tempfile.TemporaryDirectory(prefix="pwc-hf-card-") as directory:
            path = self.api.hf_hub_download(
                args["repo_id"],
                "README.md",
                repo_type=repo_type,
                revision=sha,
                cache_dir=directory,
                token=False,
                etag_timeout=min(3, self._remaining_seconds()),
            )
            self._check_deadline()
            card_path = Path(path)
            source_bytes = card_path.stat().st_size
            total_limit = min(
                int(
                    getattr(
                        self.settings,
                        "chat_hf_card_total_max_bytes",
                        MAX_CARD_TOTAL_BYTES,
                    )
                ),
                MAX_CARD_TOTAL_BYTES,
            )
            with card_path.open("rb") as card_file:
                raw = card_file.read(total_limit + 1)
        text = raw.decode("utf-8", errors="replace")
        metadata, body = _split_card(text)
        metadata_limit = min(
            int(
                getattr(
                    self.settings,
                    "chat_hf_card_metadata_max_bytes",
                    MAX_CARD_METADATA_BYTES,
                )
            ),
            MAX_CARD_METADATA_BYTES,
        )
        text_limit = min(
            int(
                getattr(
                    self.settings, "chat_hf_card_text_max_bytes", MAX_CARD_TEXT_BYTES
                )
            ),
            MAX_CARD_TEXT_BYTES,
        )
        metadata, metadata_truncation = _bound_json(metadata, metadata_limit)
        metadata_bytes = len(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode()
        )
        text_limit = min(text_limit, max(0, total_limit - metadata_bytes))
        body, body_truncation = _bound_text(body, text_limit)
        data = {"metadata": metadata, "text": body}
        source = _source(repo_type, args["repo_id"], sha, card=True)
        source_truncation = None
        if source_bytes > total_limit:
            source_truncation = {
                "component": "source",
                "original_bytes": source_bytes,
                "returned_bytes": min(source_bytes, total_limit),
            }
        truncations = [
            v for v in (source_truncation, metadata_truncation, body_truncation) if v
        ]
        return _envelope(
            f"{repo_type}_card",
            data,
            source=source,
            truncation={"truncated": bool(truncations), "components": truncations},
        )

    @staticmethod
    def _project_card(envelope: dict, args: dict) -> dict:
        if not envelope.get("operation", "").endswith("_card"):
            return envelope
        if args.get("metadata"):
            envelope["data"].pop("text", None)
        elif args.get("text"):
            envelope["data"].pop("metadata", None)
        return envelope

    def _ensure_response_bound(self, envelope: dict) -> None:
        raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
        maximum = min(
            int(
                getattr(self.settings, "chat_hf_response_max_bytes", MAX_RESPONSE_BYTES)
            ),
            MAX_RESPONSE_BYTES,
        )
        if len(raw) > maximum:
            raise ChatHfHubError(
                503,
                "hf_unavailable",
                "Normalized HF response exceeded its safety bound",
            )

    def _bound_list_envelope(self, envelope: dict) -> dict:
        maximum = min(
            MAX_LIST_BYTES,
            int(
                getattr(self.settings, "chat_hf_response_max_bytes", MAX_RESPONSE_BYTES)
            ),
        )
        data = envelope["data"]
        original_count = len(data)
        while (
            data
            and len(
                json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
            )
            > maximum
        ):
            data.pop()
        if len(data) != original_count:
            envelope["truncation"] = {
                "truncated": True,
                "reason": "maximum_bytes",
            }
            result_set = envelope.get("result_set")
            if result_set:
                result_set["returned"] = len(data)
                result_set["more_available"] = True
        return envelope

    @staticmethod
    def _ttl(operation: str, args: dict) -> int:
        revision = args.get("revision")
        if revision and re.fullmatch(r"[0-9a-fA-F]{40,64}", revision):
            return 86400
        if operation.endswith("_card"):
            return 900
        if operation.endswith("_list") and "repo_id" not in args:
            return 300
        return 600


def _json_value(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (list, tuple)):
        return [_json_value(v, depth + 1) for v in value[:200]]
    if isinstance(value, dict):
        return {str(k): _json_value(v, depth + 1) for k, v in list(value.items())[:200]}
    if is_dataclass(value):
        return _json_value(asdict(value), depth + 1)
    return str(value)


def _normalize_repo(info: Any, repo_type: str, expands: list[str]) -> dict:
    base = [
        "id",
        "author",
        "sha",
        "lastModified",
        "last_modified",
        "createdAt",
        "created_at",
        "tags",
        "likes",
        "downloads",
        "pipeline_tag",
        "sdk",
        "gated",
        "private",
        "siblings",
    ]
    fields = list(dict.fromkeys(base + expands))
    result = {}
    for field in fields:
        attr = field.replace("-", "_")
        value = getattr(info, attr, None)
        if value is not None:
            key = {"lastModified": "last_modified", "createdAt": "created_at"}.get(
                field, field
            )
            result[key] = _json_value(value)
    if "id" not in result:
        result["id"] = str(
            getattr(
                info, "modelId", getattr(info, "datasetId", getattr(info, "id", ""))
            )
        )
    result["repo_type"] = repo_type
    result.pop("private", None)
    return result


def _normalize_collection(value: Any) -> dict:
    fields = (
        "slug",
        "title",
        "description",
        "owner",
        "lastModified",
        "position",
        "private",
        "theme",
        "upvotes",
        "items",
    )
    result = {
        key: _json_value(getattr(value, key, None))
        for key in fields
        if getattr(value, key, None) is not None
    }
    result.pop("private", None)
    return result


def _source(repo_type: str, repo_id: str, sha: str | None, card: bool = False) -> dict:
    prefix = {"model": "", "dataset": "datasets/", "space": "spaces/"}[repo_type]
    url = f"https://huggingface.co/{prefix}{repo_id}"
    source = {
        "provider": "huggingface_hub",
        "repo_id": repo_id,
        "repo_type": repo_type,
        "resolved_sha": sha,
        "url": url,
    }
    if card and sha:
        source["immutable_card_url"] = f"{url}/blob/{sha}/README.md"
    return source


def _envelope(
    operation: str,
    data: Any,
    *,
    source: dict | None = None,
    result_set: dict | None = None,
    truncation: dict | None = None,
) -> dict:
    value = {
        "schema_version": 1,
        "operation": operation,
        "data": data,
        "truncation": truncation or {"truncated": False, "reason": None},
    }
    if source:
        value["source"] = source
    if result_set:
        value["result_set"] = result_set
    return value


def _result_set(limit: int, returned: int, more: bool) -> dict:
    return {"limit": limit, "returned": returned, "more_available": more}


def _split_card(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    front = text[4:end]
    try:
        # Aliases let a small document expand multiplicatively once copied;
        # model cards have no use for them.
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(front)):
            metadata = {"_malformed_front_matter": True}
        else:
            metadata = yaml.safe_load(front) or {}
    except yaml.YAMLError:
        metadata = {"_malformed_front_matter": True}
    if not isinstance(metadata, dict):
        metadata = {"value": _json_value(metadata)}
    return _json_value(metadata), text[end + 5 :]


def _bound_text(value: str, maximum: int) -> tuple[str, dict | None]:
    raw = value.encode()
    if len(raw) <= maximum:
        return value, None
    marker = b"\n[HF card text truncated]\n"
    cut = raw[: max(0, maximum - len(marker))]
    while cut:
        try:
            returned = cut.decode()
            break
        except UnicodeDecodeError as error:
            cut = cut[: error.start]
    output = returned + marker.decode()
    return output[:maximum], {
        "component": "text",
        "original_bytes": len(raw),
        "returned_bytes": len(output.encode()),
    }


def _bound_json(value: dict, maximum: int) -> tuple[dict, dict | None]:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    if len(raw) <= maximum:
        return value, None
    return {"_truncated": True}, {
        "component": "metadata",
        "original_bytes": len(raw),
        "returned_bytes": len(b'{"_truncated":true}'),
    }
