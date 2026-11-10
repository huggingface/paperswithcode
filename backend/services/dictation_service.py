"""Voice dictation for the chat composers.

The browser never talks to a speech provider directly and never holds a
provider credential. It asks for a single-use ticket, then opens
``/api/v1/dictation/ws?ticket=…`` on our own origin. nginx validates the ticket
through an ``auth_request`` to :meth:`DictationService.authorize`, which answers
with the upstream WebSocket URL and its ``Authorization`` header; nginx relays
the audio without it passing through Python.

Two providers:

* ``voxtral``: Voxtral Mini Realtime served by vLLM on a scale-to-zero HF
  Inference Endpoint. One L4 keeps up with about two live streams.
* ``openai``: OpenAI Realtime transcription, used while the endpoint is cold
  or full, under a global daily cap.

Each ticket reserves a full session (``dictation_session_seconds``) against the
user's daily allowance until the browser reports the real duration.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import DictationSession

VOXTRAL = "voxtral"
OPENAI = "openai"
TICKET_TTL = timedelta(seconds=30)
RETENTION = timedelta(days=30)
# A connected session that never reported back stops counting as live after
# its maximum length plus a grace period for the final transcript.
LIVE_GRACE_SECONDS = 15
OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime?intent=transcription"
SAMPLE_RATES = {VOXTRAL: 16_000, OPENAI: 24_000}

# Bias the OpenAI fallback towards the catalog's vocabulary. Voxtral's realtime
# API has no prompt field.
VOCABULARY = (
    "Papers with Code, arXiv, Hugging Face, LoRA, QLoRA, RLHF, DPO, GRPO, PPO, "
    "SFT, MoE, Mixture of Experts, KV cache, FlashAttention, RoPE, LayerNorm, "
    "RMSNorm, GELU, SwiGLU, Transformer, ViT, CLIP, SigLIP, DINOv2, SAM, BERT, "
    "RoBERTa, T5, GPT, Llama, Mistral, Mixtral, Qwen, DeepSeek, Gemma, Phi, "
    "Claude, Gemini, Voxtral, Whisper, Mamba, RWKV, U-Net, ResNet, YOLO, DETR, "
    "NeRF, Gaussian Splatting, diffusion, DDPM, DDIM, latent diffusion, "
    "Stable Diffusion, flow matching, VAE, GAN, contrastive learning, "
    "distillation, quantization, pruning, speculative decoding, RAG, "
    "chain-of-thought, in-context learning, tokenizer, embeddings, "
    "ImageNet, COCO, MMLU, GSM8K, MATH, HumanEval, SWE-bench, GPQA, "
    "LiveCodeBench, ARC-AGI, LibriSpeech, WER, BLEU, ROUGE, mAP, FID, "
    "perplexity, state of the art, SOTA, benchmark, leaderboard, ablation"
)


class DictationUnavailable(Exception):
    """No provider can take a new dictation session right now."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class DictationTicketRejected(Exception):
    """The ticket is unknown, expired, or already used."""


@dataclass(frozen=True)
class DictationStatus:
    provider: str | None
    reason: str | None
    remaining_seconds: int


@dataclass(frozen=True)
class IssuedTicket:
    session_id: uuid.UUID
    ticket: str
    provider: str
    model: str
    sample_rate: int
    max_seconds: int
    prompt: str | None


@dataclass(frozen=True)
class Upstream:
    url: str
    authorization: str


_probe_lock = threading.Lock()
_probe_cache: dict[str, tuple[float, bool]] = {}


def probe_endpoint(
    url: str,
    token: str,
    *,
    wake: bool = True,
    ttl_ready: float = 10,
    ttl_cold: float = 15,
) -> bool:
    """Return whether the endpoint is serving, waking it if it scaled to zero.

    Any request to a scaled-to-zero HF endpoint starts it (and gets a 503), so
    the health probe doubles as the wake-up call. Results are cached briefly so
    polling clients do not turn into a probe per request. With ``wake=False``
    only a fresh cached answer counts and nothing is sent, so the endpoint is
    not kept awake by callers who may never dictate.
    """

    now = time.monotonic()
    with _probe_lock:
        cached = _probe_cache.get(url)
        if cached and cached[0] > now:
            return cached[1]
    if not wake:
        return False
    try:
        response = httpx.get(
            f"{url.rstrip('/')}/health",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3.0,
        )
        ready = response.status_code == 200
    except httpx.HTTPError:
        ready = False
    with _probe_lock:
        _probe_cache[url] = (now + (ttl_ready if ready else ttl_cold), ready)
    return ready


def hash_ticket(ticket: str) -> str:
    return hashlib.sha256(ticket.encode()).hexdigest()


