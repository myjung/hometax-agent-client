"""라이브 NTS_KEYS drift 회귀 — ``HOMETAX_LIVE=1`` 게이트.

CI / 오프라인에서는 자동 skip. 개발자 머신 또는 cron 으로 ``HOMETAX_LIVE=1
pytest tests/test_keys_live.py`` 를 돌리면 홈택스가 키를 회전한 순간 즉시
검출. 회전 시::

    python -m hometax_client.health --refresh

로 cache 갱신 후 재실행.
"""

from __future__ import annotations

import os

import pytest

from hometax_client.crypto import active_keys, fetch_live_keys

pytestmark = pytest.mark.skipif(
    os.environ.get("HOMETAX_LIVE") != "1",
    reason="라이브 네트워크 테스트 — HOMETAX_LIVE=1 일 때만 실행",
)


def test_live_keys_match_active() -> None:
    """라이브 JS 의 키가 active_keys() 와 일치 (drift 0)."""
    live = fetch_live_keys()
    active = active_keys()
    assert live == active, (
        f"NTS_KEYS drift! live ≠ active.\n"
        f"  active: {active}\n"
        f"  live:   {live}\n"
        "→ python -m hometax_client.health --refresh"
    )


def test_live_keys_count_seven() -> None:
    """라이브 JS 의 keys 가 항상 7개 (구조 sanity)."""
    keys = fetch_live_keys()
    assert len(keys) == 7
