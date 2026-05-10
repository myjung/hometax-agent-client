"""홈택스 인증 — OACX 간편인증(카카오/네이버) + ID/PW 직접 로그인.

OACX 는 사용자가 폰에서 인증 버튼을 눌러야 하므로 자동화 불가. ID/PW 는 풀
자동이지만 2026-05 부터 ``pubcLogin`` 이 브라우저 보호 스크립트로 막혀 있어
직접 POST 가 거부될 수 있다. 그 경우 별도 부트스트랩 도구 (``[bootstrap]``
extras) 로 cookies 를 한 번 받아 ``HometaxClient.from_cookies`` 로 주입하는
것을 권장.
"""

from .idpw import IdPwAuth, IdPwAuthError, IdPwResult
from .kakao import KakaoAuth
from .naver import NaverAuth
from .oacx import OACXAuth, OACXAuthError, OACXResult

__all__ = [
    "OACXAuth",
    "OACXAuthError",
    "OACXResult",
    "KakaoAuth",
    "NaverAuth",
    "IdPwAuth",
    "IdPwAuthError",
    "IdPwResult",
]
