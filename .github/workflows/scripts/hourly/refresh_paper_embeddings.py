"""Hourly bounded refresh of missing/stale active-generation paper embeddings."""

from __future__ import annotations

import argparse
import json
import os
import sys

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.incremental_paper_embeddings import refresh_active_embeddings
from scripts.utils.cron_helpers import CronJobBase


class RefreshPaperEmbeddingsJob(CronJobBase):
    def __init__(self, *, limit: int = 500, batch_size: int = 16):
        super().__init__(job_name="refresh_paper_embeddings", log_level="INFO")
        self.limit = limit
        self.batch_size = batch_size

    def run(self) -> None:
        settings = get_settings()
        endpoint_url = (
            os.environ.get("PWC_PAPER_EMBEDDING_ENDPOINT_URL")
            or settings.hf_query_embedding_endpoint_url
        )
        if not endpoint_url:
            raise RuntimeError(
                "Set PWC_PAPER_EMBEDDING_ENDPOINT_URL or "
                "PWC_HF_QUERY_EMBEDDING_ENDPOINT_URL"
            )
        if not settings.hf_token:
            raise RuntimeError("PWC_HF_TOKEN is required")

        with db_manager.session_local() as db:
            result = refresh_active_embeddings(
                db,
                endpoint_url=endpoint_url,
                token=settings.hf_token,
                limit=self.limit,
                batch_size=self.batch_size,
            )
        self.logger.info("Generation: %d", result.generation_id)
        self.logger.info("Candidates: %d", result.candidates)
        self.logger.info("Embeddings updated: %d", result.embedded)
        self.logger.info("Stale during inference: %d", result.stale)
        self.logger.info("Missing remaining: %d", result.missing_remaining)
        self.logger.info("Content hash mismatches: %d", result.content_hash_mismatches)
        self.logger.info("Run ID: %s", result.run_id)
        self.logger.info(
            "PAPER_EMBEDDINGS_SUMMARY %s",
            json.dumps(
                {
                    "generation_id": result.generation_id,
                    "candidates": result.candidates,
                    "embeddings_updated": result.embedded,
                    "stale_during_inference": result.stale,
                    "missing_remaining": result.missing_remaining,
                    "content_hash_mismatches": result.content_hash_mismatches,
                    "run_id": str(result.run_id),
                }
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("PWC_EMBEDDING_CRON_LIMIT", "500")),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("PWC_EMBEDDING_CRON_BATCH_SIZE", "16")),
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if not 1 <= args.batch_size <= 128:
        parser.error("--batch-size must be between 1 and 128")
    return (
        0
        if RefreshPaperEmbeddingsJob(
            limit=args.limit, batch_size=args.batch_size
        ).execute()
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
