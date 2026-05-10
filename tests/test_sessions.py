"""SessionStore — 다중 세션 관리 회귀."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from hometax_client import HometaxClient, SessionEntry, SessionHealth, SessionStore


# ----------------------------------------------------------------- #
# 헬퍼                                                               #
# ----------------------------------------------------------------- #


def _make_client(
    *,
    user_id: str = "testuser",
    tin: str = "000000999999999999",
    extra_cookies: list[tuple[str, str]] | None = None,
) -> HometaxClient:
    """``ESSENTIAL_COOKIES`` 한두 개 set 한 ``HometaxClient`` 생성."""
    from curl_cffi import requests as cf

    sess = cf.Session(impersonate="chrome")
    cookies = [("TXPPsessionID", "abc123"), ("WMONID", "wmonid_value")]
    cookies.extend(extra_cookies or [])
    for name, value in cookies:
        sess.cookies.set(name, value, domain=".hometax.go.kr")
    return HometaxClient(session=sess, user_id=user_id, tin=tin)


# ----------------------------------------------------------------- #
# Discovery                                                          #
# ----------------------------------------------------------------- #


def test_empty_store_lists_nothing(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    assert store.list() == []
    assert len(store) == 0
    assert list(store) == []


def test_save_writes_file_with_metadata(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    client = _make_client(user_id="kim123", tin="111222333")
    path = store.save(
        client, client_id="kim", label="김철수", auth_method="idpw",
    )
    assert path.exists()
    assert path.name == "kim.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["client_id"] == "kim"
    assert data["label"] == "김철수"
    assert data["auth_method"] == "idpw"
    assert data["user_id"] == "kim123"
    assert data["tin"] == "111222333"
    assert data["last_used_at"] >= data["saved_at"]
    assert any(c["name"] == "TXPPsessionID" for c in data["cookies"])


def test_get_returns_entry_after_save(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    client = _make_client(user_id="kim123")
    store.save(client, client_id="kim", label="김철수")
    entry = store.get("kim")
    assert entry is not None
    assert entry.client_id == "kim"
    assert entry.label == "김철수"
    assert entry.user_id == "kim123"
    assert entry.path.name == "kim.json"


def test_get_returns_none_for_missing(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    assert store.get("ghost") is None


def test_list_skips_invalid_files(tmp_path: Path) -> None:
    """깨진 JSON / non-dict / .tmp prefix 파일은 list 에서 제외."""
    d = tmp_path / "sessions"
    d.mkdir()
    (d / "good.json").write_text(
        json.dumps({"client_id": "good", "saved_at": 1, "cookies": []}),
        encoding="utf-8",
    )
    (d / "broken.json").write_text("not a json", encoding="utf-8")
    (d / "list_only.json").write_text(json.dumps([1, 2, 3]))
    (d / ".tmp.abc.json").write_text("{}")
    store = SessionStore(d)
    ids = [e.client_id for e in store.list()]
    assert ids == ["good"]


def test_find_by_tin_and_user_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.save(
        _make_client(user_id="kim", tin="111"),
        client_id="kim", label="김",
    )
    store.save(
        _make_client(user_id="lee", tin="222"),
        client_id="lee", label="이",
    )
    by_tin = store.find_by_tin("222")
    assert by_tin is not None and by_tin.client_id == "lee"
    by_user = store.find_by_user_id("kim")
    assert by_user is not None and by_user.client_id == "kim"
    assert store.find_by_tin("000") is None
    assert store.find_by_user_id("unknown") is None


def test_dunder_membership_and_iteration(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.save(_make_client(), client_id="kim")
    store.save(_make_client(), client_id="lee")
    assert "kim" in store
    assert "ghost" not in store
    assert 123 not in store  # type: ignore[operator]
    assert "bad id!" not in store  # invalid format → False, not raise
    assert len(store) == 2
    ids = sorted(e.client_id for e in store)
    assert ids == ["kim", "lee"]


# ----------------------------------------------------------------- #
# Read / open                                                        #
# ----------------------------------------------------------------- #


def test_open_returns_working_client_and_bumps_last_used(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "sessions")
    client = _make_client(user_id="kim", tin="111")
    store.save(client, client_id="kim")
    saved_at = store.get("kim").saved_at  # type: ignore[union-attr]

    # 1초 보장 — last_used_at 차이 만들기 위함
    time.sleep(1.1)
    reopened = store.open("kim")
    assert isinstance(reopened, HometaxClient)
    assert reopened.user_id == "kim"
    assert reopened.tin == "111"

    entry_after = store.get("kim")
    assert entry_after is not None
    assert entry_after.saved_at == saved_at
    assert entry_after.last_used_at is not None
    assert entry_after.last_used_at > saved_at


def test_open_missing_raises_keyerror(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    with pytest.raises(KeyError):
        store.open("ghost")


# ----------------------------------------------------------------- #
# Write / touch / remove                                             #
# ----------------------------------------------------------------- #


def test_save_validates_client_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    client = _make_client()
    for bad in ("", "with space", "한글", "x" * 65, "dot.in.id"):
        with pytest.raises(ValueError):
            store.save(client, client_id=bad)


def test_touch_updates_last_used_at_only(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.save(_make_client(), client_id="kim")
    before = store.get("kim")
    assert before is not None
    time.sleep(1.1)
    store.touch("kim")
    after = store.get("kim")
    assert after is not None
    assert after.saved_at == before.saved_at
    assert (
        after.last_used_at is not None
        and before.last_used_at is not None
        and after.last_used_at > before.last_used_at
    )


def test_touch_missing_raises_keyerror(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    with pytest.raises(KeyError):
        store.touch("ghost")


def test_remove_returns_bool(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.save(_make_client(), client_id="kim")
    assert store.remove("kim") is True
    assert store.remove("kim") is False
    assert store.get("kim") is None


# ----------------------------------------------------------------- #
# Health                                                             #
# ----------------------------------------------------------------- #


def test_health_missing(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    h = store.health("ghost")
    assert h.client_id == "ghost"
    assert h.fresh is False
    assert h.reason == "missing"


def test_health_recent_within_threshold(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions", fresh_within_sec=1800)
    store.save(_make_client(), client_id="kim")
    h = store.health("kim")
    assert h.fresh is True
    assert h.reason == "recent"


def test_health_stale_beyond_threshold(tmp_path: Path) -> None:
    """saved_at 을 과거로 조작해 stale 판정 검증."""
    store = SessionStore(tmp_path / "sessions", fresh_within_sec=60)
    store.save(_make_client(), client_id="kim")
    # 직접 파일을 손봐 last_used_at/saved_at 을 오래 전으로
    path = store.get("kim").path  # type: ignore[union-attr]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["saved_at"] = int(time.time()) - 3600
    data["last_used_at"] = int(time.time()) - 3600
    path.write_text(json.dumps(data), encoding="utf-8")

    h = store.health("kim")
    assert h.fresh is False
    assert h.reason == "stale"


def test_health_live_verified(monkeypatch, tmp_path: Path) -> None:
    """live=True: session_info 가 정상 반환 → fresh=True / reason='verified'."""
    from hometax_client import SessionInfo

    store = SessionStore(tmp_path / "sessions")
    store.save(_make_client(user_id="kim", tin="111"), client_id="kim")

    def fake_info(self):  # noqa: ANN001
        return SessionInfo.from_session_map({
            "userId": "kim", "userNm": "홍길동", "tin": "111",
            "lgnUserClCd": "01", "userCertClCd": "11",
        })

    monkeypatch.setattr(HometaxClient, "session_info", fake_info)
    h = store.health("kim", live=True)
    assert h.fresh is True
    assert h.reason == "verified"


def test_health_live_session_expired(monkeypatch, tmp_path: Path) -> None:
    """live=True: SessionExpiredError → fresh=False / reason='session_expired'."""
    from hometax_client import SessionExpiredError

    store = SessionStore(tmp_path / "sessions")
    store.save(_make_client(), client_id="kim")

    def raise_expired(self):  # noqa: ANN001
        raise SessionExpiredError("세션 만료")

    monkeypatch.setattr(HometaxClient, "session_info", raise_expired)
    h = store.health("kim", live=True)
    assert h.fresh is False
    assert h.reason == "session_expired"


def test_health_live_other_hometax_error(monkeypatch, tmp_path: Path) -> None:
    """다른 HometaxError → reason='error:<ExcClass>'."""
    from hometax_client import AuthGradeInsufficientError

    store = SessionStore(tmp_path / "sessions")
    store.save(_make_client(), client_id="kim")

    def raise_grade(self):  # noqa: ANN001
        raise AuthGradeInsufficientError("등급 부족")

    monkeypatch.setattr(HometaxClient, "session_info", raise_grade)
    h = store.health("kim", live=True)
    assert h.fresh is False
    assert h.reason == "error:AuthGradeInsufficientError"


def test_health_all_aggregate(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions", fresh_within_sec=1800)
    store.save(_make_client(), client_id="kim")
    store.save(_make_client(), client_id="lee")
    reports = store.health_all()
    assert {r.client_id for r in reports} == {"kim", "lee"}
    assert all(r.fresh for r in reports)


# ----------------------------------------------------------------- #
# 보존 / drift tolerance                                             #
# ----------------------------------------------------------------- #


def test_unknown_fields_preserved_in_raw(tmp_path: Path) -> None:
    """홈택스 / 워크플로가 추가한 미지의 필드도 SessionEntry.raw 에 보존."""
    d = tmp_path / "sessions"
    d.mkdir()
    (d / "kim.json").write_text(
        json.dumps({
            "client_id": "kim",
            "saved_at": 100,
            "cookies": [],
            "user_id": "kim",
            "homeTax2027NewMeta": "value",
        }),
        encoding="utf-8",
    )
    store = SessionStore(d)
    entry = store.get("kim")
    assert entry is not None
    assert entry.raw["homeTax2027NewMeta"] == "value"


def test_save_session_uses_atomic_write(tmp_path: Path) -> None:
    """HometaxClient.save_session 도 atomic write 통과 (회귀 안전망)."""
    client = _make_client()
    out = tmp_path / "sub" / "sub2" / "sess.json"
    client.save_session(out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["user_id"] == "testuser"
    # 임시 파일 잔재가 없어야 함
    leftovers = list(out.parent.glob(".tmp.*"))
    assert leftovers == []
