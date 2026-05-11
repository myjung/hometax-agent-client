"""예외 계층과 ``classify_failure`` 분류 테스트."""

from __future__ import annotations

import pytest

from hometax_client.exceptions import (
    AuthGradeInsufficientError,
    BlockedError,
    HometaxError,
    LoginRequiredError,
    PermissionDeniedError,
    ResponseSchemaDriftError,
    SessionExpiredError,
    UnknownResponseError,
    ValidationError,
    WqActionFailedError,
    classify_failure,
)


def test_all_errors_inherit_hometax_error() -> None:
    """공개 예외 모두 HometaxError 를 상속해야 한다."""
    public = [
        WqActionFailedError,
        SessionExpiredError,
        ValidationError,
        LoginRequiredError,
        AuthGradeInsufficientError,
        PermissionDeniedError,
        BlockedError,
        UnknownResponseError,
        ResponseSchemaDriftError,
    ]
    for cls in public:
        assert issubclass(cls, HometaxError), cls


def test_classify_login_required_for_fwe() -> None:
    rm = {
        "result": "F",
        "msg": "[FWE] 로그인이 되어있지 않습니다.",
        "code": "ABC",
    }
    exc = classify_failure(rm, action_id="AT001")
    assert isinstance(exc, LoginRequiredError)
    assert exc.action_id == "AT001"
    assert "FWE" in (exc.raw_msg or "")


def test_classify_validation_for_required_field_missing() -> None:
    rm = {
        "result": "F",
        "msg": "귀속연도[attrYr]은(는) 필수입력 항목입니다.",
    }
    exc = classify_failure(rm)
    assert isinstance(exc, ValidationError)


def test_classify_session_expired_default() -> None:
    rm = {
        "result": "F",
        "msg": "세션정보가 존재하지 않습니다. 다시 로그인 해주세요.",
    }
    exc = classify_failure(rm)
    assert isinstance(exc, SessionExpiredError)


def test_classify_auth_grade_insufficient_for_cert_required() -> None:
    """ID/PW 등급으로 공인인증서 등급 액션 호출 시 받는 메시지.

    검증일 2026-05-10: ID/PW 세션으로 ``client.inquiries.income_statements``
    호출 시 ``01$공인인증서로 로그인 하시기 바랍니다.`` 응답.
    """
    rm = {
        "result": "F",
        "msg": "01$공인인증서로 로그인 하시기 바랍니다.",
    }
    exc = classify_failure(rm, action_id="ATXPPBAA001R16")
    assert isinstance(exc, AuthGradeInsufficientError)
    assert not isinstance(exc, SessionExpiredError)
    assert exc.action_id == "ATXPPBAA001R16"
    assert "공인인증서" in (exc.raw_msg or "")


def test_classify_auth_grade_for_short_cert_phrase() -> None:
    """공식 명칭 변경(공인인증서 → 인증서) 대응 — 짧은 표현도 분류."""
    rm = {"result": "F", "msg": "보안 강화를 위해 인증서로 로그인 해주세요."}
    exc = classify_failure(rm)
    assert isinstance(exc, AuthGradeInsufficientError)


def test_classify_permission_denied_by_code_only() -> None:
    """``code='pubcPermission'`` 만 와도 분류. msg 빈 케이스 대응.

    검증일 2026-05-11: 비회원 세션으로 TEWE 화면 (``UWEICZAA92`` 본 소득내역
    보고서) 호출 시 ``msg`` 가 빈 채 ``code=pubcPermission`` 만 옴. 종전엔
    msg 키워드 매칭 안 되어 ``SessionExpiredError`` default 로 떨어졌다.
    """
    rm = {"result": "F", "code": "pubcPermission"}
    exc = classify_failure(rm, action_id="AWEICAAA034R01")
    assert isinstance(exc, PermissionDeniedError)
    assert not isinstance(exc, SessionExpiredError)
    assert exc.action_id == "AWEICAAA034R01"


def test_classify_permission_denied_for_unauthorized_screen() -> None:
    """비회원 세션이 회원 전용 메뉴 호출 시 받는 메시지.

    검증일 2026-05-11: 비회원 세션으로 ``client.inquiries.income_statements``
    호출 시 ``0000005,|+|0000001,$권한이 없는 화면입니다.`` 응답. 종전엔
    ``SessionExpiredError`` 로 분류되어 "재인증 하세요" 안내가 부정확
    (재인증해도 같은 결과 — 회원 인증 종류 자체가 필요).
    """
    rm = {
        "result": "F",
        "msg": "0000005,|+|0000001,$권한이 없는 화면입니다.",
    }
    exc = classify_failure(rm, action_id="ATXPPBAA001R16")
    assert isinstance(exc, PermissionDeniedError)
    # SessionExpiredError 가 default 였던 회귀를 막는다.
    assert not isinstance(exc, SessionExpiredError)
    assert exc.action_id == "ATXPPBAA001R16"
    assert "권한이 없는" in (exc.raw_msg or "")


def test_classify_permission_denied_short_phrase() -> None:
    """다른 표기 (메뉴) 도 같은 분류."""
    rm = {"result": "F", "msg": "권한이 없는 메뉴입니다."}
    exc = classify_failure(rm)
    assert isinstance(exc, PermissionDeniedError)


def test_classify_with_nested_error_msg_dict() -> None:
    rm = {
        "result": "F",
        "errorMsg": {"code": "EIE2999", "msg": "차단 표시"},
    }
    exc = classify_failure(rm)
    # SessionExpiredError 로 떨어지더라도 메시지가 보존되어야 한다.
    assert isinstance(exc, WqActionFailedError)
    assert "차단" in (exc.raw_msg or "") or "EIE2999" in (exc.raw_msg or "")


def test_blocked_error_holds_code() -> None:
    exc = BlockedError("EIE2999", "차단됨")
    assert exc.code == "EIE2999"
    assert "EIE2999" in str(exc)


def test_response_schema_drift_holds_raw() -> None:
    raw = {"resultMsg": {"result": "S"}, "newField": True}
    exc = ResponseSchemaDriftError(
        action_id="AT001",
        missing=["expectedField"],
        raw=raw,
    )
    assert exc.action_id == "AT001"
    assert exc.missing == ["expectedField"]
    assert exc.raw is raw


def test_classify_does_not_raise_on_empty_rm() -> None:
    """비어있는 resultMsg 도 안전하게 분류되어야 한다."""
    exc = classify_failure({})
    assert isinstance(exc, WqActionFailedError)


def test_pytest_can_use_isinstance_chain() -> None:
    rm = {"result": "F", "msg": "필수입력 누락"}
    with pytest.raises(HometaxError):
        raise classify_failure(rm)
