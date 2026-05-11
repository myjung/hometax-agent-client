"""Browser-driven recon / cookie bootstrap (optional).

본 서브패키지는 ``[bootstrap]`` extras (Playwright) 가 있을 때만 동작한다.
라이브러리 코어는 절대 이 모듈을 import 하지 않는다. recon / 부트스트랩은
**호출자가 명시적으로** ``from hometax_client.bootstrap import ...`` 한 시점에만
들어온다.

용도:

- ID/PW 또는 OACX 등 어떤 인증이든 실제 브라우저로 통과시키고 산출물
  (cookies, HAR, storage_state) 을 저장한다.
- 산출된 ``cookies.json`` 은 ``HometaxClient.from_cookies`` 에 그대로
  주입할 수 있어, 이후 호출은 HTTP-only 코어로 진행한다.
- HAR 은 보호 스크립트 / 새 화면 분석용 (mitmproxy / Chrome DevTools 모두
  HAR import 지원).

⚠️ 산출물(쿠키/HAR) 에는 세션 토큰과 (ID/PW 인증 시) 비밀번호·주민번호 7자리
가 포함된다. 기본 출력 경로 ``captures/`` 는 ``.gitignore`` 처리되어 있다.
배포 / 공유 / 외부 업로드 금지.
"""

from __future__ import annotations

from .capture import (
    DEFAULT_LOGIN_URL,
    DEFAULT_PORTAL_URL,
    DEFAULT_START_URL,
    LOGIN_INDICATOR_COOKIES,
    CaptureSession,
    capture_login,
)
from .har import (
    ActionSchema,
    WqActionCall,
    iter_action_schemas,
    iter_wq_actions,
)

__all__ = [
    "CaptureSession",
    "capture_login",
    "DEFAULT_START_URL",
    "DEFAULT_PORTAL_URL",
    "DEFAULT_LOGIN_URL",
    "LOGIN_INDICATOR_COOKIES",
    "WqActionCall",
    "ActionSchema",
    "iter_wq_actions",
    "iter_action_schemas",
]
