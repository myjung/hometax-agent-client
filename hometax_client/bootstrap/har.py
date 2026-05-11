"""HAR 파일에서 홈택스 RPC 호출 (wqAction / jsonAction) 추출 reader.

``bootstrap.CaptureSession`` 이 dump 한 ``trace.har`` (또는 동일 포맷의
외부 HAR) 안에서 홈택스 RPC 호출만 골라 ``WqActionCall`` 로 yield 한다.

지원 endpoint:
- ``wqAction.do`` — 데스크탑 ``hometax.go.kr`` / ``teht`` / ``tewe`` / ``sesw``
- ``jsonAction.do`` — 모바일 손택스 ``mob.hometax.go.kr`` / ``mob.tbht`` 등.
  body 가 ``datas=<URL-encoded JSON>&m=`` 형식이라 디코드 후 JSON 추출.

에이전트가 새 서비스를 구현하기 전 캡처를 균일하게 읽기 위한 진입점.
매 분석마다 base64 디코드 / querystring 파싱 / HMAC suffix 분리 코드를
다시 짤 필요가 없다.

본 모듈은 Playwright 를 import 하지 않는다 — HAR 은 일반 JSON 이므로
``[bootstrap]`` extras 없이도 동작한다.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

__all__ = [
    "WqActionCall",
    "ActionSchema",
    "iter_wq_actions",
    "iter_action_schemas",
]


@dataclass(frozen=True)
class WqActionCall:
    """HAR 한 entry 의 ``wqAction.do`` 호출.

    필드:
        action_id: querystring ``actionId``. 빠지면 빈 문자열.
        screen_id: querystring ``screenId``. 없으면 ``None``.
        host: 요청 호스트 (예: ``hometax.go.kr``, ``teht.hometax.go.kr``).
        url: 전체 URL (querystring 포함).
        method: HTTP 메서드 (대개 ``POST``).
        status: 응답 상태 코드.
        started_at: HAR ``startedDateTime`` (ISO 8601).
        request_text: 디코드된 request body 전체 (JSON + HMAC suffix concat).
        request_body: request body 의 JSON 부분 (suffix 제외). 파싱 실패 시 ``{}``.
        response_text: 디코드된 response body 전체.
        response_body: response body JSON. 파싱 실패 시 ``{}``.
    """

    action_id: str
    screen_id: str | None
    host: str
    url: str
    method: str
    status: int
    started_at: str
    request_text: str
    request_body: dict[str, Any] = field(default_factory=dict)
    response_text: str = ""
    response_body: dict[str, Any] = field(default_factory=dict)


def iter_wq_actions(har_path: str | Path) -> Iterator[WqActionCall]:
    """HAR 안에서 홈택스 RPC 호출 (wqAction.do / jsonAction.do) 순차 yield.

    호출 예::

        from hometax_client.bootstrap import iter_wq_actions

        for call in iter_wq_actions("captures/2026-05-11T10-15-00/trace.har"):
            print(call.action_id, call.screen_id, call.host)
            if call.action_id == "ATXPPBAA001R16":
                print(call.request_body, call.response_body.keys())
    """
    har = json.loads(Path(har_path).read_text(encoding="utf-8"))
    entries = har.get("log", {}).get("entries", []) or []
    for entry in entries:
        request = entry.get("request") or {}
        url = request.get("url") or ""
        is_wq = "wqAction.do" in url
        is_json = "jsonAction.do" in url
        if not (is_wq or is_json):
            continue

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        action_id = (qs.get("actionId") or [""])[0]
        # 페이지 진입 (UTBxxxF001 등) 은 skip — `U` prefix.
        # 액션은 `AT*`, `AW*`, `AS*`, `A1` (테스트) 등 `A`/`a` prefix 또는 빈 ID.
        if action_id and action_id[0].upper() == "U":
            continue
        screen_id_list = qs.get("screenId") or qs.get("jspName")
        screen_id = screen_id_list[0] if screen_id_list else None
        host = parsed.netloc

        response = entry.get("response") or {}
        request_text = _decode_body(request.get("postData") or {})
        response_text = _decode_body(response.get("content") or {})

        # body 파싱 분기: wqAction = JSON+HMAC suffix, jsonAction = datas=<JSON>&m=
        if is_json:
            request_body = _parse_datas_form(request_text)
        else:
            request_body = _parse_signed_json(request_text)

        yield WqActionCall(
            action_id=action_id,
            screen_id=screen_id,
            host=host,
            url=url,
            method=request.get("method") or "",
            status=int(response.get("status") or 0),
            started_at=entry.get("startedDateTime") or "",
            request_text=request_text,
            request_body=request_body,
            response_text=response_text,
            response_body=_parse_json(response_text),
        )


@dataclass(frozen=True)
class ActionSchema:
    """홈택스 페이지 JS 안에 정의된 한 action 의 입출력 스키마.

    페이지 JS (``_wpack_/ui/.../UTxxx.js``) 안의 ``scwin.action`` dict 또는
    ``action : {id, indatalist, outdatalist}`` 객체 리터럴에서 추출.

    필드:
        action_id: ``"ATXPPBAA001R16"`` 등.
        input_targets: indatalist 의 ``des`` 값들 (request body 의 top-level key).
            예: ``["ErinCfrSbjsInqrSVO"]``. body 구조는 ``{<des>: {...input fields...}}``.
        input_sources: indatalist 의 ``src`` 값들 (페이지의 어느 element 에서 가져옴).
            예: ``["search[@id='s1']"]``. 페이지 XML 의 search element 정의를 보면
            그 안의 ``<w2:key>`` 들이 실제 필드 (attrYr 등).
        output_targets: outdatalist 의 ``des`` 값들 (페이지의 어느 element 에 저장).
        output_sources: outdatalist 의 ``src`` 값들 + ``list`` 타입 추적 (응답 리스트 키).
            예: ``["dscRslInqrDVOList", "agitxRtnInqrDVOList"]``.
        page_url: 추출 소스 페이지 JS URL.
    """

    action_id: str
    input_targets: tuple[str, ...]
    input_sources: tuple[str, ...]
    output_targets: tuple[str, ...]
    output_sources: tuple[str, ...]
    page_url: str


def iter_action_schemas(har_path: str | Path) -> Iterator[ActionSchema]:
    """HAR 의 ``_wpack_/...js`` 응답에서 페이지 안의 모든 action 정의 추출.

    페이지 JS 의 ``action : {id : "...", indatalist : [...], outdatalist : [...]}``
    object literal 을 정규식으로 찾는다. WebSquare framework 의 표준 패턴이라
    홈택스 화면 거의 모두에 적용.

    중복 (같은 actionId 가 여러 페이지에 정의) 도 그대로 yield. 호출자가
    원하는 대로 dedupe.

    호출 예::

        from hometax_client.bootstrap import iter_action_schemas

        for sch in iter_action_schemas("captures/.../trace.har"):
            print(sch.action_id, sch.input_targets, sch.output_sources)
    """
    import re

    har = json.loads(Path(har_path).read_text(encoding="utf-8"))
    entries = har.get("log", {}).get("entries", []) or []

    # action : { id : "AT...", ..., indatalist : [...], outdatalist : [...] }
    # 정규식은 object literal 한 개 정확히 잡기 어려워 단계적 파싱:
    # 1) "id : '<actionId>'" 위치 모두 찾음
    # 2) 각 위치 주변 균형 잡힌 {...} 추출 → indatalist/outdatalist 파싱
    id_pat = re.compile(
        r'''id\s*:\s*['"]((?:AT|AS|AW|AC)[A-Z0-9_]+)['"]''',
    )
    des_pat = re.compile(r'''des\s*:\s*['"]([^'"]+)['"]''')
    src_pat = re.compile(r'''src\s*:\s*['"]([^'"]+)['"]''')

    for entry in entries:
        request = entry.get("request") or {}
        url = request.get("url") or ""
        # 페이지 HTML / JS 본문 모두 scan (data:url 같은 비표준 skip)
        if not url.startswith("http"):
            continue
        if request.get("method") and request["method"].upper() != "GET":
            continue
        body = _decode_body((entry.get("response") or {}).get("content") or {})
        # action 정의 안 들어있을 게 명백한 응답 skip (속도)
        if not body or "indatalist" not in body:
            continue
        for id_match in id_pat.finditer(body):
            action_id = id_match.group(1)
            # action 객체 본문 추출 — id_match 앞쪽 `{` 부터 균형 brace 까지
            brace_start = body.rfind("{", 0, id_match.start())
            if brace_start < 0:
                continue
            depth = 0
            brace_end = brace_start
            for i in range(brace_start, len(body)):
                c = body[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        brace_end = i + 1
                        break
            chunk = body[brace_start:brace_end]
            # indatalist / outdatalist sub-block 분리
            in_block, out_block = _split_action_blocks(chunk)
            in_des = tuple(des_pat.findall(in_block))
            in_src = tuple(src_pat.findall(in_block))
            out_des = tuple(des_pat.findall(out_block))
            out_src = tuple(src_pat.findall(out_block))
            yield ActionSchema(
                action_id=action_id,
                input_targets=in_des,
                input_sources=in_src,
                output_targets=out_des,
                output_sources=out_src,
                page_url=url,
            )


def _split_action_blocks(chunk: str) -> tuple[str, str]:
    """action 객체 chunk 에서 indatalist / outdatalist sub-block 추출."""
    def _slice(keyword: str) -> str:
        idx = chunk.find(keyword)
        if idx < 0:
            return ""
        start = chunk.find("[", idx)
        if start < 0:
            return ""
        depth = 0
        for i in range(start, len(chunk)):
            c = chunk[i]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return chunk[start:i + 1]
        return ""

    return _slice("indatalist"), _slice("outdatalist")


def _decode_body(part: dict[str, Any]) -> str:
    """HAR ``postData`` / ``response.content`` 한 조각을 utf-8 문자열로 디코드.

    ``record_har_content="embed"`` 면 본문이 base64 인코딩되어 있다.
    Playwright 기본은 base64. base64 가 아니면 ``text`` 그대로.
    """
    text = part.get("text") or ""
    if not text:
        return ""
    if part.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            return ""
    return text


def _parse_signed_json(text: str) -> dict[str, Any]:
    """JSON body + HMAC suffix concat 에서 JSON 부분만 추출.

    홈택스 request body 는 ``json.dumps(body) + nts_encrypt(...)`` 형태로
    concat 되어 끝에 알파숫자 HMAC suffix 가 붙는다. ``JSONDecoder.raw_decode``
    가 첫 JSON 객체만 정확히 파싱한다.
    """
    if not text:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _parse_datas_form(text: str) -> dict[str, Any]:
    """모바일 jsonAction body 의 ``datas=<URL-encoded JSON>&m=...`` 파싱.

    body 끝에 추가 form 필드가 붙는 경우도 있는데 ``datas`` 만 추출.
    파싱 실패 시 ``{}``.
    """
    if not text or "datas=" not in text:
        return {}
    after = text.split("datas=", 1)[1]
    # &m= 또는 & 로 datas 값 끝남
    end = len(after)
    for sep in ("&m=", "&"):
        idx = after.find(sep)
        if idx >= 0:
            end = min(end, idx)
    datas_raw = after[:end]
    try:
        obj = json.loads(unquote(datas_raw))
    except (ValueError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _parse_json(text: str) -> dict[str, Any]:
    """순수 JSON 응답 파싱. 실패 시 ``{}``."""
    if not text:
        return {}
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}
