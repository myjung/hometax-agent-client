"""hometax_client 예외 계층.

모든 라이브러리 예외는 ``HometaxError`` 를 상속한다. 호출 측에서
``except HometaxError:`` 한 줄로 라이브러리 발생 에러 전체를 잡을 수 있다.
"""

from __future__ import annotations

from typing import Any


class HometaxError(Exception):
    """모든 hometax_client 예외의 베이스."""


class WqActionFailedError(HometaxError):
    """``wqAction.do`` 응답이 ``result='F'`` 로 돌아온 모든 실패의 공통 부모.

    구체 분류 (SessionExpired/Validation/LoginRequired) 가 안 되는 케이스에서
    직접 raise 됨. ``action_id``, ``raw_msg`` 로 디버그 컨텍스트 보존.
    """

    def __init__(
        self,
        msg: str = "",
        *,
        action_id: str | None = None,
        raw_msg: str | None = None,
    ) -> None:
        super().__init__(msg)
        self.action_id = action_id
        self.raw_msg = raw_msg or msg


class SessionExpiredError(WqActionFailedError):
    """세션 쿠키가 만료되어 서버가 세션 없음을 반환.

    재인증 후 캐시 갱신 필요. ``HometaxClient.login(..., force_reauth=True)``
    로 재인증할 수 있다. 응답 메시지가 "세션정보가 존재하지 않습니다." 인 경우
    진짜 세션 만료 외에도 해당 서브시스템의 권한이 없거나 별도 인증이 필요한
    경우와 메시지가 동일해 분간이 어렵다. 재인증 후에도 같은 에러가 나면 권한
    문제 가능성이 높다.
    """


class ValidationError(WqActionFailedError):
    """요청 본문의 필수 파라미터 누락 / 형식 오류.

    세션과 무관 — 호출 측에서 body 를 수정해야 한다.
    """


class LoginRequiredError(WqActionFailedError):
    """현재 세션은 살아있지만 호출한 액션에 별도 인증/권한이 필요.

    홈택스가 ``[FWE]`` 코드와 함께 "로그인이 되어있지 않습니다." 같은 메시지를
    반환하는 경우. 예: 세무대리인 권한이 필요한 액션을 일반 사용자 세션으로
    호출.
    """


class AuthGradeInsufficientError(WqActionFailedError):
    """현재 인증 등급으로 호출이 거부됨 (ID/PW 등급으로 카카오/공인인증서 필요 액션 호출 등).

    ``classify_failure`` 가 응답 메시지에 "공인인증서로 로그인" / "인증서로 로그인"
    등 등급 상승을 명시적으로 요구하는 문구가 있을 때 자동 분류한다. 서비스
    모듈이 사전 검사로 raise 하는 것도 가능하다.
    """


class BusinessAccountUnsupportedError(WqActionFailedError):
    """사업자용 ID 로 개인 자료 조회를 시도해 거부됨.

    permission.do 응답 메시지 패턴 + 화면 식별자로 추정. 정확 분류가 어려운
    경우 ``SessionExpiredError`` 로 대체될 수 있다.
    """


class PermissionDeniedError(WqActionFailedError):
    """현재 인증으로 접근 불가능한 메뉴/화면을 호출.

    ``LoginRequiredError`` 와 구분: 후자는 "별도 인증 추가" (재로그인 / 등급
    상승) 로 해결 가능. 본 에러는 **현재 인증의 종류 자체가 부적합** —
    재인증해도 같은 결과. 회원 전용 메뉴를 비회원 세션으로 호출하는 경우 등.

    검증된 트리거 (2026-05-11 비회원 세션 라이브 캡처):

    - 메시지: ``"권한이 없는 화면입니다."``
    - 코드: ``"0000005,|+|0000001,..."``
    - 예: 비회원 세션으로 지급명세서 (``UTXPPBAA48`` / ``ATXPPBAA001R16``)
      또는 세금신고내역 (``UTXPPBAA47`` / ``ATXPPBAA001R15``) 호출 시.
    """


