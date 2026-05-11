"""홈택스 service-health CLI.

라이브 ``common_te-min.js`` 의 NTS_KEYS 를 라이브러리 active 키와 비교한다.

용법::

    python -m hometax_client.health             # drift 검사 (exit 0/1)
    python -m hometax_client.health --refresh   # drift 시 cache 갱신
    python -m hometax_client.health --cache-path captures/.nts_keys.json

cron / CI 에 ``python -m hometax_client.health`` 를 걸어두면 키 회전을 즉시
검출 가능. 자동 갱신을 원하면 ``--refresh`` 까지.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .crypto import (
    ENV_KEYS_FILE,
    NTS_KEYS_BASELINE,
    NTS_KEYS_JS_URL,
    active_keys,
    save_keys,
    verify_keys_in_sync,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "홈택스 NTS_KEYS health check — 라이브 JS 와 active 키 비교"
        ),
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="drift 시 cache 갱신 (exit 0). 미지정시 drift 보고만 (exit 1).",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=None,
        help=(
            "cache 저장 위치 override. 미지정시 "
            f"${ENV_KEYS_FILE} 또는 OS 기본 cache 경로 사용."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="라이브 JS fetch 타임아웃 초 (기본 15)",
    )
    args = parser.parse_args(argv)

    print(f"[health] source: {NTS_KEYS_JS_URL}", file=sys.stderr)
    try:
        report = verify_keys_in_sync(timeout=args.timeout)
    except Exception as exc:  # network / parser
        print(f"[health] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    using_baseline = report.active == NTS_KEYS_BASELINE
    print(
        f"[health] active source: "
        f"{'baseline (hardcoded)' if using_baseline else 'cache file'}",
        file=sys.stderr,
    )
    print(f"[health] in_sync: {report.in_sync}", file=sys.stderr)

    if not report.in_sync:
        print(
            f"[health] drift at indices {list(report.drift_indices)}",
            file=sys.stderr,
        )
        for i in report.drift_indices:
            print(
                f"  [{i}] active={report.active[i]!r}",
                file=sys.stderr,
            )
            print(
                f"      live  ={report.live[i]!r}",
                file=sys.stderr,
            )
        if args.refresh:
            saved = save_keys(report.live, path=args.cache_path)
            print(
                f"[health] refreshed cache: {saved}",
                file=sys.stderr,
            )
            verify = active_keys()
            if verify == report.live:
                print(
                    "[health] ✓ active keys now match live",
                    file=sys.stderr,
                )
                return 0
            print(
                "[health] ⚠ saved but active still differs — "
                f"check {ENV_KEYS_FILE} env override",
                file=sys.stderr,
            )
            return 3
        print(
            "[health] re-run with --refresh to update cache",
            file=sys.stderr,
        )
        return 1

    print("[health] ✓ NTS_KEYS in sync", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
