"""신고안내문 공식 PDF 저장 demo (ClipReport R09 export).

기존 캐시된 세션 (회원 OACX 또는 비회원 ``ssn`` OACX) 을 사용해 종합소득세
신고안내문 PDF 를 발급받아 디스크에 저장한다. 라이브러리는 PDF bytes 만
반환하므로 (정책상 디스크 저장은 워크플로 영역), 본 demo 에서 파일 IO 를
직접 처리한다.

데이터 없는 케이스 (사용자 계정에 해당 연도 자료 없음) 도 정상 분기로
처리됨을 보여주기 위해 ``status="empty"`` 도 출력한다.

사전 조건:

- 세션 캐시 파일 (회원: ``captures/.session.json``, 비회원:
  ``captures/.session.guest.json``) 가 살아있어야 함. 만료된 경우
  ``examples/auth_kakao.py`` 또는 ``examples/auth_kakao_guest.py`` 로 재발급.

실행::

    .venv/bin/python examples/filing_help_pdf.py
    .venv/bin/python examples/filing_help_pdf.py --years 2024 2023 2022
    .venv/bin/python examples/filing_help_pdf.py --cache captures/.session.json

산출물 PDF 는 ``out/`` (``.gitignore`` 적용) 에 ``filing_help_{year}.pdf``
형태로 저장. 권한은 디렉토리 기본값 (현재 umask) 적용.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from hometax_client import HometaxClient
from hometax_client.exceptions import HometaxError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        default="captures/.session.guest.json",
        help="세션 캐시 파일 경로 (기본: 비회원)",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2024],
        help="조회 귀속연도 (기본: [2024])",
    )
    parser.add_argument(
        "--out",
        default="out",
        help="PDF 저장 디렉토리 (기본: out/)",
    )
    args = parser.parse_args()

    client = HometaxClient.from_cookies(args.cache)
    info = client.session_info()
    print(
        f"세션: is_guest={info.is_guest} user_name={info.user_name!r} "
        f"tin={info.tin!r}"
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for year in args.years:
        print(f"\n[{year}] filing_help_pdf …")
        try:
            result = client.income_tax.filing_help_pdf(year)
        except HometaxError as exc:
            print(f"  ✗ {type(exc).__name__}: {exc}")
            continue
        print(
            f"  status={result.status} "
            f"page_count={result.page_count} "
            f"message={result.message}"
        )
        if result.status == "found" and result.pdf:
            path = out_dir / f"filing_help_{year}.pdf"
            path.write_bytes(result.pdf)
            print(f"  ✓ saved {path} ({len(result.pdf)} bytes)")
        elif result.status == "empty":
            print(
                "  → 해당 연도에 자료가 없는 정상 케이스로 분류 "
                "(reportkey 또는 page count 없음)"
            )
        # failed 는 위에서 message 로 출력됨
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
