"""OACX `_post_with_tls_retry` 회귀.

curl_cffi 의 Chrome impersonation TLS handshake 가 일시 RST 되는 케이스
대응. 첫 시도 SSLError → 1회 재시도 → 둘째 시도 성공 시나리오 검증.
"""

from __future__ import annotations

from typing import Any

import pytest
from curl_cffi.requests.exceptions import (
    ConnectionError as CCEConnectionError,
    SSLError,
)

from hometax_client.auth.oacx import _post_with_tls_retry


class _FlakySession:
    """첫 N 번 호출은 raise, 그 다음은 fake response 반환."""

    def __init__(
        self,
        *,
        fail_times: int,
        exc_cls: type[Exception] = SSLError,
    ) -> None:
        self.fail_times = fail_times
        self.exc_cls = exc_cls
        self.calls = 0

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc_cls(
                "Failed to perform, curl: (35) Recv failure: "
                "Connection reset by peer", 35, None,
            )

        class _R:
            text = '{"ok": true}'
            content = b'{"ok": true}'
            def json(self) -> dict:
                return {"ok": True}
        return _R()


def test_retry_recovers_on_first_failure() -> None:
    """1회 SSLError → 1회 retry → 성공."""
    sess = _FlakySession(fail_times=1)
    resp = _post_with_tls_retry(sess, "https://x/", delay=0.0)
    assert resp.json() == {"ok": True}
    assert sess.calls == 2


def test_retry_recovers_on_connection_error() -> None:
    """SSLError 외 ConnectionError 도 같은 catch."""
    sess = _FlakySession(fail_times=1, exc_cls=CCEConnectionError)
    resp = _post_with_tls_retry(sess, "https://x/", delay=0.0)
    assert resp.json() == {"ok": True}
    assert sess.calls == 2


def test_retry_gives_up_after_max_retries() -> None:
    """retries=1 (default) 면 첫 + 1회 = 2회 시도. 그 후에도 fail 이면 raise."""
    sess = _FlakySession(fail_times=2)
    with pytest.raises(SSLError):
        _post_with_tls_retry(sess, "https://x/", delay=0.0)
    assert sess.calls == 2


def test_no_retry_on_success() -> None:
    """첫 시도 성공이면 retry 안 함."""
    sess = _FlakySession(fail_times=0)
    resp = _post_with_tls_retry(sess, "https://x/", delay=0.0)
    assert resp.json() == {"ok": True}
    assert sess.calls == 1


def test_custom_retries_count() -> None:
    """retries=3 이면 최대 4회 시도."""
    sess = _FlakySession(fail_times=2)
    resp = _post_with_tls_retry(sess, "https://x/", retries=3, delay=0.0)
    assert resp.json() == {"ok": True}
    assert sess.calls == 3
