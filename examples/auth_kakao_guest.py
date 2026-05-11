"""비회원 카카오 간편인증 → 비회원 세션 발급 예제.

회원이 아닌 사용자 (이름 + 주민등록번호 + 휴대폰 + 카카오 인증) 로 홈택스에
로그인하는 흐름. 회원 ``KakaoAuth`` 와 동일 클래스를 쓰되 ``ssn`` 인자
하나 추가하면 비회원 모드로 분기한다.

권한 주의 — 비회원 세션은 지급명세서 / 세금신고내역 등 회원 전용 메뉴는
``PermissionDeniedError`` 가 떨어진다 (``SessionInfo.is_guest`` 로 사전
판별 가능). ``docs/hometax-facts.md`` §16 의 비회원 권한 매핑 참고.

사전 조건:

- ``.env`` 에 ``HOMETAX_NAME``, ``HOMETAX_PHONE``, ``HOMETAX_BIRTH``,
  ``HOMETAX_RRN`` 설정. ``HOMETAX_RRN`` 은 13자리 주민등록번호 (``-`` 무관).
  PII — 파일 권한 ``0o600`` 권장.

실행::

    uv run --env-file .env python examples/auth_kakao_guest.py
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
    rrn = os.environ.get("HOMETAX_RRN")
    if not (name and phone and birthday and rrn):
        print(
            "HOMETAX_NAME / HOMETAX_PHONE / HOMETAX_BIRTH / HOMETAX_RRN "
            "가 모두 필요합니다.",
            file=sys.stderr,
        )
        return 2

    auth = KakaoAuth(
        name=name,
        phone=phone,
        birthday=birthday,
        ssn=rrn,
    )
    client = HometaxClient.login(
        auth=auth,
        cache_path="captures/.session.guest.json",
        on_authenticate=lambda: print(
            "폰의 카카오톡에서 인증 알림을 승인해 주세요…",
        ),
        on_wait=lambda attempt: print(
            f"  대기 {attempt}/10 — 폰 승인을 기다리는 중",
        ),
    )
    info = client.session_info()
    print(
        f"로그인 완료. is_guest={info.is_guest}, "
        f"user_name={info.user_name}, tin={info.tin}"
    )
    if not info.is_guest:
        print(
            "  주의: 비회원 인증을 요청했으나 회원 세션으로 통과됨 "
            "(홈택스가 회원 가입된 사용자로 식별).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
