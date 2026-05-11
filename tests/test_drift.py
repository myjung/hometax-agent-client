"""응답 schema drift 회귀 — list key 자체가 사라지면 silent ``[]`` 아니라 raise.

P1-2: 홈택스 자료 0건 케이스 ("키 있고 빈 리스트") 와 응답 구조 변경
("키 자체 없음") 을 구분. 후자가 silent 빈 결과로 통과하면 세무 데이터에
서는 "자료 없음" 으로 오인되어 가장 위험한 실패 모드가 된다.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from hometax_client import HometaxClient
from hometax_client.exceptions import ResponseSchemaDriftError


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.text = self.content.decode("utf-8")
        self.status_code = 200


class _FakeSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.cookies = _FakeCookieJar()

    def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(self.payload)


class _FakeCookieJar:
    def __init__(self) -> None:
        self.jar: list[Any] = []

    def set(self, *args: Any, **kwargs: Any) -> None:
        pass


def _client_with(payload: dict[str, Any]) -> HometaxClient:
    return HometaxClient(
        session=_FakeSession(payload),
        user_id="u1",
        tin="000000999999999999",
        max_retries=0,
    )


def _ok(extra: dict[str, Any]) -> dict[str, Any]:
    """sessionMap.userId 가 있는 정상 응답 + extra 병합."""
    base = {"resultMsg": {"sessionMap": {"userId": "u1"}}}
    base.update(extra)
    return base


# ----------------------------------------------------------------- #
# inquiries.income_statements                                        #
# ----------------------------------------------------------------- #


def _income_items_key() -> str:
    from hometax_client import facts
    return facts.lookup(
        "services", "inquiries", "income_statements",
    )["items_key"]


def test_income_statements_empty_list_is_ok() -> None:
    """자료 0건 — 키 있고 빈 리스트 → 정상 빈 결과."""
    client = _client_with(_ok({_income_items_key(): []}))
    result = client.inquiries.income_statements(attr_year=2024)
    assert result == []


def test_income_statements_missing_list_raises_drift() -> None:
    """list key 자체 누락 → drift error (silent 흡수 금지)."""
    client = _client_with(_ok({}))   # items_key 자체 없음
    with pytest.raises(ResponseSchemaDriftError) as exc:
        client.inquiries.income_statements(attr_year=2024)
    assert _income_items_key() in exc.value.missing


def test_income_statements_non_list_raises_drift() -> None:
    """key 가 list 가 아님 (예: dict) → drift."""
    client = _client_with(_ok({_income_items_key(): {"unexpected": "dict"}}))
    with pytest.raises(ResponseSchemaDriftError):
        client.inquiries.income_statements(attr_year=2024)


# ----------------------------------------------------------------- #
# inquiries.tax_filings                                              #
# ----------------------------------------------------------------- #


def test_tax_filings_empty_list_is_ok() -> None:
    """tax_filings 의 items_key — facts 에서 조회."""
    from hometax_client import facts
    items_key = facts.lookup("services", "inquiries", "tax_filings")[
        "items_key"
    ]
    client = _client_with(_ok({items_key: []}))
    result = client.inquiries.tax_filings(start="20240101", end="20241231")
    assert result == []


def test_tax_filings_missing_list_raises_drift() -> None:
    client = _client_with(_ok({}))
    with pytest.raises(ResponseSchemaDriftError):
        client.inquiries.tax_filings(start="20240101", end="20241231")
