"""HAR 캡처에서 hometax RPC 호출 (wqAction / jsonAction) 을 actionId 별 정리.

본 라이브러리의 캡처 산출물 (``trace.har``) 안에서 각 actionId 의 요청 /
응답을 한 눈에 보기.

용도:
- 새 service 구현 전 wire 형식 확정
- 데스크탑 vs 모바일 path 비교
- 응답에 특정 식별자 (예: ``cvaId``) 포함된 호출 검색

실행::

    # 모든 actionId 요약 (host / count / 첫 응답 상태)
    .venv/bin/python examples/inspect_har.py captures/probe-wage-.../trace.har

    # 특정 actionId 상세 (request body + response body 일부)
    .venv/bin/python examples/inspect_har.py captures/<HAR>/trace.har \\
        --action ATXPPBAA001R16

    # 응답에 특정 키 포함된 호출 검색
    .venv/bin/python examples/inspect_har.py captures/<HAR>/trace.har \\
        --has-key dsdEtcSbmsBrkdNtplDVOList

    # 모든 actionId 별 첫 호출 1건씩 req/resp 덤프
    .venv/bin/python examples/inspect_har.py captures/<HAR>/trace.har \\
        --first-of-each
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from hometax_client.bootstrap import (
    WqActionCall,
    iter_action_schemas,
    iter_wq_actions,
)


def _walk_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            yield path
            yield from _walk_keys(v, path)
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
        yield from _walk_keys(obj[0], f"{prefix}[0]")


def _dump_call(call: WqActionCall, *, truncate: int = 600) -> None:
    print(f"\n=== {call.action_id} ({call.host}) ===")
    print(f"  screen_id   : {call.screen_id}")
    print(f"  status      : {call.status}")
    print(f"  url         : {call.url[:140]}")
    if call.request_body:
        body_text = json.dumps(call.request_body, ensure_ascii=False)
        print(f"  REQ body    : {body_text[:truncate]}")
    elif call.request_text:
        print(f"  REQ raw     : {call.request_text[:truncate]!r}")
    if call.response_body:
        # 상위 키 + 리스트 필드 size
        keys = list(call.response_body.keys())[:12]
        print(f"  RESP keys   : {keys}")
        rm = (
            call.response_body.get("resultMsg")
            or call.response_body.get("RESULT", {}).get("resultMsg")
            or call.response_body.get("RESULT", {})
        )
        if isinstance(rm, dict):
            print(
                f"  RESP result : code={rm.get('code') or rm.get('result')!r} "
                f"msg={(rm.get('msg') or '')[:80]!r}"
            )
        # 리스트 필드 size
        for k, v in call.response_body.items():
            if isinstance(v, list):
                print(f"    .{k}: list({len(v)})")
    elif call.response_text:
        print(f"  RESP raw[:200]: {call.response_text[:200]!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path, help="HAR 파일 경로")
    parser.add_argument(
        "--action", "-a", default=None,
        help="특정 actionId 만 (substring 매치 — 'ATERN' 도 가능)",
    )
    parser.add_argument(
        "--host", default=None,
        help="특정 host 만 (substring 매치 — 'mob.tbht' 등)",
    )
    parser.add_argument(
        "--has-key", default=None, metavar="KEY",
        help="응답에 특정 key 포함된 호출만 (예: cvaId)",
    )
    parser.add_argument(
        "--first-of-each", action="store_true",
        help="각 actionId 의 첫 호출 1건씩만 상세 dump",
    )
    parser.add_argument(
        "--summary", "-s", action="store_true",
        help="요약 표만 (action × host × count + 첫 응답 result)",
    )
    parser.add_argument(
        "--catalog", action="store_true",
        help=(
            "HAR 안 로드된 페이지 JS 들에서 action 정의 (id + body schema) "
            "추출. 사용자가 GUI 클릭 안 한 actionId 도 카탈로그 보임 — 페이지 "
            "load 시 JS 안에 정의돼 있기만 하면 노출."
        ),
    )
    parser.add_argument(
        "--truncate", type=int, default=600,
        help="body 출력 길이 제한 (기본 600자)",
    )
    args = parser.parse_args(argv)

    if not args.har.exists():
        print(f"HAR 파일 없음: {args.har}", file=sys.stderr)
        return 2

    if args.catalog:
        schemas = list(iter_action_schemas(args.har))
        # actionId 별 dedupe (첫 발견)
        seen: dict[str, object] = {}
        for s in schemas:
            if args.action and args.action not in s.action_id:
                continue
            if s.action_id in seen:
                continue
            seen[s.action_id] = s
        print(
            f"# {args.har} : 카탈로그 {len(seen)} unique actionId "
            f"(page JS 추출)",
            file=sys.stderr,
        )
        print(
            f"\n{'actionId':30s} {'input_targets':30s} {'output_sources':40s} page",
        )
        for aid, sch in sorted(seen.items()):
            page = sch.page_url.split("/")[-1].split("?")[0]
            in_t = ",".join(sch.input_targets) or "-"
            out_s = ",".join(sch.output_sources)[:38] or "-"
            print(f"{aid:30s} {in_t[:30]:30s} {out_s:40s} {page}")
        return 0

    calls = list(iter_wq_actions(args.har))
    print(f"# {args.har} : {len(calls)} actionId 호출", file=sys.stderr)

    # 필터
    if args.action:
        calls = [c for c in calls if args.action in c.action_id]
    if args.host:
        calls = [c for c in calls if args.host in c.host]
    if args.has_key:
        calls = [
            c for c in calls
            if any(args.has_key in k for k in _walk_keys(c.response_body))
        ]
    print(f"# 필터 후: {len(calls)} 호출", file=sys.stderr)

    if args.summary:
        groups: dict[tuple[str, str, str | None], int] = defaultdict(int)
        first_result: dict[tuple[str, str, str | None], str] = {}
        for c in calls:
            key = (c.action_id, c.host, c.screen_id)
            groups[key] += 1
            if key not in first_result:
                rm = (
                    c.response_body.get("resultMsg")
                    or c.response_body.get("RESULT", {}).get("resultMsg")
                    or c.response_body.get("RESULT", {})
                )
                first_result[key] = str(
                    rm.get("code") or rm.get("result")
                    if isinstance(rm, dict) else "?"
                )[:10]
        print(
            f"\n{'actionId':30s} {'host':28s} {'screen':15s} "
            f"{'count':>5s} result",
        )
        for (aid, host, screen), count in sorted(groups.items()):
            print(
                f"{aid:30s} {host:28s} {(screen or ''):15s} "
                f"{count:>5d} {first_result.get((aid,host,screen),'')}"
            )
        return 0

    if args.first_of_each:
        seen: set[str] = set()
        for c in calls:
            if c.action_id in seen:
                continue
            seen.add(c.action_id)
            _dump_call(c, truncate=args.truncate)
    else:
        for c in calls:
            _dump_call(c, truncate=args.truncate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
