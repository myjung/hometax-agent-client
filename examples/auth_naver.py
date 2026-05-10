"""네이버 간편인증 → 세션 캐시 저장 (recon 친화 verbose 로그 포함).

OACX 흐름의 네이버 provider 검증용. 카카오 흐름과 동일하다고 가정하지만
``hometax_client/auth/naver.py`` docstring 의 단서대로 실제 응답이 어디서
갈리는지 stage-level 로 출력한다 (실패 시 어디까지 갔는지 명확히 보이도록).

사전 조건:

- ``.env`` 에 ``HOMETAX_NAME``, ``HOMETAX_PHONE``, ``HOMETAX_BIRTH``.
- 폰의 네이버 앱이 본인 명의 (인증 알림 받을 단말).

실행::

    uv run --env-file .env python examples/auth_naver.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from hometax_client import HometaxClient
from hometax_client.auth import NaverAuth, OACXAuth
from hometax_client.auth.oacx import OACXAuthError


def _short(d: Any, limit: int = 200) -> str:
    s = json.dumps(d, ensure_ascii=False) if not isinstance(d, str) else d
    return s if len(s) <= limit else s[:limit] + "…"


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

    auth = NaverAuth(name=name, phone=phone, birthday=birthday)

    # Stage-level 모니터링 — 카카오와 어디서 갈리는지 즉시 보이도록 패치.
    print(f"[naver] provider={auth.PROVIDER!r} aid={auth.NETFUNNEL_AID!r}")

    try:
        token, tx_id = auth.initiate()
        print(f"[naver] 1. trans OK  tx_id={tx_id[:12]}… token={token[:12]}…")
    except OACXAuthError as exc:
        print(f"[naver] 1. trans FAIL: {exc}", file=sys.stderr)
        return 3

    try:
        nf = auth.get_netfunnel()
        if nf is None:
            print("[naver] 2. netfunnel  SKIP (5002:501 — aid 미등록)")
        else:
            print(f"[naver] 2. netfunnel  OK  {nf[:60]}…")
    except OACXAuthError as exc:
        print(f"[naver] 2. netfunnel FAIL: {exc}", file=sys.stderr)
        return 4

    try:
        cx_id = auth.request_authentication()
        print(f"[naver] 3. authen/request OK  cx_id={cx_id[:12]}…")
    except OACXAuthError as exc:
        print(f"[naver] 3. authen/request FAIL: {exc}", file=sys.stderr)
        return 5

    print("[naver] 폰의 네이버 앱에서 인증 알림을 승인해 주세요…")

    def _on_wait(attempt: int) -> None:
        print(f"[naver]   poll {attempt}/10 — 폰 승인 대기")

    def _on_response(attempt: int, data: dict[str, Any]) -> None:
        keys = sorted(data.keys())[:8]
        status = data.get("oacxStatus") or data.get("oacxCode") or "?"
        msg = (
            data.get("clientMessage")
            or data.get("systemMessage")
            or data.get("_raw")
            or ""
        )
        print(
            f"[naver]   ← attempt={attempt} status={status!r} "
            f"msg={msg!r:.60s} keys={keys}"
        )

    try:
        cert_token = auth.poll_result(
            on_wait=_on_wait,
            on_response=_on_response,
        )
        print(f"[naver] 4. poll_result OK  cert_token={cert_token[:12]}…")
    except OACXAuthError as exc:
        print(f"[naver] 4. poll_result FAIL: {exc}", file=sys.stderr)
        return 6

    try:
        cookies = auth.login_to_hometax()
    except OACXAuthError as exc:
        print(f"[naver] 5. pubcLogin FAIL: {exc}", file=sys.stderr)
        return 7

    have = sorted(cookies.keys())
    print(f"[naver] 5. pubcLogin OK  cookies={have}")

    client = auth.to_client()
    try:
        info = client.session_info()
    except Exception as exc:
        print(f"[naver] 6. session_info FAIL: {exc}", file=sys.stderr)
        return 8

    client.tin = info.tin
    out = client.save_session("captures/.session-naver.json")
    print(
        f"[naver] 6. session_info OK  user_name={info.user_name} "
        f"tin={info.tin} → cached at {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
