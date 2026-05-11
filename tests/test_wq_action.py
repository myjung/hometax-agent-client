"""``HometaxClient.wq_action`` 응답 분류 회귀 테스트.

홈택스 응답이 ``resultMsg.result == "F"`` 인데 ``sessionMap`` 이 동반되는
실패 모드를 silent 하게 통과시키지 않는다 (P1-1).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from hometax_client import HometaxClient
from hometax_client.exceptions import WqActionFailedError


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        self.content = text.encode("utf-8")
        self.text = text
        self.status_code = 200


class _FakeSession:
    """``wq_action`` 의 응답 분류만 검증하기 위한 최소 fake."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.cookies = _FakeCookieJar()
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return _FakeResponse(self.payload)


class _FakeCookieJar:
    def __init__(self) -> None:
        self.jar: list[Any] = []

    def set(self, *args: Any, **kwargs: Any) -> None:
        pass


def _client(payload: dict[str, Any]) -> HometaxClient:
    return HometaxClient(
        session=_FakeSession(payload),
        user_id="u1",
        tin="000000999999999999",
        max_retries=0,
    )


# ----------------------------------------------------------------- #
# P1-1 핵심: result=="F" 는 sessionMap 동반과 무관하게 raise        #
# ----------------------------------------------------------------- #


def test_result_F_with_sessionMap_still_raises() -> None:
    """인증된 세션의 validation 실패 — sessionMap 가 있어도 raise."""
    client = _client({
        "resultMsg": {
            "result": "F",
            "msg": "필수입력 항목이 누락되었습니다",
            "sessionMap": {"userId": "u1", "txprDscmNo": "000000999999999999"},
        }
    })
    with pytest.raises(WqActionFailedError):
        client.wq_action(action_id="A1", screen_id="S1", body={})


def test_result_F_without_sessionMap_raises() -> None:
    client = _client({
        "resultMsg": {"result": "F", "msg": "세션이 만료되었습니다"}
    })
    with pytest.raises(WqActionFailedError):
        client.wq_action(action_id="A1", screen_id="S1", body={})


def test_login_msg_without_userId_raises() -> None:
    """result 가 비어도 '로그인' 메시지 + userId 없으면 raise."""
    client = _client({
        "resultMsg": {"msg": "로그인이 되어있지 않습니다"}
    })
    with pytest.raises(WqActionFailedError):
        client.wq_action(action_id="A1", screen_id="S1", body={})


def test_success_passthrough() -> None:
    """정상 응답은 그대로 dict 반환."""
    payload = {
        "resultMsg": {"sessionMap": {"userId": "u1"}},
        "agitxRtnInqrDVOList": [{"a": 1}],
    }
    client = _client(payload)
    data = client.wq_action(action_id="A1", screen_id="S1", body={})
    assert data == payload
