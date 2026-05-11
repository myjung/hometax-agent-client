"""HAR 파일에서 ``wqAction.do`` 호출만 추출하는 reader.

``bootstrap.CaptureSession`` 이 dump 한 ``trace.har`` (또는 동일 포맷의
외부 HAR) 안에서 홈택스 RPC 호출만 골라 ``WqActionCall`` 로 yield 한다.

에이전트가 새 서비스를 구현하기 전 캡처를 균일하게 읽기 위한 진입점.
매 분석마다 base64 디코드 / querystring 파싱 / HMAC suffix 분리 코드를
다시 짤 필요가 없다.

본 모듈은 Playwright 를 import 하지 않는다 — HAR 은 일반 JSON 이므로
``[bootstrap]`` extras 없이도 동작한다. 단 import 경로는 의도적으로
``hometax_client.bootstrap`` 하위에 둔다 (캡처 산출물 분석 도구이므로).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

__all__ = ["WqActionCall", "iter_wq_actions"]


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
    """HAR 안에서 ``wqAction.do`` 호출만 순차 yield.

    호출 예::

        from hometax_client.bootstrap import iter_wq_actions

        for call in iter_wq_actions("captures/2026-05-11T10-15-00/trace.har"):
            print(call.action_id, call.screen_id, call.host)
            if call.action_id == "ATXPP...":
                print(call.response_body.keys())
    """
    har = json.loads(Path(har_path).read_text(encoding="utf-8"))
    entries = har.get("log", {}).get("entries", []) or []
    for entry in entries:
        request = entry.get("request") or {}
        url = request.get("url") or ""
        if "wqAction.do" not in url:
            continue

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        action_id = (qs.get("actionId") or [""])[0]
        screen_id_list = qs.get("screenId")
        screen_id = screen_id_list[0] if screen_id_list else None
        host = parsed.netloc

        response = entry.get("response") or {}
        request_text = _decode_body(request.get("postData") or {})
        response_text = _decode_body(response.get("content") or {})

        yield WqActionCall(
            action_id=action_id,
            screen_id=screen_id,
            host=host,
            url=url,
            method=request.get("method") or "",
            status=int(response.get("status") or 0),
            started_at=entry.get("startedDateTime") or "",
            request_text=request_text,
            request_body=_parse_signed_json(request_text),
            response_text=response_text,
            response_body=_parse_json(response_text),
        )


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


def _parse_json(text: str) -> dict[str, Any]:
    """순수 JSON 응답 파싱. 실패 시 ``{}``."""
    if not text:
        return {}
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}
