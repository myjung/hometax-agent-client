"""쿠키 기반 기본 조회 예제.

사전 조건:

- 브라우저 또는 부트스트랩 도구로 ``cookies.json`` 을 한 번 받아둠.
- ``HOMETAX_USER_ID`` 환경변수에 본인 홈택스 ID.

실행::

    uv run --env-file .env python examples/basic_inquiry.py
"""

from __future__ import annotations

import os
import sys

from hometax_client import HometaxClient


def main() -> int:
    cookies_path = os.environ.get(
        "HOMETAX_COOKIES",
        "captures/cookies.json",
    )
    user_id = os.environ.get("HOMETAX_USER_ID")
    if not user_id:
        print("HOMETAX_USER_ID 환경변수가 필요합니다.", file=sys.stderr)
        return 2

    client = HometaxClient.from_cookies(
        cookies_path=cookies_path,
        user_id=user_id,
    )
    info = client.session_info()
    print(f"로그인된 사용자: {info.user_name} (tin={info.tin})")

    statements = client.inquiries.income_statements(attr_year=2024)
    print(f"\n2024 귀속 지급명세서: {len(statements)}건")
    for statement in statements[:5]:
        print(
            f"  - {statement.material_kind_name}"
            f" / {statement.payer_name}"
            f" / {statement.period_start}~{statement.period_end}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
