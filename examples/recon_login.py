"""홈택스 로그인 recon — 실제 브라우저로 인증 통과 후 cookies / HAR 캡처.

플랫폼 중립 (Linux / macOS / Windows). Playwright 번들 chromium 사용.

사전 준비:

    uv sync --extra bootstrap
    .venv/bin/playwright install chromium     # POSIX
    .venv\\Scripts\\playwright install chromium # Windows

기본 실행 (메인 포털 열고 → 사람이 '로그인' 클릭해 정상 흐름으로 로그인 →
결과 저장):

    .venv/bin/python examples/recon_login.py

⚠️ 메인 포털에서 출발해야 한다. 로그인 화면(UTXPPABA01) 에 deep-link 로
직접 진입하면 priming 이 안 되어 ID 로그인 폼이 정상 동작하지 않는다.

옵션:

    --output captures/idpw-2026-05  결과 저장 위치
    --url <URL>                     시작 URL (기본은 메인 포털)
    --auto-close                    쿠키 indicator 자동 종료 (기본은 수동 Enter)
    --headless                      창 없이 (헤드리스 — 보통은 비추)
    --no-har                        HAR 수집 끔
    --channel chrome                Playwright 번들 대신 시스템 Chrome 사용
    --timeout 900                   --auto-close 모드 대기 초 (기본 600)
    --indicator NTS_LOGIN_SYSTEM_CODE_P  --auto-close 신호 쿠키 (반복 가능)

생성 파일 (output 경로 기준):

    cookies.json        Playwright cookies — HometaxClient.from_cookies 에 그대로 주입
    storage_state.json  storage_state (cookies + localStorage 등)
    trace.har           HAR (request/response body 포함)
    meta.json           메타데이터 (URL, 쿠키 이름 목록)

산출물에는 세션 토큰과(ID/PW 인증 시) 비밀번호·주민번호 7자리가 포함될 수
있다. 외부 공유 금지.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hometax_client.bootstrap import (
    DEFAULT_START_URL,
    LOGIN_INDICATOR_COOKIES,
    capture_login,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HomeTax 로그인 recon 캡처 (cookies + HAR)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="결과 저장 경로 (기본: captures/<timestamp>/)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_START_URL,
        help=(
            "시작 URL (기본: 메인 포털 https://hometax.go.kr/ — 메인에서 '로그인' "
            "버튼으로 진입해야 priming 이 걸려 ID 로그인 폼이 동작)"
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="브라우저 창 없이 실행 (기본은 headed)",
    )
    parser.add_argument(
        "--no-har",
        action="store_true",
        help="HAR 미수집 (기본: 수집)",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Playwright channel (예: chrome, msedge). 미지정 시 번들 chromium.",
    )
    parser.add_argument(
        "--auto-close",
        action="store_true",
        help=(
            "쿠키 indicator 가 잡히면 자동 종료 (기본은 수동 — Enter 입력 시 "
            "종료). 다단계 인증(ID/PW+RRN 등) 은 1차에 잘못 fire 할 수 있어 "
            "recon 에는 비추."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="--auto-close 모드의 대기 초 (기본 600)",
    )
    parser.add_argument(
        "--indicator",
        action="append",
        metavar="COOKIE_NAME",
        help=(
            "--auto-close 모드의 신호 쿠키 (반복 가능). "
            f"기본: {list(LOGIN_INDICATOR_COOKIES)}"
        ),
    )
    args = parser.parse_args(argv)

    indicator = (
        tuple(args.indicator) if args.indicator else LOGIN_INDICATOR_COOKIES
    )
    wait_mode = "cookie" if args.auto_close else "manual"

    print(f"[recon] launching browser → {args.url}", file=sys.stderr)
    if wait_mode == "manual":
        print(
            "[recon] log in (메인 → 로그인 버튼 → ID/PW + RRN 등). "
            "완료 후 이 터미널에서 Enter 를 누르세요.",
            file=sys.stderr,
        )
    else:
        print(
            f"[recon] auto-close on cookies {list(indicator)} "
            f"(timeout {args.timeout:.0f}s).",
            file=sys.stderr,
        )

    try:
        paths = capture_login(
            output_dir=args.output,
            url=args.url,
            headed=not args.headless,
            record_har=not args.no_har,
            channel=args.channel,
            wait_mode=wait_mode,
            timeout=args.timeout,
            indicator_cookies=indicator,
        )
    except TimeoutError as exc:
        print(f"[recon] timeout: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"[recon] {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("[recon] interrupted", file=sys.stderr)
        return 130

    print(f"\n[recon] saved to: {paths['output_dir']}", file=sys.stderr)
    for key in ("cookies", "storage_state", "har", "meta"):
        if key in paths:
            print(f"  {key:>14}: {paths[key]}", file=sys.stderr)

    print(
        "\n[recon] round-trip 확인 (1 step):\n"
        "  from hometax_client import HometaxClient\n"
        f"  c = HometaxClient.from_cookies('{paths['cookies']}')\n"
        "  print(c.session_info())",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
