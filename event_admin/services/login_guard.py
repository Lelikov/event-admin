"""In-memory login throttling and TOTP replay protection.

Per-process state is acceptable for a single-instance admin API; a
multi-replica deployment would need a shared store (documented in AUDIT.md).
"""

import time

import structlog


logger = structlog.get_logger(__name__)

# A TOTP code is valid for its 30s step plus pyotp's default +/-1 window;
# remembering the last accepted code for 90s covers the full validity span.
TOTP_REPLAY_WINDOW_SECONDS = 90


class LoginGuard:
    """Fixed-window failure lockout per key plus one-time TOTP acceptance."""

    def __init__(self, *, max_failures: int = 5, lockout_seconds: int = 300) -> None:
        self._max_failures = max_failures
        self._lockout_seconds = lockout_seconds
        self._failures: dict[str, tuple[int, float]] = {}
        self._used_totp: dict[str, tuple[str, float]] = {}

    def is_locked(self, key: str) -> bool:
        entry = self._failures.get(key)
        if entry is None:
            return False
        count, window_start = entry
        if time.monotonic() - window_start > self._lockout_seconds:
            del self._failures[key]
            return False
        return count >= self._max_failures

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        count, window_start = self._failures.get(key, (0, now))
        if now - window_start > self._lockout_seconds:
            count, window_start = 0, now
        count += 1
        self._failures[key] = (count, window_start)
        if count >= self._max_failures:
            logger.warning("login_lockout_engaged", key=key, failures=count)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

    def totp_is_replay(self, email: str, code: str) -> bool:
        entry = self._used_totp.get(email)
        if entry is None:
            return False
        used_code, used_at = entry
        if time.monotonic() - used_at > TOTP_REPLAY_WINDOW_SECONDS:
            del self._used_totp[email]
            return False
        return used_code == code

    def mark_totp_used(self, email: str, code: str) -> None:
        self._used_totp[email] = (code, time.monotonic())
