"""네이버 간편인증 (``naver_v1.5``).

OACX 흐름은 카카오와 동일. provider 만 다르다.

검증 (2026-05-10): 본인 계정으로 ``examples/auth_naver.py`` 실행 → 6단계
(`trans → netfunnel → authen/request → poll → pubcLogin → session_info`)
모두 카카오와 동일 흐름으로 통과. 코드 변경 없이 ``_build_authen_body`` 의
provider-specific 필드 그대로 동작. 인증 등급은 카카오 OACX 와 동일하게
지급명세서 등 상위 등급 액션 호출 가능 (``userCertClCd=19`` /
``lgnCertCd=01``).
"""

from __future__ import annotations

from .oacx import OACXAuth


class NaverAuth(OACXAuth):
    PROVIDER_ID = "naver"
    PROVIDER = "naver_v1.5"
    NETFUNNEL_AID = "simple_cert_naver"
