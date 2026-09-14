"""Modal resource rates for the region pinned by the sandbox contract."""

from decimal import Decimal

from backend.chat_sandbox_worker.contract import CHAT_SANDBOX_REGION

# https://modal.com/docs/guide/region-selection (verified 2026-09-14).
# Keep placement changes explicit: an unknown region must not silently use base pricing.
_REGION_MULTIPLIERS = {"eu-west": Decimal("1.75")}
REGION_MULTIPLIER = _REGION_MULTIPLIERS[CHAT_SANDBOX_REGION]
CPU_MICROUSD_PER_CORE_SECOND = Decimal("39.42") * REGION_MULTIPLIER
MEMORY_MICROUSD_PER_GIB_SECOND = Decimal("6.72") * REGION_MULTIPLIER
MODAL_CPU_USD_PER_CORE_SECOND = float(CPU_MICROUSD_PER_CORE_SECOND / 1_000_000)
MODAL_MEMORY_USD_PER_GIB_SECOND = float(MEMORY_MICROUSD_PER_GIB_SECOND / 1_000_000)
