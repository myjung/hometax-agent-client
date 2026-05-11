"""Naver 인증 → 세션 export → Playwright 로 메뉴 조회 e2e (에이전트 주도).

사용자는 폰의 네이버 앱 알림 승인만 하면 된다. 나머지는 자동:

  1. NaverAuth 흐름 (.env 의 ``HOMETAX_NAME`` / ``HOMETAX_PHONE`` /
     ``HOMETAX_BIRTH``).
  2. HTTP-only 세션 → ``export_storage_state`` → Playwright storage_state.
  3. ``CaptureSession`` (headless) 로 메인 포털 진입 + HAR dump.
  4. ``iter_wq_actions`` 로 발생한 ``wqAction.do`` 호출 목록 출력.

실행::

    uv run --env-file .env python examples/recon_e2e_naver.py

Playwright 번들 chromium 이 OS 빌드를 못 가지면 시스템 Chrome 사용:

    .venv/bin/python examples/recon_e2e_naver.py --channel chrome

산출물: ``captures/naver-e2e/`` 하위 (cookies / storage_state / HAR / meta).
``.gitignore`` 됨.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from hometax_client.auth import NaverAuth
from hometax_client.auth.oacx import OACXAuthError
from hometax_client.bootstrap import CaptureSession, iter_wq_actions

OUTPUT_DIR = Path("captures/naver-e2e")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--channel",
        default=os.environ.get("RECON_CHANNEL"),
        help=(
            "Playwright channel (예: 'chrome' / 'msedge'). 미지정 시 번들 "
            "chromium. Ubuntu 26.04 같이 OS 전용 번들이 없는 환경에선 "
            "'chrome' 권장 (`RECON_CHANNEL` env 도 가능)."
        ),
    )
    args = parser.parse_args()

    name = os.environ.get("HOMETAX_NAME")
    phone = os.environ.get("HOMETAX_PHONE")
    birthday = os.environ.get("HOMETAX_BIRTH")
    if not (name and phone and birthday):
        _log("HOMETAX_NAME / HOMETAX_PHONE / HOMETAX_BIRTH 환경변수가 필요합니다.")
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _log("[e2e] 1/4 Naver 인증 — 폰의 네이버 앱 알림을 승인해주세요.")
    auth = NaverAuth(name=name, phone=phone, birthday=birthday)
    try:
        auth.authenticate(
            on_wait=lambda i: _log(f"[e2e]   폰 승인 대기 {i}/10"),
        )
    except OACXAuthError as exc:
        _log(f"[e2e] 인증 실패: {exc}")
        return 3

    client = auth.to_client()
    try:
        info = client.session_info()
    except Exception as exc:
        _log(f"[e2e] session_info 실패: {exc}")
        return 4
    client.tin = info.tin
    _log(f"[e2e]   인증 OK user_name={info.user_name} tin={info.tin}")

    storage_state_path = OUTPUT_DIR / "storage_state.json"
    client.export_storage_state(storage_state_path)
    _log(f"[e2e] 2/4 storage_state → {storage_state_path}")

    _log(
        f"[e2e] 3/4 Playwright (headless, channel={args.channel!r}) 로 메인 진입",
    )
    with CaptureSession(
        storage_state=storage_state_path,
        output_dir=OUTPUT_DIR,
        headed=False,
        channel=args.channel,
    ) as cap:
        cap.page.goto("https://hometax.go.kr/", wait_until="load")
        try:
            cap.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as exc:
            _log(f"[e2e]   networkidle 대기 timeout (무시): {exc}")
        _log(f"[e2e]   page.url={cap.page.url}")
        try:
            _log(f"[e2e]   page.title={cap.page.title()!r}")
        except Exception as exc:
            _log(f"[e2e]   title 실패 (무시): {exc}")
        cap.dump()

    har_path = OUTPUT_DIR / "trace.har"
    _log(f"[e2e] 4/4 HAR 분석 — {har_path}")

    calls = list(iter_wq_actions(har_path))
    if not calls:
        _log("[e2e]   wqAction.do 호출 없음 — 메인 페이지만으로는 RPC 가 안 떴을 수 있음.")
    else:
        _log(f"[e2e]   wqAction 호출 {len(calls)} 개:")
        for call in calls:
            print(
                f"  {call.action_id:36}  screen={call.screen_id!s:14}  "
                f"host={call.host:24}  status={call.status}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
