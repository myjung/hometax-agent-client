"""dataclass 변환기 테스트.

홈택스가 새 필드를 추가해도 ``raw`` 가 보존되고 핵심 필드는 ``None`` 으로
graceful 하게 떨어지는지 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from hometax_client import IncomeStatement, SessionInfo, TaxFiling

FIXTURES = Path(__file__).parent / "fixtures" / "2026-05-10"


def test_session_info_extracts_known_fields() -> None:
    info = SessionInfo.from_session_map({
        "userId": "rey123",
        "userNm": "홍길동",
        "tin": "1234567890",
        "lgnUserClCd": "01",
        "userCertClCd": "01",
        "newFieldFromHomeTax2027": "value",
    })
    assert info.user_id == "rey123"
    assert info.user_name == "홍길동"
    assert info.tin == "1234567890"
    assert info.user_class_cd == "01"
    # raw 보존 — 라이브러리가 모르는 새 필드도 호출자가 꺼낼 수 있다.
    assert info.raw["newFieldFromHomeTax2027"] == "value"


def test_session_info_handles_missing_fields() -> None:
    info = SessionInfo.from_session_map({})
    assert info.user_id is None
    assert info.tin is None
    assert info.raw == {}


def test_income_statement_from_dict() -> None:
    statement = IncomeStatement.from_dict({
        "attrYr": "2024",
        "mateKndNm": "근로소득지급명세서",
        "sbmtNm": "주식회사 홍길동",
        "sbmtNo": "1234567890",
        "txnrmStrtYm": "202401",
        "txnrmEndYm": "202412",
    })
    assert statement.attr_year == "2024"
    assert statement.material_kind_name == "근로소득지급명세서"
    assert statement.payer_name == "주식회사 홍길동"
    assert statement.period_start == "202401"


def test_tax_filing_from_dict() -> None:
    filing = TaxFiling.from_dict({
        "txnrmYm": "202412",
        "rtnClNm": "정기(확정)",
        "stmnKndNm": "종합소득세 정기확정신고서",
        "stasAmt": 500_000,
        "itrfCd": "10",
    })
    assert filing.period_ym == "202412"
    assert filing.return_kind_name == "정기(확정)"
    assert filing.computed_tax == 500_000
    assert filing.interface_cd == "10"
    # final_tax 가 응답에 없으면 None
    assert filing.final_tax is None


def test_session_info_from_real_captured_response() -> None:
    """실제 ATXPPAAA001R037 응답 (마스킹된 fixture) 으로 회귀.

    sessionMap 필드 이름이 살아있고 SessionInfo 가 핵심 값을 추출하는지.
    출처: ``docs/hometax-facts.md §15`` (2026-05-10).
    """
    data = json.loads(
        (FIXTURES / "session_info_idpw.json").read_text(encoding="utf-8"),
    )
    sm = data["resultMsg"]["sessionMap"]
    info = SessionInfo.from_session_map(sm)
    assert info.user_id == "testuser"
    assert info.user_name == "홍길동"
    assert info.tin == "000000999999999999"
    assert info.user_class_cd == "01"  # lgnUserClCd
    # raw 보존 — 와이어 키 그대로 호출자에 노출.
    assert info.raw["pubcUserNo"] == "100000000099999999"
    assert info.raw["txofOgzCd"] == "232"
    assert info.raw["userCertClCd"] == "11"


def test_session_info_is_guest_member() -> None:
    """회원 sessionMap (lgnUserClCd='01') 은 is_guest=False."""
    info = SessionInfo.from_session_map({"lgnUserClCd": "01"})
    assert info.is_guest is False


def test_session_info_is_guest_true() -> None:
    """비회원 sessionMap (lgnUserClCd='02') 은 is_guest=True.

    검증일 2026-05-11: ``captures/2026-05-11T13-38-50/`` 의 비회원 세션
    sessionMap. 회원/비회원 분기는 docs/hometax-facts.md §16.
    """
    info = SessionInfo.from_session_map({"lgnUserClCd": "02"})
    assert info.is_guest is True


def test_session_info_is_guest_none_defaults_to_false() -> None:
    """필드 누락 시 보수적 default — 회원 가정."""
    info = SessionInfo.from_session_map({})
    assert info.is_guest is False


def test_dataclasses_are_frozen() -> None:
    """공개 dataclass 들은 frozen — 호출자 변경으로 인한 사이드이펙트 방지."""
    import dataclasses

    for cls in (SessionInfo, IncomeStatement, TaxFiling):
        params = dataclasses.fields(cls)
        assert params  # 필드가 있어야 함
        assert getattr(cls, "__dataclass_params__").frozen, cls