class BlockedError(HometaxError):
    """홈택스가 명시적인 차단 코드를 반환 (EIE2*, ECE10* 등).

    스크래핑 탐지에 걸렸을 가능성. 호출 빈도/패턴을 줄이거나 잠시 멈춰야 한다.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"홈택스 차단 코드 {code}: {message}")
        self.code = code


class UnknownResponseError(HometaxError):
    """응답 본문이 JSON 으로 파싱되지 않거나 expected 한 키가 없음."""


class ResponseSchemaDriftError(HometaxError):
    """라이브러리가 알고 있던 응답 shape 과 다른 응답이 도착.

    홈택스가 응답 구조를 바꿨을 때 raise. ``raw`` 로 응답 dict 전체를 들고
    있어 호출 측이 우회/디버그할 수 있다.
    """

    def __init__(
        self,
        action_id: str,
        missing: list[str],
        raw: dict[str, Any],
    ) -> None:
        super().__init__(
            f"{action_id} 응답에서 필수 필드 누락: {missing!r}"
        )
        self.action_id = action_id
        self.missing = missing
        self.raw = raw


class ProtectedLoginError(HometaxError):
    """ID/PW 직접 로그인이 홈택스 보호 스크립트로 거부됨.

    2026-05 부터 ``pubcLogin.do`` 가 브라우저 보호 스크립트로 random
    protected fields 형태로 요청 본문을 감싼다. capture-and-replay 방식으로
    이 보호를 통과할 방법이 확정될 때까지는, 별도의 부트스트랩 도구
    (``[bootstrap]`` extras) 로 cookies 를 한 번 받아 ``HometaxClient.from_cookies``
    로 주입하는 것을 권장.
    """


# ------------------------------------------------------------------ #
# 응답 result='F' 메시지 → 예외 분류                                   #
# ------------------------------------------------------------------ #


def _first_text(value: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        item = value.get(key)
        if item is None:
            continue
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, (int, float)):
            return str(item)
    return ""


def _collect_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        parts: list[str] = []
        for key in (
            "msg",
            "message",
            "errorMsg",
            "errMsg",
            "detailMsg",
            "systemMessage",
            "clientMessage",
            "code",
            "result",
        ):
            parts.extend(_collect_text(value.get(key)))
        return parts
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(_collect_text(item))
        return parts
    return []


def _failure_message(rm: dict[str, Any]) -> str:
    msg = _first_text(rm, ("msg", "message", "errMsg", "detailMsg"))
    if msg:
        return msg
    nested = " / ".join(dict.fromkeys(_collect_text(rm.get("errorMsg"))))
    return nested


def _failure_code(rm: dict[str, Any]) -> str:
    code = _first_text(rm, ("code", "errCd", "errorCode"))
    if code:
        return code
    error_msg = rm.get("errorMsg")
    if isinstance(error_msg, dict):
        nested = _first_text(error_msg, ("code", "errCd", "errorCode"))
        if nested:
            return nested
    # ``rtnVal`` 안에 code 가 들어오는 케이스 (일부 권한/세션 거부 응답).
    rtn_val = rm.get("rtnVal")
    if isinstance(rtn_val, dict):
        return _first_text(rtn_val, ("code", "errCd", "errorCode"))
    return ""


def classify_failure(
    rm: dict[str, Any],
    *,
    action_id: str | None = None,
) -> WqActionFailedError:
    """``wqAction.do`` 응답의 resultMsg dict 를 분석해 적절한 예외 인스턴스 반환.

    호출자가 raise 하면 된다. 메시지 패턴:

    - ``[FWE]`` 또는 ``로그인이 되어있지 않`` → ``LoginRequiredError``
    - ``공인인증서로 로그인`` / ``인증서로 로그인`` → ``AuthGradeInsufficientError``
    - ``권한이 없는 화면`` / ``권한이 없는 메뉴`` → ``PermissionDeniedError``
    - ``필수입력`` / ``올바르지 않`` / ``형식이`` / ``범위`` → ``ValidationError``
    - 그 외 → ``SessionExpiredError`` (실제 권한 문제도 같은 메시지인 경우 있음)
    """
    code = _failure_code(rm)
    msg = _failure_message(rm) or (
        f"code={code}"
        if code
        else "홈택스가 상세 메시지 없는 실패 응답을 반환했습니다."
    )

    if "[FWE]" in msg or "로그인이 되어있지 않" in msg:
        return LoginRequiredError(
            f"권한/별도 인증 필요: msg={msg!r} code={code!r}",
            action_id=action_id,
            raw_msg=msg,
        )

    auth_grade_keywords = (
        "공인인증서로 로그인",
        "인증서로 로그인",
    )
    if any(keyword in msg for keyword in auth_grade_keywords):
        return AuthGradeInsufficientError(
            f"인증 등급 부족: msg={msg!r}",
            action_id=action_id,
            raw_msg=msg,
        )

    permission_keywords = (
        "권한이 없는 화면",
        "권한이 없는 메뉴",
        # ``pubcPermission`` 가 msg slot 에 그대로 잡힌 케이스 — 응답 dict
        # 구조에 따라 ``code`` 슬롯이 비어 있고 ``errorMsg.code`` 가 msg 로
        # 추출되는 경로가 있다.
        "pubcPermission",
    )
    permission_codes = ("pubcPermission",)
    if (
        any(keyword in msg for keyword in permission_keywords)
        or code in permission_codes
    ):
        return PermissionDeniedError(
            f"메뉴/화면 권한 없음: msg={msg!r} code={code!r}",
            action_id=action_id,
            raw_msg=msg,
        )

    validation_keywords = (
        "필수입력",
        "올바르지 않",
        "형식이 ",
        "범위",
        "필수 입력",
    )
    if any(keyword in msg for keyword in validation_keywords):
        return ValidationError(
            f"입력 검증 실패: msg={msg!r}",
            action_id=action_id,
            raw_msg=msg,
        )

    return SessionExpiredError(
        f"세션 만료 의심: result={rm.get('result')}, msg={msg}",
        action_id=action_id,
        raw_msg=msg,
    )
