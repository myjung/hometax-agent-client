"""``HometaxClient.export_storage_state`` 회귀.

OACX/IdPw HTTP-only 세션을 Playwright ``storage_state`` 로 export 해
``bootstrap.CaptureSession`` 에 주입하기 위한 진입점.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from hometax_client import HometaxClient


def _make_client(
    cookies: list[tuple[str, str]] | None = None,
) -> HometaxClient:
    from curl_cffi import requests as cf

    sess = cf.Session(impersonate="chrome")
    cookies = cookies or [
        ("TXPPsessionID", "abc123"),
        ("WMONID", "wmonid_value"),
        ("NTS_REQUEST_SYSTEM_CODE_P", "TXPP"),
    ]
    for name, value in cookies:
        sess.cookies.set(name, value, domain=".hometax.go.kr")
    return HometaxClient(session=sess, user_id="u", tin="000000999999999999")


def test_export_storage_state_writes_playwright_format(
    tmp_path: Path,
) -> None:
    client = _make_client()
    out = tmp_path / "storage_state.json"
    client.export_storage_state(out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"cookies", "origins"}
    assert payload["origins"] == []

    names = {c["name"] for c in payload["cookies"]}
    assert "TXPPsessionID" in names
    assert "WMONID" in names
    assert "NTS_REQUEST_SYSTEM_CODE_P" in names

    for cookie in payload["cookies"]:
        # Playwright storage_state cookie 필수 필드
        assert set(cookie.keys()) >= {
            "name", "value", "domain", "path",
            "expires", "httpOnly", "secure", "sameSite",
        }
        assert cookie["domain"] == ".hometax.go.kr"
        assert cookie["path"] == "/"
        assert cookie["sameSite"] in {"Lax", "Strict", "None"}


def test_export_storage_state_skips_non_essential_cookies(
    tmp_path: Path,
) -> None:
    client = _make_client(cookies=[
        ("TXPPsessionID", "abc"),
        ("randomThirdParty", "should_not_leak"),
        ("UI_LANG", "ko"),
    ])
    out = tmp_path / "storage_state.json"
    client.export_storage_state(out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    names = {c["name"] for c in payload["cookies"]}
    assert "TXPPsessionID" in names
    assert "randomThirdParty" not in names
    assert "UI_LANG" not in names


def test_export_storage_state_file_mode_0600(tmp_path: Path) -> None:
    client = _make_client()
    out = tmp_path / "storage_state.json"
    client.export_storage_state(out)
    mode = stat.S_IMODE(os.stat(out).st_mode)
    # POSIX only — Windows 에선 chmod 가 noop 일 수 있음
    if os.name == "posix":
        assert mode == 0o600


def test_export_storage_state_creates_parent_dir(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "subdir" / "storage_state.json"
    client = _make_client()
    client.export_storage_state(out)
    assert out.exists()


def test_export_storage_state_returns_path(tmp_path: Path) -> None:
    client = _make_client()
    out = tmp_path / "storage_state.json"
    result = client.export_storage_state(out)
    assert isinstance(result, Path)
    assert result == out
