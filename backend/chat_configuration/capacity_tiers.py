"""Reviewed chat capacity tiers shared by the runtime profile and host tooling.

Keys are admitted concurrent turns. Each environment's OpenAI call allowance
per rate-limit window belongs to the tier; see ADR 0021.
"""

CHAT_CAPACITY_TIERS = (32, 64)
CHAT_CAPACITY_TIER_OPENAI_RATE_LIMIT_CALLS = {
    "production": {32: 512, 64: 4096},
    "staging": {32: 300, 64: 4096},
}
