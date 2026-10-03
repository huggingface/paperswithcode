"""Effective turn capabilities, resolved before capacity or session mutation."""

from dataclasses import dataclass

from backend.config import Settings


@dataclass(frozen=True, slots=True)
class TurnMode:
    reader_mode: bool
    poster_mode: bool
    paper_artifacts_enabled: bool
    lease_seconds: int

    @property
    def ordinary_research(self) -> bool:
        return not self.poster_mode and not self.paper_artifacts_enabled


def resolve_turn_mode(
    settings: Settings, *, primary_paper_id: int | None, poster_intent: bool
) -> TurnMode:
    """Use bound/new-session identity and the effective (possibly retried) request."""
    reader_mode = primary_paper_id is not None
    poster_mode = (
        settings.chat_artifacts_enabled
        and settings.chat_posterly_enabled
        and poster_intent
    )
    return TurnMode(
        reader_mode=reader_mode,
        poster_mode=poster_mode,
        paper_artifacts_enabled=(
            settings.chat_artifacts_enabled
            and settings.chat_latex_paper_enabled
            and settings.chat_latex_compiler_jobs_enabled
            and not reader_mode
        ),
        lease_seconds=(
            settings.chat_posterly_timeout_seconds
            if poster_mode
            else settings.chat_timeout_seconds
        )
        + 30,
    )
