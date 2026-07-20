"""
tests/test_rate_limit.py

Tests the dependency-free rate limiter and brute-force lockout used across
the backend's cost-sensitive and auth endpoints.
"""

import time
import pytest
from backend.app.rate_limit import RateLimiter, LoginAttemptTracker
from fastapi import HTTPException


def test_rate_limiter_allows_up_to_the_limit():
    rl = RateLimiter(max_requests=3, window_seconds=5)
    assert rl.allow("k") is True
    assert rl.allow("k") is True
    assert rl.allow("k") is True
    assert rl.allow("k") is False


def test_rate_limiter_keys_are_independent():
    rl = RateLimiter(max_requests=1, window_seconds=5)
    assert rl.allow("a") is True
    assert rl.allow("b") is True  # different key, unaffected by "a"'s usage
    assert rl.allow("a") is False


def test_rate_limiter_window_expires():
    rl = RateLimiter(max_requests=1, window_seconds=0.3)
    assert rl.allow("k") is True
    assert rl.allow("k") is False
    time.sleep(0.35)
    assert rl.allow("k") is True


def test_rate_limiter_enforce_raises_429():
    rl = RateLimiter(max_requests=1, window_seconds=5)
    rl.enforce("k")  # first call is fine
    with pytest.raises(HTTPException) as exc_info:
        rl.enforce("k")
    assert exc_info.value.status_code == 429


def test_login_lockout_after_max_failures():
    tracker = LoginAttemptTracker(max_failures=3, window_seconds=60, lockout_seconds=60)
    tracker.check_locked("a@x.com")  # no failures yet, must not raise
    for _ in range(3):
        tracker.record_failure("a@x.com")
    with pytest.raises(HTTPException) as exc_info:
        tracker.check_locked("a@x.com")
    assert exc_info.value.status_code == 429


def test_login_success_clears_lockout():
    tracker = LoginAttemptTracker(max_failures=2, window_seconds=60, lockout_seconds=60)
    tracker.record_failure("a@x.com")
    tracker.record_failure("a@x.com")
    tracker.record_success("a@x.com")
    tracker.check_locked("a@x.com")  # must not raise -- success reset it


def test_login_lockout_expires():
    tracker = LoginAttemptTracker(max_failures=1, window_seconds=60, lockout_seconds=0.3)
    tracker.record_failure("a@x.com")
    with pytest.raises(HTTPException):
        tracker.check_locked("a@x.com")
    time.sleep(0.35)
    tracker.check_locked("a@x.com")  # must not raise -- lockout window passed


def test_login_lockout_is_per_email_not_global():
    tracker = LoginAttemptTracker(max_failures=1, window_seconds=60, lockout_seconds=60)
    tracker.record_failure("a@x.com")
    with pytest.raises(HTTPException):
        tracker.check_locked("a@x.com")
    tracker.check_locked("b@x.com")  # different account, must not be locked