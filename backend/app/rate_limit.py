"""
backend/app/rate_limit.py

Dependency-free rate limiting and brute-force lockout. Deliberately NOT using
a third-party library (e.g. slowapi) here -- this project has already hit
real dependency-conflict pain once this session (react-three/drei's peer
dependency lagging React 19), and a rate limiter is simple enough to implement
correctly in ~60 lines of stdlib code without that risk.

Known, honest limitation: this is in-memory, per-process state. It works
correctly for a single server instance (which is what this project runs
today) but does NOT share state across multiple instances behind a load
balancer -- that would need a shared store (e.g. Redis). Documented here
rather than silently assumed away.
"""

import time
import threading
import logging
from collections import defaultdict, deque
from typing import Dict, Deque

from fastapi import HTTPException, Request

logger = logging.getLogger("clarimed.rate_limit")


class RateLimiter:
    """Sliding-window rate limiter keyed by an arbitrary string (usually
    client IP, sometimes an email for per-account limits)."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True

    def enforce(self, key: str, what: str = "requests") -> None:
        """Raises HTTP 429 if the caller has exceeded the limit."""
        if not self.allow(key):
            logger.warning("Rate limit exceeded for %s on %s", key, what)
            raise HTTPException(
                status_code=429,
                detail=f"Too many {what}. Please wait a moment and try again.",
            )


def client_key(request: Request) -> str:
    """Best-effort client identifier. request.client.host is what uvicorn
    sees directly -- behind a real reverse proxy this would need to read
    X-Forwarded-For instead, which is a known, documented gap for when this
    moves behind a proxy/load balancer in real deployment."""
    return request.client.host if request.client else "unknown"


class LoginAttemptTracker:
    """Brute-force lockout for the doctor login endpoint. After
    `max_failures` failed attempts for the same email within `window_seconds`,
    further attempts are rejected for `lockout_seconds`, regardless of
    whether the password given is now correct -- this deliberately doesn't
    reveal whether lockout is due to wrong guesses vs an unknown email, to
    avoid leaking which emails have real accounts.
    """

    def __init__(self, max_failures: int = 5, window_seconds: float = 300, lockout_seconds: float = 300):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._failures: Dict[str, Deque[float]] = defaultdict(deque)
        self._locked_until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def check_locked(self, email: str) -> None:
        now = time.monotonic()
        with self._lock:
            until = self._locked_until.get(email)
            if until and now < until:
                remaining = int(until - now)
                logger.warning("Login blocked for %s -- locked out for %ds more", email, remaining)
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many failed login attempts. Try again in {remaining} seconds.",
                )

    def record_failure(self, email: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._failures[email]
            hits.append(now)
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.max_failures:
                self._locked_until[email] = now + self.lockout_seconds
                logger.warning("Email %s locked out after %d failed attempts", email, len(hits))

    def record_success(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)
            self._locked_until.pop(email, None)


# Shared instances used across the app -- one rate limiter per concern, so a
# burst on one endpoint doesn't affect the budget of an unrelated one.
screening_limiter = RateLimiter(max_requests=20, window_seconds=60)       # /api/screen and similar LLM-backed calls
body_part_suggest_limiter = RateLimiter(max_requests=30, window_seconds=60)
doctor_login_ip_limiter = RateLimiter(max_requests=10, window_seconds=60)  # coarse, per-IP
login_attempts = LoginAttemptTracker()