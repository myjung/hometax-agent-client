"""P1-3 회귀: ``.hometax.go.kr`` leading dot 보존.

Playwright cookies array 의 ``domain == ".hometax.go.kr"`` 가 ``from_cookies``
주입 후에도 그대로 살아 있어야 ``teht.hometax.go.kr`` 서브도메인에도
domain-match 가 된다.
"""

from __future__ import annotations

import json
from pathlib import Path

from hometax_client import HometaxClient


def _write_playwright_cookies(tmp_path: Path) -> Path:
    cookies = [
        {
            "name": "TXPPsessionID",
            "value": "abc",
            "domain": ".hometax.go.kr",
            "path": "/",
        },
        {
            "name": "WMONID",
            "value": "wm",
            "domain": ".hometax.go.kr",
            "path": "/",
        },
    ]
    out = tmp_path / "cookies.json"
    out.write_text(json.dumps(cookies), encoding="utf-8")
    return out


def test_from_cookies_preserves_leading_dot_domain(tmp_path: Path) -> None:
    """Playwright cookies 의 ``.hometax.go.kr`` domain 이 그대로 보존."""
    cookies_path = _write_playwright_cookies(tmp_path)
    client = HometaxClient.from_cookies(
        cookies_path, user_id="u1", tin="000000999999999999",
    )
    jar_domains = {c.domain for c in client._session.cookies.jar}
    # leading dot 유지 — http.cookiejar 의 host-only=False 신호.
    assert ".hometax.go.kr" in jar_domains
    # leading dot 가 제거된 host-only 도메인은 없어야 함.
    assert "hometax.go.kr" not in jar_domains


def test_normalize_cookie_domain_default_has_leading_dot() -> None:
    """domain 누락 시 default 도 leading dot 으로."""
    from hometax_client.client import _normalize_cookie_domain
    assert _normalize_cookie_domain(None) == ".hometax.go.kr"
    assert _normalize_cookie_domain("") == ".hometax.go.kr"


def test_normalize_cookie_domain_preserves_provided() -> None:
    """이미 제공된 domain 은 손대지 않는다."""
    from hometax_client.client import _normalize_cookie_domain
    assert _normalize_cookie_domain(".hometax.go.kr") == ".hometax.go.kr"
    # 호출자가 의도적으로 host-only 로 set 한 경우도 그대로.
    assert _normalize_cookie_domain("hometax.go.kr") == "hometax.go.kr"
