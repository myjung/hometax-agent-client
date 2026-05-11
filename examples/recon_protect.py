"""pubcLogin 보호 스크립트 분석 도구 (1회용).

비회원 로그인의 ``pubcLogin.do`` POST body 가 ~3KB obfuscated 인데 본
라이브러리가 캡처한 JS 6개에는 ``XMLHttpRequest`` override / ``ajaxSetup``
hijack 이 0건. 즉 다른 JS (OACX UI / 동적 load) 가 body 를 변환한다.

본 도구는 그 변환 함수를 식별하기 위한 instrumentation:

- Playwright ``add_init_script`` 로 **페이지 로드 전** ``XHR.send`` /
  ``XHR.open`` / ``window.fetch`` 를 override. 호출 시점의 ``stack`` +
  ``url`` + ``data`` + ``data type`` 을 ``console.log`` 로 export.
- ``jQuery.ajaxSend`` global listener — settings.data 와 호출 stack.
- Playwright Python 측 ``page.on("console")`` 으로 받아 메모리 + 파일 dump.
- 사용자가 비회원 카카오 인증을 직접 통과시키면, 그 사이 pubcLogin POST
  의 caller frame + data 모양이 자동으로 잡힌다.

산출물: ``captures/<timestamp>/protect_dump.json`` — pubcLogin 호출
관련 ajax / xhr / fetch 이벤트 목록. PII 가능성 (RRN / 이름) 으로 본 파일은
``0o600`` 권한 + ``captures/`` (gitignored) 안.

실행::

    .venv/bin/python examples/recon_protect.py --channel chrome

라이브러리 코드 아님 — 1회용 분석. 결과는 ``docs/hometax-facts.md §16``
의 protection layer 추정에 반영.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")

# 페이지 로드 전 주입할 instrumentation JS.
# - 원본 함수 보존 + console.log("[PROTECT] " + JSON.stringify(...)) 발행.
# - pubcLogin URL 만 필터링 (다른 ajax 노이즈 제거).
_INIT_SCRIPT = r"""
(function () {
  const TARGET = "pubcLogin";
  const tag = (kind, payload) => {
    try {
      console.log("[PROTECT]" + JSON.stringify({ kind, ...payload }));
    } catch (e) {
      console.log("[PROTECT]" + JSON.stringify({
        kind, error: String(e),
      }));
    }
  };

  // 1. XMLHttpRequest.prototype.open / send override
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__protect_url = url;
    this.__protect_method = method;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (this.__protect_url && String(this.__protect_url).includes(TARGET)) {
      let bodyStr = "";
      let bodyType = typeof body;
      try {
        if (body == null) bodyStr = "";
        else if (typeof body === "string") bodyStr = body;
        else if (body instanceof FormData) {
          const parts = [];
          for (const [k, v] of body.entries()) parts.push(k + "=" + v);
          bodyStr = parts.join("&");
          bodyType = "FormData";
        } else if (body instanceof URLSearchParams) {
          bodyStr = body.toString();
          bodyType = "URLSearchParams";
        } else {
          bodyStr = String(body);
        }
      } catch (e) {
        bodyStr = "<unstringify: " + String(e) + ">";
      }
      tag("xhr.send", {
        url: this.__protect_url,
        method: this.__protect_method,
        bodyType,
        bodyLen: bodyStr.length,
        bodyPreview: bodyStr.slice(0, 400),
        bodyEnd: bodyStr.slice(-100),
        stack: new Error("trace").stack,
      });
    }
    return origSend.apply(this, arguments);
  };

  // 2. fetch override
  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (url.includes(TARGET)) {
      const body = (init && init.body) || "";
      tag("fetch", {
        url,
        method: (init && init.method) || "GET",
        bodyLen: typeof body === "string" ? body.length : -1,
        bodyPreview: typeof body === "string" ? body.slice(0, 400) : "",
        stack: new Error("trace").stack,
      });
    }
    return origFetch.apply(this, arguments);
  };

  // 3. jQuery ajaxSend (페이지 jQuery 로드 후 활성)
  document.addEventListener("DOMContentLoaded", function () {
    if (window.jQuery) {
      try {
        window.jQuery(document).ajaxSend(function (event, xhr, settings) {
          if (!settings.url || !settings.url.includes(TARGET)) return;
          const d = settings.data;
          let preview = "";
          let dType = typeof d;
          try {
            if (d == null) preview = "";
            else if (typeof d === "string") preview = d.slice(0, 400);
            else preview = JSON.stringify(d).slice(0, 400);
          } catch (e) {
            preview = "<unstringify: " + String(e) + ">";
          }
          tag("jq.ajaxSend", {
            url: settings.url,
            method: settings.type || settings.method,
            contentType: settings.contentType,
            dataType: dType,
            preview,
            stack: new Error("trace").stack,
          });
        });
      } catch (e) {
        tag("jq.ajaxSend.error", { error: String(e) });
      }
    }
  });
})();
"""


def _ts() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%dT%H-%M-%S")


def _import_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright 미설치. uv sync --extra bootstrap"
        ) from exc
    return sync_playwright


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--channel",
        default=os.environ.get("RECON_CHANNEL"),
        help="Playwright channel (예: 'chrome'). 미지정 시 번들 chromium.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="산출물 디렉토리. 기본 captures/protect-<ts>/.",
    )
    parser.add_argument(
        "--start-url",
        default="https://hometax.go.kr/",
        help=(
            "시작 URL. 기본 = 메인 포털. 비회원 deep-link 로 바로 가면 "
            "priming 이 빠져 UI 가 비어 보이므로 메인에서 출발해 사용자가 "
            "'로그인' 버튼 → '비회원 로그인' 탭으로 직접 이동한다."
        ),
    )
    args = parser.parse_args(argv)

    out_dir = args.output_dir or Path("captures") / f"protect-{_ts()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict[str, Any]] = []
    other_console: list[str] = []

    def on_console(msg: Any) -> None:
        text = msg.text
        if text.startswith("[PROTECT]"):
            try:
                payload = json.loads(text[len("[PROTECT]"):])
                events.append(payload)
                kind = payload.get("kind", "?")
                print(
                    f"[recon-protect] {kind} bodyLen="
                    f"{payload.get('bodyLen', '?')}",
                    file=sys.stderr, flush=True,
                )
            except json.JSONDecodeError:
                events.append({"kind": "parse_error", "raw": text[:200]})
        else:
            # 페이지 자체 콘솔 (디버그 시 유용)
            if len(other_console) < 200:
                other_console.append(text[:300])

    sync_playwright = _import_playwright()
    print(
        "[recon-protect] 메인 포털을 띄웁니다.\n"
        "  → '로그인' 버튼 → '비회원 로그인' 탭 → 이름/주민번호 입력 →\n"
        "    카카오 선택 → 폰 승인 → 메인 진입까지 직접 진행해주세요.\n"
        "  NTS_REQUEST_SYSTEM_CODE_P cookie 감지 시 자동 종료 (최대 10분).",
        file=sys.stderr, flush=True,
    )
    import time
    cookies: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        launch_kwargs: dict[str, Any] = {"headless": False}
        if args.channel:
            launch_kwargs["channel"] = args.channel
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(locale="ko-KR")
        context.add_init_script(_INIT_SCRIPT)

        page = context.new_page()
        page.on("console", on_console)

        # 메인에서 시작 — 사용자가 직접 '로그인' → '비회원' 탭으로 navigate.
        # deep-link 직진은 priming 빠져 UI 가 비어 보인다.
        page.goto(args.start_url, wait_until="load")

        # 사용자가 폰 인증 통과 → NTS_REQUEST_SYSTEM_CODE_P cookie 발급 감지.
        # pubcLogin 호출 직후 발급되므로 instrumentation 이벤트는 이미 모임.
        deadline = time.monotonic() + 600.0
        login_done = False
        while time.monotonic() < deadline:
            names = {c["name"] for c in context.cookies()}
            if "NTS_REQUEST_SYSTEM_CODE_P" in names:
                # cookies 갱신 + SPA 후속 호출까지 약간 대기
                time.sleep(3)
                login_done = True
                break
            time.sleep(1)
        if not login_done:
            print(
                "[recon-protect] 10분 timeout — 로그인 미완료 / 이벤트만 수집.",
                file=sys.stderr, flush=True,
            )

        cookies = context.cookies()
        context.close()
        browser.close()

    # 결과 dump
    dump_path = out_dir / "protect_dump.json"
    dump_path.write_text(
        json.dumps(
            {
                "events": events,
                "other_console_sample": other_console[:50],
                "cookies": cookies,
                "ts": _ts(),
                "start_url": args.start_url,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(dump_path, 0o600)
    except OSError:
        pass

    n = len(events)
    print(
        f"\n[recon-protect] {n}개 이벤트 캡처 → {dump_path}\n"
        "  jq '.events[] | {kind, url, bodyLen, bodyType, stack}' "
        f"{dump_path}",
        file=sys.stderr, flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
