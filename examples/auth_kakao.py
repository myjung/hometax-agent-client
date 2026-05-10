"""카카오 간편인증 → 세션 캐시 저장 예제.

사전 조건:

- ``.env`` 에 ``HOMETAX_NAME``, ``HOMETAX_PHONE``, ``HOMETAX_BIRTH`` 설정.

실행::

    uv run --env-file .env python examples/auth_kakao.py
"""

from __future__ import annotations

import os
import sys

from hometax_client import HometaxClient
from hometax_client.auth import KakaoAuth


def main() -> int:
    name = os.environ.get("HOMETAX_NAME")
    phone = os.environ.get("HOMETAX_PHONE")
    birthday = os.environ.get("HOMETAX_BIRTH")
    if not (name and phone and birthday):
        print(
            "HOMETAX_NAME / HOMETAX_PHONE / HOMETAX_BIRTH 가 필요합니다.",
            file=sys.stderr,
        )
        return 2

    auth = KakaoAuth(name=name, phone=phone, birthday=birthday)
    client = HometaxClient.login(
        auth=auth,
        on_authenticate=lambda: print(
            "폰의 카카오톡에서 인증 알림을 승인해 주세요…",
        ),
        on_wait=lambda attempt: print(
            f"  대기 {attempt}/10 — 폰 승인을 기다리는 중",
        ),
    )
    info = client.session_info()
    print(f"로그인 완료. user_name={info.user_name}, tin={info.tin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
