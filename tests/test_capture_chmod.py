"""P1-4 회귀: bootstrap 산출물이 ``0o600`` 으로 저장된다.

cookies / storage_state / meta / HAR 에 RRN·세션 토큰이 들어갈 수 있으므로
``save_session`` 과 같은 권한 정책을 적용. Playwright 의존을 피하기 위해
helper (``_chmod_0o600``) 와 dump 의 fake context 흐름만 단위 테스트.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from hometax_client.bootstrap.capture import CaptureSession, _chmod_0o600


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.mark.skipif(os.name != "posix", reason="POSIX chmod only")
def test_chmod_helper_sets_0o600(tmp_path: Path) -> None:
    p = tmp_path / "secret.json"
    p.write_text("{}", encoding="utf-8")
    _chmod_0o600(p)
    assert _mode(p) == 0o600


def test_chmod_helper_silent_on_missing(tmp_path: Path) -> None:
    """없는 경로 / 권한 없는 fs 등은 noop (테스트만 무사 통과)."""
    _chmod_0o600(tmp_path / "nope")   # 예외 raise 하지 않아야


class _FakeContext:
    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._cookies = [
            {"name": "TXPPsessionID", "value": "abc",
             "domain": ".hometax.go.kr", "path": "/"},
        ]

    def cookies(self) -> list[dict]:
        return self._cookies

    def storage_state(self, path: str) -> None:
        Path(path).write_text(
            json.dumps({"cookies": self._cookies, "origins": []}),
            encoding="utf-8",
        )


class _FakePage:
    url = "https://hometax.go.kr/"


@pytest.mark.skipif(os.name != "posix", reason="POSIX chmod only")
def test_dump_applies_0o600(tmp_path: Path) -> None:
    """``dump()`` 가 cookies / storage_state / meta 세 파일 모두 0o600 으로."""
    cap = CaptureSession(output_dir=tmp_path, record_har=False)
    # Playwright 띄우지 않고 fake 로 dump 만 호출.
    cap._context = _FakeContext(tmp_path)   # type: ignore[assignment]
    cap._page = _FakePage()                  # type: ignore[assignment]
    cap._started_at = "2026-05-11T12:00:00"

    paths = cap.dump()
    cap._closed = True   # close() 시 Playwright 안 깨지게 (안 호출되도록 차단)

    for key in ("cookies", "storage_state", "meta"):
        assert _mode(paths[key]) == 0o600, f"{key} mode != 0o600"
