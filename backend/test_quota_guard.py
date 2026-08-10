import time

import pytest

import quota_guard


@pytest.fixture(autouse=True)
def _reset_minute_window():
    quota_guard._minute_window.clear()
    yield
    quota_guard._minute_window.clear()


def test_daily_cap_blocks_once_reached(monkeypatch):
    monkeypatch.setattr(quota_guard, "_count_gemini_requests_today", lambda: 15)
    with pytest.raises(quota_guard.QuotaExceeded, match="daily"):
        quota_guard.check_gemini_quota(max_per_day=15, max_per_minute=100)


def test_daily_cap_allows_below_limit(monkeypatch):
    monkeypatch.setattr(quota_guard, "_count_gemini_requests_today", lambda: 14)
    quota_guard.check_gemini_quota(max_per_day=15, max_per_minute=100)  # should not raise


def test_per_minute_cap_blocks_once_reached(monkeypatch):
    monkeypatch.setattr(quota_guard, "_count_gemini_requests_today", lambda: 0)
    for _ in range(4):
        quota_guard.record_gemini_request()
    with pytest.raises(quota_guard.QuotaExceeded, match="per-minute"):
        quota_guard.check_gemini_quota(max_per_day=100, max_per_minute=4)


def test_per_minute_window_expires_old_entries(monkeypatch):
    monkeypatch.setattr(quota_guard, "_count_gemini_requests_today", lambda: 0)
    # simulate 4 requests that happened over a minute ago
    now = time.time()
    quota_guard._minute_window.extend([now - 90, now - 80, now - 70, now - 61])
    quota_guard.check_gemini_quota(max_per_day=100, max_per_minute=4)  # should not raise — all expired


def test_record_does_not_raise_and_books_usage(monkeypatch):
    monkeypatch.setattr(quota_guard, "_count_gemini_requests_today", lambda: 0)
    assert len(quota_guard._minute_window) == 0
    quota_guard.record_gemini_request()
    assert len(quota_guard._minute_window) == 1