def ticket_from_uri(original_uri: str) -> str:
    """Read ``ticket`` from the original request URI nginx forwards."""

    values = parse_qs(urlsplit(original_uri).query).get("ticket") or [""]
    return values[0]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class DictationService:
    def __init__(self, db: Session, settings: Settings, *, probe=None, now=_utcnow):
        self.db = db
        self.settings = settings
        self._probe = probe or probe_endpoint
        self._now = now

    # -- metering -----------------------------------------------------------

    def _charged_seconds(self):
        """Seconds a row counts against an allowance.

        Unused tickets cost nothing; a connected session costs its reported
        duration, or its full reservation while it has not reported one.
        """

        return func.coalesce(
            DictationSession.used_seconds, DictationSession.max_seconds
        )

    def _user_used_today(self, hf_subject: str, now: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.coalesce(func.sum(self._charged_seconds()), 0)).where(
                    DictationSession.hf_subject == hf_subject,
                    DictationSession.connected_at.is_not(None),
                    DictationSession.issued_at >= _day_start(now),
                )
            )
        )

    def _openai_used_today(self, now: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.coalesce(func.sum(self._charged_seconds()), 0)).where(
                    DictationSession.provider == OPENAI,
                    DictationSession.connected_at.is_not(None),
                    DictationSession.issued_at >= _day_start(now),
                )
            )
        )

    def _live_filter(self, now: datetime):
        """Sessions that hold a stream now, or a fresh ticket about to open one."""

        live_since = now - timedelta(
            seconds=self.settings.dictation_session_seconds + LIVE_GRACE_SECONDS
        )
        return and_(
            DictationSession.finished_at.is_(None),
            or_(
                DictationSession.connected_at >= live_since,
                and_(
                    DictationSession.connected_at.is_(None),
                    DictationSession.issued_at >= now - TICKET_TTL,
                ),
            ),
        )

    def _live_count(self, now: datetime, **filters) -> int:
        conditions = [self._live_filter(now)]
        if "provider" in filters:
            conditions.append(DictationSession.provider == filters["provider"])
        if "hf_subject" in filters:
            conditions.append(DictationSession.hf_subject == filters["hf_subject"])
        return int(self.db.scalar(select(func.count()).where(*conditions)))

    # -- provider choice ----------------------------------------------------

    def _voxtral_ready(self, *, wake: bool) -> bool:
        url = self.settings.dictation_endpoint_url
        return bool(url) and self._probe(url, self.settings.hf_token, wake=wake)

    def _choose(self, hf_subject: str, now: datetime, *, wake: bool) -> DictationStatus:
        remaining = max(
            0,
            self.settings.dictation_user_daily_seconds
            - self._user_used_today(hf_subject, now),
        )
        if remaining <= 0:
            return DictationStatus(None, "daily_limit", 0)
        openai_left = (
            self.settings.dictation_openai_daily_seconds - self._openai_used_today(now)
        )
        openai_ok = bool(self.settings.openai_api_key) and (
            openai_left >= self.settings.dictation_session_seconds
        )
        # Without the OpenAI fallback, waking Voxtral is the only way to serve.
        voxtral_ready = self._voxtral_ready(wake=wake or not openai_ok)
        if (
            voxtral_ready
            and self._live_count(now, provider=VOXTRAL)
            < self.settings.dictation_voxtral_capacity
        ):
            return DictationStatus(VOXTRAL, None, remaining)
        if openai_ok:
            return DictationStatus(OPENAI, None, remaining)
        return DictationStatus(None, "busy" if voxtral_ready else "starting", remaining)

    def status(self, hf_subject: str) -> DictationStatus:
        """Report availability without waking the endpoint; a mic tap wakes it."""

        return self._choose(hf_subject, self._now(), wake=False)

    # -- tickets ------------------------------------------------------------

    def issue(self, hf_subject: str) -> IssuedTicket:
        now = self._now()
        # A new ticket replaces any of the user's tickets that never connected.
        self.db.execute(
            update(DictationSession)
            .where(
                DictationSession.hf_subject == hf_subject,
                DictationSession.connected_at.is_(None),
                DictationSession.finished_at.is_(None),
            )
            .values(finished_at=now)
            .execution_options(synchronize_session=False)
        )
        if self._live_count(now, hf_subject=hf_subject):
            raise DictationUnavailable("already_dictating")
        choice = self._choose(hf_subject, now, wake=True)
        if choice.provider is None:
            raise DictationUnavailable(choice.reason or "unavailable")
        self.db.execute(
            delete(DictationSession)
            .where(DictationSession.issued_at < now - RETENTION)
            .execution_options(synchronize_session=False)
        )
        ticket = secrets.token_urlsafe(32)
        max_seconds = min(
            self.settings.dictation_session_seconds, choice.remaining_seconds
        )
        session = DictationSession(
            id=uuid.uuid4(),
            hf_subject=hf_subject,
            provider=choice.provider,
            ticket_hash=hash_ticket(ticket),
            issued_at=now,
            max_seconds=max_seconds,
        )
        self.db.add(session)
        self.db.commit()
        openai = choice.provider == OPENAI
        return IssuedTicket(
            session_id=session.id,
            ticket=ticket,
            provider=choice.provider,
            model=self.settings.dictation_openai_model
            if openai
            else self.settings.dictation_voxtral_model,
            sample_rate=SAMPLE_RATES[choice.provider],
            max_seconds=max_seconds,
            prompt=VOCABULARY if openai else None,
        )

    def authorize(self, ticket: str) -> Upstream:
        """Consume a ticket for nginx and name the upstream it may open."""

        now = self._now()
        provider = self.db.execute(
            update(DictationSession)
            .where(
                DictationSession.ticket_hash == hash_ticket(ticket),
                DictationSession.connected_at.is_(None),
                DictationSession.finished_at.is_(None),
                DictationSession.issued_at >= now - TICKET_TTL,
            )
            .values(connected_at=now)
            .returning(DictationSession.provider)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        self.db.commit()
        if provider == VOXTRAL:
            url = self.settings.dictation_endpoint_url.rstrip("/") + "/v1/realtime"
            return Upstream(url, f"Bearer {self.settings.hf_token}")
        if provider == OPENAI:
            return Upstream(
                OPENAI_REALTIME_URL, f"Bearer {self.settings.openai_api_key}"
            )
        raise DictationTicketRejected()

    def finish(self, hf_subject: str, session_id: uuid.UUID, seconds: float) -> None:
        """Settle a session at the duration the browser recorded."""

        session = self.db.get(DictationSession, session_id)
        if session is None or session.hf_subject != hf_subject or session.finished_at:
            return
        session.finished_at = self._now()
        if session.connected_at is not None:
            session.used_seconds = max(0, min(round(seconds), session.max_seconds))
        self.db.commit()
