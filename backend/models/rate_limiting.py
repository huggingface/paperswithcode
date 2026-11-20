"""
Shared rate limiting functionality for AI generators.

This module provides a mixin class that can be used by any generator
to implement consistent rate limiting and retry logic.
"""

import asyncio
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from abc import ABC

logger = logging.getLogger(__name__)


MAX_RETRY_DELAY_SECONDS = 300


class RateLimitingMixin(ABC):
    """
    Mixin class providing rate limiting and retry functionality for AI generators.

    This mixin can be used by any generator class to add consistent rate limiting,
    retry logic, and error handling capabilities.
    """

    def __init__(
        self, requests_per_minute: int = 20, requests_per_day: int = 50, **kwargs
    ):
        """
        Initialize rate limiting configuration.

        Args:
            requests_per_minute: Maximum requests per minute
            requests_per_day: Maximum requests per day
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(**kwargs)

        self.requests_per_minute = requests_per_minute
        self.requests_per_day = requests_per_day
        self.request_times = []
        self.daily_requests = 0
        self.last_reset = datetime.now().date()

        self.max_retries = 3
        self.base_delay = 1.0

    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if the error is a rate limit error."""
        error_str = str(error).lower()
        return (
            "rate limit" in error_str
            or "429" in error_str
            or "too many requests" in error_str
            or "resource_exhausted" in error_str
        )

    def _is_quota_exceeded_error(self, error: Exception) -> bool:
        """Check if the error is a quota exceeded error."""
        error_str = str(error).lower()
        return (
            "quota" in error_str
            or "limit exceeded" in error_str
            or "insufficient" in error_str
        )

    def _is_service_unavailable_error(self, error: Exception) -> bool:
        """Check if the error is a service unavailable error."""
        error_str = str(error).lower()
        return (
            "503" in error_str
            or "service unavailable" in error_str
            or "unavailable" in error_str
        )

    def _parse_retry_delay(self, error_str: str) -> Optional[int]:
        """
        Parse retry delay from error message.

        Supports multiple formats used by different APIs:
        - OpenRouter: "retry in 30 seconds"
        - Gemini: "'retryDelay': '30s'"
        - Generic: "wait 30 seconds"
        """
        try:
            patterns = [
                r"'retryDelay':\s*'(\d+)s'",
                r'"retryDelay":\s*"(\d+)s"',
                r"retry.*?in\s+(\d+)\s*seconds?",
                r"try again in\s+(\d+)\s*seconds?",
                r"wait\s+(\d+)\s*seconds?",
            ]

            for pattern in patterns:
                match = re.search(pattern, error_str, re.IGNORECASE)
                if match:
                    delay = int(match.group(1))
                    if delay <= MAX_RETRY_DELAY_SECONDS:
                        return delay
                    return None
        except (ValueError, AttributeError):
            pass
        return None

    async def _check_rate_limits(self):
        """Check and enforce rate limits."""
        now = datetime.now()

        if now.date() > self.last_reset:
            self.daily_requests = 0
            self.last_reset = now.date()
            logger.info(f"🔄 Daily counter reset. New day: {now.date()}")

        if self.daily_requests >= self.requests_per_day:
            wait_until = datetime.combine(
                now.date() + timedelta(days=1), datetime.min.time()
            )
            wait_seconds = (wait_until - now).total_seconds()
            logger.warning(
                f"🚫 Daily limit reached ({self.daily_requests}/{self.requests_per_day}). Waiting {wait_seconds / 3600:.1f} hours..."
            )
            raise Exception(
                f"Daily quota exceeded: {self.daily_requests}/{self.requests_per_day} requests used"
            )

        minute_ago = now - timedelta(minutes=1)
        self.request_times = [t for t in self.request_times if t > minute_ago]

        if len(self.request_times) >= self.requests_per_minute:
            wait_seconds = 60 - (now - self.request_times[0]).total_seconds() + 1
            logger.info(
                f"⏳ Rate limit reached ({len(self.request_times)}/{self.requests_per_minute}). Waiting {wait_seconds:.1f} seconds..."
            )
            await asyncio.sleep(wait_seconds)

        self.request_times.append(now)
        self.daily_requests += 1

    async def _handle_rate_limit_error(self, error: Exception, attempt: int) -> int:
        """Handle rate limit errors with exponential backoff."""
        error_str = str(error)

        retry_delay = self._parse_retry_delay(error_str)

        if retry_delay:
            delay = retry_delay
        else:
            delay = self.base_delay * (2**attempt)

        logger.warning(
            f"⏳ Rate limit error (attempt {attempt + 1}). Waiting {delay} seconds..."
        )
        await asyncio.sleep(delay)
        return delay

    async def _handle_service_unavailable_error(
        self, error: Exception, attempt: int
    ) -> int:
        """Handle service unavailable errors with exponential backoff."""
        error_str = str(error)

        retry_delay = self._parse_retry_delay(error_str)

        if retry_delay:
            delay = retry_delay
        else:
            delay = self.base_delay * (2**attempt)

        logger.warning(
            f"⏳ Service unavailable error (attempt {attempt + 1}). Waiting {delay} seconds..."
        )
        await asyncio.sleep(delay)
        return delay

    async def _execute_with_rate_limiting(self, api_call_func, *args, **kwargs):
        """
        Execute an API call with rate limiting and retry logic.

        Args:
            api_call_func: The actual API call function to execute
            *args: Arguments to pass to the API call function
            **kwargs: Keyword arguments to pass to the API call function

        Returns:
            The result of the API call function

        Raises:
            Exception: If max retries exceeded or quota exceeded
        """
        for attempt in range(self.max_retries):
            try:
                await self._check_rate_limits()

                result = await api_call_func(*args, **kwargs)

                logger.debug(
                    f"✅ API call successful. Daily: {self.daily_requests}/{self.requests_per_day}"
                )
                return result

            except Exception as e:
                if self._is_rate_limit_error(e):
                    if attempt < self.max_retries - 1:
                        await self._handle_rate_limit_error(e, attempt)
                        continue
                    else:
                        raise e
                elif self._is_service_unavailable_error(e):
                    if attempt < self.max_retries - 1:
                        await self._handle_service_unavailable_error(e, attempt)
                        continue
                    else:
                        raise e
                elif self._is_quota_exceeded_error(e):
                    logger.error(f"❌ Quota exceeded: {e}")
                    raise Exception(f"Daily quota exceeded: {e}")
                else:
                    if attempt == self.max_retries - 1:
                        raise e
                    else:
                        delay = self.base_delay * (2**attempt)
                        logger.warning(
                            f"⚠️ Request failed (attempt {attempt + 1}), retrying in {delay}s: {e}"
                        )
                        await asyncio.sleep(delay)

        raise Exception(f"Max retries ({self.max_retries}) exceeded")

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        recent_requests = len([t for t in self.request_times if t > minute_ago])

        return {
            "requests_per_minute": self.requests_per_minute,
            "requests_per_day": self.requests_per_day,
            "recent_requests": recent_requests,
            "daily_requests": self.daily_requests,
            "daily_remaining": max(0, self.requests_per_day - self.daily_requests),
            "minute_remaining": max(0, self.requests_per_minute - recent_requests),
            "last_reset": self.last_reset.isoformat(),
        }
