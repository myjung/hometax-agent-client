"""ClipReport4 PDF export — ``clipreport.do`` 응답 HTML 에서 PDF bytes 발급.

홈택스의 미리보기 HTML 응답에는 ``var reportkey = ...{'uid':'<key>'}...``
형태의 토큰이 박혀 있다. 이 토큰을 두 단계 후속 호출로 PDF 로 변환::

    1. ``POST /serp/ClipReport4/Clip.jsp`` (``ClipID=R03``) — page count
       polling. 응답이 ``count:N, endReport:true`` 가 될 때까지 반복.
    2. ``POST /serp/ClipReport4/Clip.jsp`` (``ClipID=R09``) — PDF export.
       성공 응답은 ``%PDF`` magic header 로 시작하는 bytes.

라이브 검증 2026-05-11 — 비회원 OACX 세션 + 신고안내문 5페이지 200KB PDF.
호출 host 는 ``sesw.hometax.go.kr`` (separate origin, cookies 호환 확인).

라이브러리 정책상 데이터 dict / bytes 반환만 — 디스크 저장은 호출자
(워크플로 계층) 책임. ``ClipReportResult`` 의 ``status`` 로 정상 / 데이터
없음 / 실패 를 명확히 구분 (``docs/painpoints.md`` 의 "2025년 자료 없음 →
PDF export 빈 응답" 케이스 분기).
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

from .. import facts
from ..exceptions import UnknownResponseError

CLIPREPORT_HOST = "sesw.hometax.go.kr"
CLIPREPORT_REFERER = f"https://{CLIPREPORT_HOST}/serp/clipreport.do"

_REPORT_KEY_RE = re.compile(r"var reportkey = .*?'uid':'([^']+)'", re.S)
_COUNT_RE = re.compile(r"['\"]?count['\"]?\s*:\s*(\d+)")
_END_REPORT_RE = re.compile(r"['\"]?endReport['\"]?\s*:\s*true", re.I)


Status = Literal["found", "empty", "failed"]


@dataclass
class ClipReportResult:
    """ClipReport PDF export 결과.

    ``status`` 로 분기:

    - ``"found"``: ``pdf`` 가 PDF bytes (``%PDF`` 로 시작). ``page_count`` 채워짐.
    - ``"empty"``: HTML 에 ``reportkey`` 없음 또는 page count 0 / R09 가 PDF
      가 아닌 응답. 사용자 계정의 해당 조회에 자료가 없는 정상 케이스.
    - ``"failed"``: HTTP 4xx/5xx 등 wire 실패. ``message`` 에 상세.

    ``raw_html`` 은 디버깅용 — empty / failed 케이스 진단에 사용.
    """

    status: Status
    pdf: bytes | None
    page_count: int
    report_key: str | None
    message: str
    raw_html: str


def export_pdf_from_html(
    session: Any,
    report_html: str,
    *,
    file_name: str = "report.pdf",
) -> ClipReportResult:
    """미리보기 HTML 에서 PDF bytes 발급. 데이터 없음 / 실패 분기 포함.

    Args:
        session: ``curl_cffi`` 또는 ``requests`` Session — ``.post(url, data,
            headers, timeout)`` 인터페이스만 사용.
        report_html: ``clipreport.do`` 응답 본문.
        file_name: R09 export 옵션의 ``name`` 에 들어가는 파일명 hint.
            서버는 이 이름의 PDF bytes 만 반환하고 실제 파일은 만들지 않는다.

    Returns:
        ``ClipReportResult``. ``status="found"`` 인 경우 ``pdf`` 가 bytes.
    """
    match = _REPORT_KEY_RE.search(report_html)
    if not match:
        return ClipReportResult(
            status="empty",
            pdf=None,
            page_count=0,
            report_key=None,
            message="reportkey 미발견 — 조회 자료가 없는 케이스 추정",
            raw_html=report_html,
        )
    report_key = match.group(1)

    poll_max = int(facts.lookup(
        "services", "clipreport", "page_count_poll_max",
    ))
    poll_interval = float(facts.lookup(
        "services", "clipreport", "page_count_poll_interval_sec",
    ))

    try:
        page_count = _poll_page_count(
            session, report_key,
            poll_max=poll_max, poll_interval=poll_interval,
        )
    except _ClipWireError as exc:
        return ClipReportResult(
            status="failed",
            pdf=None,
            page_count=0,
            report_key=report_key,
            message=f"R03 page count polling 실패: {exc}",
            raw_html=report_html,
        )

    if page_count == 0:
        return ClipReportResult(
            status="empty",
            pdf=None,
            page_count=0,
            report_key=report_key,
            message="page count 0 — 조회 자료가 없는 케이스 추정",
            raw_html=report_html,
        )

    pdf_attempts = int(facts.lookup(
        "services", "clipreport", "pdf_export_attempts",
    ))
    try:
        pdf = _export_r09(
            session, report_key,
            page_count=page_count,
            file_name=file_name,
            attempts=pdf_attempts,
            interval=poll_interval,
        )
    except _ClipWireError as exc:
        return ClipReportResult(
            status="failed",
            pdf=None,
            page_count=page_count,
            report_key=report_key,
            message=f"R09 PDF export 실패: {exc}",
            raw_html=report_html,
        )

    if pdf is None:
        return ClipReportResult(
            status="empty",
            pdf=None,
            page_count=page_count,
            report_key=report_key,
            message="R09 응답이 PDF 가 아님 — 자료 없음 추정",
            raw_html=report_html,
        )

    return ClipReportResult(
        status="found",
        pdf=pdf,
        page_count=page_count,
        report_key=report_key,
        message=f"PDF {page_count}페이지 {len(pdf)} bytes",
        raw_html=report_html,
    )


# ------------------------------------------------------------------ #
# 내부                                                                #
# ------------------------------------------------------------------ #


class _ClipWireError(Exception):
    """HTTP 4xx/5xx 같은 진짜 wire 실패. 데이터 없음 (empty) 과 구분."""


def _clip_url() -> str:
    path = facts.lookup("services", "clipreport", "clip_jsp_path")
    return f"https://{CLIPREPORT_HOST}{path}"


def _base_headers() -> dict[str, str]:
    return {
        "Origin": f"https://{CLIPREPORT_HOST}",
        "Referer": CLIPREPORT_REFERER,
        "User-Agent": "Mozilla/5.0",
    }


def _poll_page_count(
    session: Any,
    report_key: str,
    *,
    poll_max: int,
    poll_interval: float,
) -> int:
    r03_id = facts.lookup("services", "clipreport", "r03_clip_id")
    url = _clip_url()
    headers = {
        **_base_headers(),
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
    }
    max_count = 0
    for attempt in range(poll_max):
        resp = session.post(
            url,
            data={
                "ClipID": r03_id,
                "uid": report_key,
                "clipUID": report_key,
                "s_time": f"t{attempt}",
            },
            headers=headers,
            timeout=20,
        )
        if resp.status_code >= 400:
            raise _ClipWireError(f"HTTP {resp.status_code}")
        text = resp.text
        m = _COUNT_RE.search(text)
        if m:
            max_count = max(max_count, int(m.group(1)))
        if _END_REPORT_RE.search(text) and max_count > 0:
            return max_count
        if attempt < poll_max - 1:
            time.sleep(poll_interval)
    return max_count


def _export_r09(
    session: Any,
    report_key: str,
    *,
    page_count: int,
    file_name: str,
    attempts: int,
    interval: float,
) -> bytes | None:
    r09_id = facts.lookup("services", "clipreport", "r09_clip_id")
    url = _clip_url()
    export_name = base64.b64encode(
        quote(file_name).encode("utf-8"),
    ).decode("ascii")
    export_option = {
        "name": export_name,
        "pageType": 1,
        "startNum": 1,
        "endNum": page_count,
        "exportType": 2,
        "option": {
            "isSplite": False,
            "spliteValue": 1,
            "fileNames": [],
            "userpw": "",
            "textToImage": False,
            "importOriginImage": False,
            "removeHyperlink": False,
            "splitPage": 0,
        },
    }
    headers = {
        **_base_headers(),
        "Accept": "application/pdf,*/*",
    }
    for attempt in range(attempts):
        resp = session.post(
            url,
            data={
                "ClipID": r09_id,
                "uid": report_key,
                "clipUID": report_key,
                "path": "/serp/ClipReport4",
                "optionValue": json.dumps(
                    export_option, ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "exportN": quote(export_name),
                "exportType": "2",
                "isSmartPhone": "false",
                "is_ie": "true",
            },
            headers=headers,
            timeout=60,
        )
        if resp.status_code >= 400:
            raise _ClipWireError(f"HTTP {resp.status_code}")
        content = resp.content
        if content.startswith(b"%PDF"):
            return content
        if attempt < attempts - 1:
            time.sleep(interval)
    return None


__all__ = ["ClipReportResult", "export_pdf_from_html"]


def _self_check() -> None:
    """import 시점에 facts 가 다 채워졌는지 가벼운 검증."""
    for key in (
        "host", "endpoint", "clip_jsp_path",
        "r03_clip_id", "r09_clip_id",
        "page_count_poll_max", "page_count_poll_interval_sec",
        "pdf_export_attempts",
    ):
        try:
            facts.lookup("services", "clipreport", key)
        except Exception as exc:
            raise UnknownResponseError(
                f"services.clipreport.{key} 가 facts 에 없음 — "
                f"facts/current.toml 갱신 필요"
            ) from exc
