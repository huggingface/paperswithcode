#!/bin/bash
#
# GitHub Repository Cleanup Wrapper Script
#
# This script provides a safe wrapper for cleaning up invalid GitHub repositories
# from the database. It includes memory checks and proper logging.
#

# Set PATH for cron environment
export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PROJECT_DIR/.github/workflows:${PYTHONPATH:-}"

# Set working directory
cd "$PROJECT_DIR" || exit 1

# Parse command line arguments
DRY_RUN=true
LIMIT=""
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --live)
            DRY_RUN=false
            shift
            ;;
        --limit)
            LIMIT="--limit $2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --live          Run in live mode (actually remove repositories)"
            echo "  --limit N       Process only N unique repositories"
            echo "  --force         Skip confirmation prompts"
            echo "  --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                          # Dry run (safe)"
            echo "  $0 --limit 100             # Dry run with limit"
            echo "  $0 --live --limit 50       # Live cleanup of 50 repos"
            echo "  $0 --live --force          # Live cleanup without confirmation"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create log file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$SCRIPT_DIR/logs/cleanup_invalid_repositories_${TIMESTAMP}.log"
mkdir -p "$SCRIPT_DIR/logs"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting GitHub Repository Cleanup" | tee -a "$LOG_FILE"

# Check available memory before starting
AVAILABLE_MEM=$(free -m | awk 'NR==2{printf "%.0f", $7}')
echo "$(date '+%Y-%m-%d %H:%M:%S') - Available memory: ${AVAILABLE_MEM}MB" | tee -a "$LOG_FILE"

# Don't start if less than 500MB available
if [ "$AVAILABLE_MEM" -lt 500 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Insufficient memory (${AVAILABLE_MEM}MB < 500MB)" | tee -a "$LOG_FILE"
    exit 1
fi

# Check environment file
if [ ! -f "backend/keys.env" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Environment file not found" | tee -a "$LOG_FILE"
    exit 1
fi

# Safety confirmation for live mode
if [ "$DRY_RUN" = false ] && [ "$FORCE" = false ]; then
    echo ""
    echo "⚠️  WARNING: You are about to run in LIVE mode!"
    echo "This will permanently delete invalid repositories from the database."
    echo ""
    echo "Recommendations:"
    echo "1. Run a dry-run first: $0 --limit 100"
    echo "2. Check the logs and backup files"
    echo "3. Consider starting with a small limit: $0 --live --limit 10"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Operation cancelled."
        exit 0
    fi
fi

# Build command arguments
CMD_ARGS=""
if [ "$DRY_RUN" = true ]; then
    CMD_ARGS="$CMD_ARGS --dry-run"
else
    CMD_ARGS="$CMD_ARGS --live"
fi

if [ -n "$LIMIT" ]; then
    CMD_ARGS="$CMD_ARGS $LIMIT"
fi

# Show what we're about to do
MODE="DRY RUN"
if [ "$DRY_RUN" = false ]; then
    MODE="LIVE MODE"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Mode: $MODE" | tee -a "$LOG_FILE"
if [ -n "$LIMIT" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Limit: $LIMIT" | tee -a "$LOG_FILE"
fi

# Run the cleanup script
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting cleanup process..." | tee -a "$LOG_FILE"

timeout 60m uv run --env-file backend/keys.env python -m scripts.maintenance.cleanup_invalid_repositories $CMD_ARGS 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

# Check final memory state
FINAL_MEM=$(free -m | awk 'NR==2{printf "%.0f", $7}')
echo "$(date '+%Y-%m-%d %H:%M:%S') - Final available memory: ${FINAL_MEM}MB" | tee -a "$LOG_FILE"

if [ $EXIT_CODE -eq 124 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Job timed out (60min limit)" | tee -a "$LOG_FILE"
    exit 0
elif [ $EXIT_CODE -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleanup completed successfully" | tee -a "$LOG_FILE"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Log file: $LOG_FILE" | tee -a "$LOG_FILE"

    # Show backup file location if in live mode
    if [ "$DRY_RUN" = false ]; then
        BACKUP_FILE=$(find "$SCRIPT_DIR/logs" -name "removed_repositories_backup_*.json" -newer "$LOG_FILE" 2>/dev/null | head -1)
        if [ -n "$BACKUP_FILE" ]; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup file: $BACKUP_FILE" | tee -a "$LOG_FILE"
        fi
    fi

    exit 0
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleanup failed with exit code: $EXIT_CODE" | tee -a "$LOG_FILE"
    exit $EXIT_CODE
fi
