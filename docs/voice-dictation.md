# Voice dictation

The chat composers (homepage, `/chat`, paper reader) have a mic button that
streams speech into the message box as text.

## How it works

1. On mount, chat surfaces call `GET /api/v1/dictation/status`, which reports
   whether a signed-in user can dictate. It does not contact the speech
   endpoint (unless the OpenAI fallback is exhausted), so page views never keep
   the GPU awake.
2. Tapping the mic opens the microphone, then `POST /api/v1/dictation/sessions`
   probes the speech endpoint's `/health` (which wakes it from scale-to-zero),
   picks a provider, and issues a single-use ticket (valid 30 s; only its
   SHA-256 is stored). The first tap after an idle hour therefore uses OpenAI
   while Voxtral spends about 2 minutes starting.
3. The browser opens `wss://<site>/api/v1/dictation/ws?ticket=…`. nginx sends an
   `auth_request` to `/api/internal/dictation/authorize`, which consumes the
   ticket and answers with the upstream URL and its `Authorization` header in
   response headers. nginx relays the WebSocket there. The browser never sees a
   provider credential, and audio never passes through Python.
4. On stop, the browser reports the recorded seconds to
   `POST /api/v1/dictation/sessions/{id}/finish`.

No audio or transcript is stored. `dictation_sessions` keeps ticket hashes and
seconds for 30 days to enforce limits.

## Providers

| Provider | When | Audio |
| --- | --- | --- |
| Voxtral Mini 4B Realtime (vLLM on HF Inference Endpoint) | endpoint healthy and fewer than `PWC_DICTATION_VOXTRAL_CAPACITY` (2) live streams | PCM16 16 kHz |
| OpenAI Realtime transcription (`gpt-4o-mini-transcribe`) | endpoint cold, waking, or full, while the global daily OpenAI cap lasts | PCM16 24 kHz |

One L4 keeps up with two concurrent streams (final text within ~1 s of
stopping); a third makes every stream lag 4–7 s, so the third concurrent user
goes to OpenAI. A cold start from zero takes about 2 minutes.

## Limits (settings)

| Setting | Default |
| --- | --- |
| `PWC_DICTATION_SESSION_SECONDS` | 120 per session; the endpoint's `--max-model-len 2304` enforces it server-side |
| `PWC_DICTATION_USER_DAILY_SECONDS` | 1800 per user per UTC day |
| `PWC_DICTATION_OPENAI_DAILY_SECONDS` | 18000 across all users per UTC day |
| one live session per user | always |

## Endpoint

The endpoint image is `deploy/dictation/Dockerfile` (stock vLLM lacks the
`soundfile` extra the realtime route needs). It is built by the public,
build-only Space `nielsr/pwc-voxtral-vllm`; Inference Endpoints pull it as
`registry.hf.space/nielsr-pwc-voxtral-vllm:latest` (they cannot pull private
Space images or `hf.co/spaces/…` references). The Space shows a runtime error
because it has no GPU; only its built image matters.

```bash
uv run --env-file backend/keys.env python -m backend.cli dictation endpoint-plan --namespace nielsr --revision <model-sha>
```

Add `--execute --confirm DEPLOY_HF_ENDPOINT` to create or update it.

## Enabling an environment

1. Apply `backend/database/migrations/add_dictation_sessions.sql` as `postgres`
   with `search_path=staging,public` (staging) or `public` (production).
2. Install the nginx template with `pwc-nginx` (the relay locations).
3. Set `PWC_DICTATION_ENABLED=true` and `PWC_DICTATION_ENDPOINT_URL` in the
   environment file, then redeploy.
