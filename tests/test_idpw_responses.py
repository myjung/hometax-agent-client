"""캡처된 실제 응답으로 IdPwAuth parser 회귀.

캡처 출처: ``docs/hometax-facts.md §15`` (2026-05-10). PII 는 마스킹되어
있다 — fixture 파일 안의 모든 식별자는 placeholder.
"""

from __future__ import annotations

import json
from pathlib import Path

from hometax_client.auth.idpw import IdPwAuth

FIXTURES = Path(__file__).parent / "fixtures" / "2026-05-10"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_r07_login_value_extraction() -> None:
    """R07 ``result='S'`` 응답에서 회전된 자격증명을 IdPwAuth 가 추출."""
    data = json.loads(_read("r07_validate_success.json"))
    values = IdPwAuth._extract_r07_login_values(data)
    assert values is not None
    new_id, new_pswd = values
    assert new_id == "ID_PLACEHOLDER_HEX_ID_PLACEHOLDER"
    assert new_pswd == (
        "PSWD_PLACEHOLDER_HEX_PSWD_PLACEHOLDER_HEX_PSWD_PLACEHOLDER_HE"
    )
    # resultMsg.result == "S" — IdPwAuth.validate_credentials 가 통과 신호로 사용.
    assert data["resultMsg"]["result"] == "S"


def test_pubclogin_step1_indicates_rrn_required() -> None:
    """1차 응답: ``lgnRsltCd=30`` (RRN 필요) — IdPwAuth 가 2차로 분기하는 신호."""
    text = _read("pubclogin_step1_rrn_required.txt")
    assert IdPwAuth._extract_lgn_rslt_cd(text) == "30"
    assert IdPwAuth._is_pubc_failure(text) is False
    assert IdPwAuth._extract_field(text, "tin") == "000000999999999999"
    assert IdPwAuth._extract_field(text, "sq2LgnCertYn") == "N"
    assert IdPwAuth._extract_field(text, "code") == "S"


def test_pubclogin_step2_success() -> None:
    """2차 응답: ``lgnRsltCd=01`` (정상) — tin 추출 성공."""
    text = _read("pubclogin_step2_success.txt")
    assert IdPwAuth._extract_lgn_rslt_cd(text) == "01"
    assert IdPwAuth._is_pubc_failure(text) is False
    assert IdPwAuth._extract_field(text, "tin") == "000000999999999999"
    assert IdPwAuth._extract_field(text, "sq2LgnCertYn") == "Y"
