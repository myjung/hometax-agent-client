"""IdPwAuth 의 인코딩 헬퍼 단위 테스트.

직접 네트워크 호출은 하지 않고, 캡처에서 확인된 인코딩 규칙만 검증한다.
"""

from __future__ import annotations

import base64

import pytest

from hometax_client.auth.idpw import IdPwAuth, IdPwAuthError


def test_encode_id_r07_inserts_commas_then_base64() -> None:
    encoded = IdPwAuth._encode_id_r07("hello")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "h,e,l,l,o,"


def test_encode_id_r07_handles_korean_id() -> None:
    encoded = IdPwAuth._encode_id_r07("한글")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "한,글,"


def test_extract_r07_login_values_top_level() -> None:
    pair = IdPwAuth._extract_r07_login_values({
        "id": "encoded_id",
        "pswd": "encoded_pw",
    })
    assert pair == ("encoded_id", "encoded_pw")


def test_extract_r07_login_values_nested_response_shape() -> None:
    pair = IdPwAuth._extract_r07_login_values({
        "response": {"id": "X", "pswd": "Y"},
    })
    assert pair == ("X", "Y")


def test_extract_r07_login_values_returns_none_for_missing() -> None:
    assert IdPwAuth._extract_r07_login_values({}) is None


def test_encode_sq2_txpr_dscm_no_accepts_seven_digits() -> None:
    encoded = IdPwAuth._encode_sq2_txpr_dscm_no("9001011")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "9001011"


def test_encode_sq2_txpr_dscm_no_truncates_thirteen_digits() -> None:
    encoded = IdPwAuth._encode_sq2_txpr_dscm_no("9001011234567")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "9001011"


def test_encode_sq2_txpr_dscm_no_strips_separators() -> None:
    encoded = IdPwAuth._encode_sq2_txpr_dscm_no("900101-1")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "9001011"


def test_encode_sq2_txpr_dscm_no_rejects_short_input() -> None:
    with pytest.raises(IdPwAuthError):
        IdPwAuth._encode_sq2_txpr_dscm_no("12345")


def test_encode_sq2_txpr_dscm_no_returns_none_for_empty() -> None:
    assert IdPwAuth._encode_sq2_txpr_dscm_no(None) is None
    assert IdPwAuth._encode_sq2_txpr_dscm_no("") is None


def test_extract_lgn_rslt_cd_from_pubc_response() -> None:
    text = (
        "nts_loginSystemCallback('TXPP', { 'lgnRsltCd' : '30', "
        "'sq2LgnCertYn' : 'Y' });"
    )
    assert IdPwAuth._extract_lgn_rslt_cd(text) == "30"
    assert IdPwAuth._extract_field(text, "sq2LgnCertYn") == "Y"


def test_is_pubc_failure_detects_both_quotation_styles() -> None:
    assert IdPwAuth._is_pubc_failure("body 'code' : 'F' more")
    assert IdPwAuth._is_pubc_failure("body 'code':'F' more")
    assert not IdPwAuth._is_pubc_failure("'code' : 'S'")


def test_extract_err_msg_decodes_uri_component() -> None:
    text = "alert(decodeURIComponent('%EB%B0%80%EB%A6%AC'))"
    msg = IdPwAuth._extract_err_msg(text)
    assert msg == "밀리"
