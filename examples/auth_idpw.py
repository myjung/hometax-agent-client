"""ID/PW 직접 로그인 예제.

⚠️ 2026-05 부터 홈택스가 ``pubcLogin.do`` 본문에 브라우저 보호 스크립트를
적용했다. 직접 POST 가 막히면 ``ProtectedLoginError`` 가 raise 된다. 그
경우 ``[bootstrap]`` extras 의 부트스트랩 도구를 사용하거나 OACX 인증으로
전환하라.
"""

from __future__ import annotations

import os
import sys

from hometax_client import HometaxClient, ProtectedLoginError
from hometax_client.auth import IdPwAuth, IdPwAuthError


def main() -> int:
    user_id = os.environ.get("HOMETAX_USER_ID")
    password = os.environ.get("HOMETAX_PASSWORD")
    rrn = os.environ.get("HOMETAX_RRN")
    if not (user_id and password and rrn):
        print(
            "HOMETAX_USER_ID / HOMETAX_PASSWORD / HOMETAX_RRN 가 필요합니다.",
            file=sys.stderr,
        )
        return 2

    auth = IdPwAuth(user_id=user_id, password=password, rrn=rrn)
    try:
        client = HometaxClient.login(
            auth=auth,
            cache_path="captures/.session-idpw.json",
        )
    except ProtectedLoginError as exc:
        print(
            f"보호 스크립트로 직접 로그인이 막혔습니다: {exc}",
            file=sys.stderr,
        )
        return 3
    except IdPwAuthError as exc:
        print(f"ID/PW 인증 실패: {exc}", file=sys.stderr)
        return 4

    info = client.session_info()
    print(f"로그인 완료. user_name={info.user_name}, tin={info.tin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
