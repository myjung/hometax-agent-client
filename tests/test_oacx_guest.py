"""OACX 비회원 (``ssn`` 인자) 분기 회귀.

- ``ssn`` 파싱 / 검증
- ``_register_guest_identity()`` 의 body (popupType / userType / ssn / userName) 형식
- ``login_to_hometax()`` data 의 비회원 추가 필드 (nMemberLoginYn / txprNm / ssn1 / ssn2)
- 회원 모드 (``ssn=None``) 는 기존 form 그대로 유지 (regression guard)

라이브 호출은 안 함 — 모두 monkeypatch / dummy session 으로 검증.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from hometax_client.auth.kakao import KakaoAuth
from hometax_client.auth.oacx import OACXAuthError


class _Recorder:
    """``session.post`` / ``session.get`` 호출 인자 기록만 하는 더미."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kw: Any) -> Any:
        self.calls.append({"method": "GET", "url": url, **kw})

        class _R:
            text = ""
            content = b""

            @property
            def cookies(self):  # type: ignore[no-untyped-def]
                return type("J", (), {"jar": []})()

            def json(self) -> dict:
                return {}

        return _R()

    def post(self, url: str, **kw: Any) -> Any:
        self.calls.append({"method": "POST", "url": url, **kw})

        class _R:
            text = ""
            content = b""

            @property
            def cookies(self):  # type: ignore[no-untyped-def]
                return type("J", (), {"jar": []})()

            def json(self) -> dict:
                return {}

        return _R()

    @property
    def cookies(self):  # type: ignore[no-untyped-def]
        return type("J", (), {"jar": []})()


def _make_kakao(*, ssn: str | None) -> KakaoAuth:
    auth = KakaoAuth(
        name="홍길동",
        phone="010-1234-5678",
        birthday="19900101",
        ssn=ssn,
    )
    auth.session = _Recorder()
    return auth


def test_guest_mode_flag() -> None:
    assert _make_kakao(ssn="9001011234567").is_guest is True
    assert _make_kakao(ssn=None).is_guest is False


def test_ssn_split() -> None:
    auth = _make_kakao(ssn="900101-1234567")  # hyphen 허용
    assert auth._ssn1 == "900101"
    assert auth._ssn2 == "1234567"


def test_ssn_invalid_length() -> None:
    with pytest.raises(OACXAuthError):
        _make_kakao(ssn="12345")


def test_register_guest_identity_uses_tls_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_register_guest_identity` 가 `_post_with_tls_retry` 를 거쳐 호출.

    회원 `initiate()` 가 같은 retry 도입 (commit 8203e6f) — curl error 35
    (Chrome impersonation TLS RST) 가 첫 시도에 종종 발생. 비회원 진입
    POST 도 같은 보호 필요 (2026-05-11 라이브 검증 시 첫 시도 실패 사례).
    """
    auth = _make_kakao(ssn="9001011234567")
    calls: list[tuple[Any, ...]] = []

    class _R:
        pass

    def _fake_retry(sess: Any, url: str, **kw: Any) -> Any:
        calls.append((sess, url, kw))
        return _R()

    monkeypatch.setattr(
        "hometax_client.auth.oacx._post_with_tls_retry", _fake_retry,
    )
    auth._register_guest_identity()
    assert len(calls) == 1
    sess, url, kw = calls[0]
    assert url.endswith("/oacx/index.jsp")
    assert kw["data"]["popupType"] == "layer"


def test_register_guest_identity_body() -> None:
    """``/oacx/index.jsp`` POST body — popupType / userType / ssn / userName.

    캡처 (captures/2026-05-11T13-38-50/, entry [236]) 와 형식 일치 검증.
    """
    auth = _make_kakao(ssn="9001011234567")
    auth._register_guest_identity()
    recorder: _Recorder = auth.session  # type: ignore[assignment]
    [call] = recorder.calls
    assert call["method"] == "POST"
    assert call["url"].endswith("/oacx/index.jsp")
    body = call["data"]
    assert body["popupType"] == "layer"
    assert body["userType"] == "R"
    # ssn = base64(13자리 평문 RRN)
    assert base64.b64decode(body["ssn"]).decode() == "9001011234567"
    # userName = base64(UTF-8 이름)
    assert base64.b64decode(body["userName"]).decode("utf-8") == "홍길동"


def test_initiate_guest_calls_register(monkeypatch: pytest.MonkeyPatch) -> None:
    """``initiate()`` 가 비회원 모드에서 ``_register_guest_identity`` 를 호출하고
    회원 모드에서는 호출하지 않음을 확인."""
    auth = _make_kakao(ssn="9001011234567")
    called: list[bool] = []
    monkeypatch.setattr(
        auth, "_register_guest_identity", lambda: called.append(True),
    )

    # _post_with_tls_retry 가 trans 호출 — 더미 응답으로 short-circuit
    class _R:
        text = ""

        def json(self) -> dict:
            return {
                "oacxCode": "OACX_SUCCESS",
                "txId": "dummy-tx",
                "token": "dummy-token",
            }
    monkeypatch.setattr(
        "hometax_client.auth.oacx._post_with_tls_retry",
        lambda *a, **kw: _R(),
    )
    auth.initiate()
    assert called == [True]

    # 회원 모드
    member = _make_kakao(ssn=None)
    called2: list[bool] = []
    monkeypatch.setattr(
        member, "_register_guest_identity",
        lambda: called2.append(True),
    )
    member.initiate()
    assert called2 == []


def test_login_to_hometax_guest_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """``login_to_hometax`` data dict — 비회원 4개 필드 추가."""
    auth = _make_kakao(ssn="9001011234567")
    auth._cert_token = "CERT_TOKEN_X"

    monkeypatch.setattr(auth, "_prime_hometax_login_context", lambda: None)

    auth.login_to_hometax()
    recorder: _Recorder = auth.session  # type: ignore[assignment]
    pubc = [c for c in recorder.calls if "pubcLogin" in c["url"]]
    assert len(pubc) == 1
    data = pubc[0]["data"]
    # 비회원 필드
    assert data["nMemberLoginYn"] == "Y"
    assert data["txprNm"] == "홍길동"  # raw, base64 X (JS 와 일치)
    assert base64.b64decode(data["ssn1"]).decode() == "900101"
    assert base64.b64decode(data["ssn2"]).decode() == "1234567"
    # 회원과 공통 필드 유지
    assert data["moisCertYn"] == "Y"
    assert data["newGpinYn"] == "Y"
    assert data["reqTxId"] == "CERT_TOKEN_X"
    assert data["scrnId"] == "UTXPPABA01"


def test_login_to_hometax_member_data_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """회원 모드 (``ssn=None``) 에서 form 이 그대로 — 비회원 필드 부재."""
    auth = _make_kakao(ssn=None)
    auth._cert_token = "CERT_TOKEN_X"
    monkeypatch.setattr(auth, "_prime_hometax_login_context", lambda: None)

    auth.login_to_hometax()
    recorder: _Recorder = auth.session  # type: ignore[assignment]
    pubc = [c for c in recorder.calls if "pubcLogin" in c["url"]]
    data = pubc[0]["data"]
    assert "nMemberLoginYn" not in data
    assert "txprNm" not in data
    assert "ssn1" not in data
    assert "ssn2" not in data
    assert data["scrnId"] == "UTXPPABA01"
    assert data["reqTxId"] == "CERT_TOKEN_X"
