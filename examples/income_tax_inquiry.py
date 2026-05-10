"""종합소득세 신고도움 서비스 호출 예제.

자료구분별 소득내역, 신고안내문 데이터, 보험료 조회까지 호출해 화면에
요약을 출력한다. 데이터만 dict 로 반환하므로 어떻게 저장할지는 호출 측
책임.

실행::

    uv run --env-file .env python examples/income_tax_inquiry.py
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
    print(f"로그인 사용자: {info.user_name}")

    income = client.income_tax.income_details(attr_year=2024)
    print(f"\n자료구분 그룹: {len(income['groups'])}개")
    for code, group in income["groups"].items():
        print(f"  {code} / {group['material_kind_name']}: "
              f"{group['total_count']}건")

    address = client.income_tax.address_candidates(attr_year=2024)
    print(f"\n주소 후보 status: {address['status']}")
    if address.get("road_address"):
        print(f"  도로명주소: {address['road_address']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
