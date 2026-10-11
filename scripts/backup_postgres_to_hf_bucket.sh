#!/usr/bin/env bash
set -euo pipefail

# Database backups contain private user data.
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PWC_BACKUP_ENV_FILE:-}"
CREDENTIAL_ENV_FILE="${PWC_BACKUP_CREDENTIAL_ENV_FILE:-}"
BACKUP_DIR="${PWC_POSTGRES_BACKUP_DIR:-/var/lib/paperswithcode/production/backups}"
REMOTE_BUCKET=""
REMOTE_PREFIX="postgres"
REMOTE_URI=""
HF_BIN="${HF_BIN:-/srv/paperswithcode/.venv/bin/hf}"
tmp_dump=""

log() {
    printf '[backup] %s\n' "$*"
}

die() {
    printf '[backup] ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

resolve_hf() {
    if [[ -x "$HF_BIN" ]]; then
        return
    fi

    if HF_BIN="$(command -v hf 2>/dev/null)"; then
        return
    fi

    die "Required command not found: hf"
}

run_hf() {
    if [[ -n "${PWC_POSTGRES_BACKUP_HF_TOKEN:-}" ]]; then
        env HF_TOKEN="$PWC_POSTGRES_BACKUP_HF_TOKEN" \
            "$HF_BIN" "$@"
        return
    fi
    "$HF_BIN" "$@"
}

require_private_bucket() {
    # Reject unavailable, malformed, missing, or non-boolean privacy metadata.
    # Never print the response: only the affirmative private flag permits upload.
    if ! run_hf buckets info "$REMOTE_BUCKET" --format json | python3 -c '
import json
import sys
try:
    metadata = json.load(sys.stdin)
except (ValueError, UnicodeError):
    sys.exit(1)
sys.exit(0 if isinstance(metadata, dict) and metadata.get("private") is True else 1)
'; then
        die "Backup bucket privacy could not be verified; refusing to continue"
    fi
}

validate_keep_count() {
    local name="$1"
    local value="$2"

    [[ "$value" =~ ^[0-9]+$ ]] || die "$name must be a non-negative integer, got: $value"
}

prune_local_backups() {
    shopt -s nullglob
    local dumps=("$BACKUP_DIR"/"${PWC_DB_NAME}"_*.dump)
    shopt -u nullglob

    if (( ${#dumps[@]} <= LOCAL_KEEP_COUNT )); then
        log "Local prune: nothing to delete (${#dumps[@]}/$LOCAL_KEEP_COUNT dumps kept)"
        return
    fi

    readarray -t dumps < <(printf '%s\n' "${dumps[@]}" | sort)
    local delete_count=$(( ${#dumps[@]} - LOCAL_KEEP_COUNT ))

    log "Local prune: deleting $delete_count old dump(s)"
    local index
    for (( index = 0; index < delete_count; index++ )); do
        local dump_path="${dumps[$index]}"
        log "Pruned local: $dump_path"
        rm -f -- "$dump_path" "$dump_path.sha256"
    done
}

list_remote_files() {
    run_hf buckets list "$REMOTE_BUCKET/$REMOTE_PREFIX" --recursive --format quiet
}

verify_remote_upload() {
    local dump_name="$1"
    local checksum_name="$2"
    local listing

    listing="$(list_remote_files)"
    printf '%s\n' "$listing" | sed 's/^/[backup] remote: /'

    grep -Fxq "$REMOTE_PREFIX/$dump_name" <<<"$listing" \
        || die "Uploaded dump missing from remote listing: $REMOTE_PREFIX/$dump_name"
    grep -Fxq "$REMOTE_PREFIX/$checksum_name" <<<"$listing" \
        || die "Uploaded checksum missing from remote listing: $REMOTE_PREFIX/$checksum_name"
}

prune_remote_backups() {
    local listing="$1"
    local remote_dumps=()
    local remote_path

    while IFS= read -r remote_path; do
        local filename="${remote_path##*/}"
        if [[ "$filename" == "${PWC_DB_NAME}"_*.dump && "$filename" != *.dump.sha256 ]]; then
            remote_dumps+=("$remote_path")
        fi
    done <<<"$listing"

    if (( ${#remote_dumps[@]} <= REMOTE_KEEP_COUNT )); then
        log "Remote prune: nothing to delete (${#remote_dumps[@]}/$REMOTE_KEEP_COUNT dumps kept)"
        return
    fi

    readarray -t remote_dumps < <(printf '%s\n' "${remote_dumps[@]}" | sort)
    local delete_count=$(( ${#remote_dumps[@]} - REMOTE_KEEP_COUNT ))

    log "Remote prune: deleting $delete_count old dump(s)"
    local index
    for (( index = 0; index < delete_count; index++ )); do
        local remote_dump="${remote_dumps[$index]}"
        log "Pruned remote: $remote_dump"
        run_hf buckets remove "$REMOTE_BUCKET/$remote_dump" --yes
        run_hf buckets remove "$REMOTE_BUCKET/$remote_dump.sha256" --yes
    done
}

main() {
    if [[ -n "$ENV_FILE" ]]; then
        [[ -f "$ENV_FILE" ]] || die "Missing env file: $ENV_FILE"
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE"
        set +a
    fi
    if [[ -n "$CREDENTIAL_ENV_FILE" ]]; then
        [[ -f "$CREDENTIAL_ENV_FILE" ]] || die "Missing credential env file: $CREDENTIAL_ENV_FILE"
        set -a
        # shellcheck disable=SC1090
        source "$CREDENTIAL_ENV_FILE"
        set +a
    fi

    REMOTE_BUCKET="${PWC_POSTGRES_BACKUP_BUCKET:-huggingface/paperswithcode-backups}"
    REMOTE_URI="hf://buckets/$REMOTE_BUCKET/$REMOTE_PREFIX/"
    [[ -n "${PWC_DB_NAME:-}" ]] || die "PWC_DB_NAME is required"
    # The Hub bucket is the durable 30-day store. Keep only a few recent dumps
    # on the VPS so database growth does not consume the production filesystem.
    local local_keep_count="${PWC_POSTGRES_BACKUP_LOCAL_KEEP_COUNT:-3}"
    local remote_keep_count="${PWC_POSTGRES_BACKUP_REMOTE_KEEP_COUNT:-30}"
    LOCAL_KEEP_COUNT="$local_keep_count"
    REMOTE_KEEP_COUNT="$remote_keep_count"
    validate_keep_count "PWC_POSTGRES_BACKUP_LOCAL_KEEP_COUNT" "$LOCAL_KEEP_COUNT"
    validate_keep_count "PWC_POSTGRES_BACKUP_REMOTE_KEEP_COUNT" "$REMOTE_KEEP_COUNT"
    require_command python3
    require_command pg_dump
    require_command sha256sum
    resolve_hf

    if [[ -n "${PWC_POSTGRES_BACKUP_HF_TOKEN:-}" ]]; then
        export HF_TOKEN="$PWC_POSTGRES_BACKUP_HF_TOKEN"
    elif [[ -n "${PWC_HF_TOKEN:-}" && -z "${HF_TOKEN:-}" ]]; then
        export HF_TOKEN="$PWC_HF_TOKEN"
    fi
    [[ -n "${HF_TOKEN:-}" ]] || die "PWC_POSTGRES_BACKUP_HF_TOKEN, HF_TOKEN, or PWC_HF_TOKEN is required for Hugging Face bucket uploads"

    require_private_bucket

    mkdir -p "$BACKUP_DIR"

    local timestamp backup_name dump_path checksum_path remote_listing
    timestamp="$(date -u +%Y%m%d_%H%M%S)"
    backup_name="${PWC_DB_NAME}_${timestamp}.dump"
    # PrivateTmp may be another mount: copying a full dump can fill the disk.
    # Keep the in-progress file beside its final name for an atomic rename.
    tmp_dump="$(mktemp "$BACKUP_DIR/.$backup_name.XXXXXX.partial")"
    trap 'rm -f -- "$tmp_dump"' EXIT
    dump_path="$BACKUP_DIR/$backup_name"
    checksum_path="$dump_path.sha256"

    log "Dumping database: $PWC_DB_NAME"
    local backup_user="${PWC_POSTGRES_BACKUP_DB_USER:-${PWC_DB_USER:-}}"
    local backup_password="${PWC_POSTGRES_BACKUP_DB_PASSWORD:-${PWC_DB_PASSWORD:-}}"
    [[ -n "$backup_user" && -n "$backup_password" ]] \
        || die "dedicated PostgreSQL backup credentials are required"
    PGPASSWORD="$backup_password" pg_dump \
        -h "${PWC_DB_HOST:-localhost}" \
        -p "${PWC_DB_PORT:-5432}" \
        -U "$backup_user" \
        -d "$PWC_DB_NAME" \
        --schema=public \
        --schema=staging \
        -Fc -Z 9 -f "$tmp_dump"

    [[ -s "$tmp_dump" ]] || die "Dump file is missing or empty: $tmp_dump"
    mv "$tmp_dump" "$dump_path"
    trap - EXIT

    (
        cd "$BACKUP_DIR"
        sha256sum "$backup_name" > "$backup_name.sha256"
    )

    log "Local dump path: $dump_path"
    log "Local dump size: $(du -h "$dump_path" | awk '{print $1}')"
    log "Local checksum path: $checksum_path"
    log "Remote bucket path: $REMOTE_URI"

    require_private_bucket
    log "Uploading dump"
    run_hf buckets cp "$dump_path" "$REMOTE_URI"
    log "Uploading checksum"
    run_hf buckets cp "$checksum_path" "$REMOTE_URI"

    log "Verifying remote listing"
    verify_remote_upload "$backup_name" "$backup_name.sha256"

    log "Verifying local checksum"
    (
        cd "$BACKUP_DIR"
        sha256sum -c "$backup_name.sha256"
    )

    require_private_bucket
    prune_local_backups
    remote_listing="$(list_remote_files)"
    prune_remote_backups "$remote_listing"

    log "Backup completed successfully"
}

main "$@"
