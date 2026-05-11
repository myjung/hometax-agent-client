"""ClipReport PDF export (``services/_clipreport.py``) 분기 회귀.

라이브 호출 안 함 — dummy session 으로 found / empty / failed 분기 검증.
"""

from __future__ import annotations

from typing import Any

import pytest

from hometax_client.services._clipreport import (
    ClipReportResult,
    export_pdf_from_html,
)


class _DummyResp:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.content = content


class _ScriptedSession:
    """미리 정의된 응답을 차례로 반환. POST 호출만 기록."""

    def __init__(self, responses: list[_DummyResp]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kw: Any) -> _DummyResp:
        self.calls.append({"url": url, **kw})
        if not self._responses:
            raise AssertionError(
                f"unexpected extra POST: {url} {kw.get('data')}"
            )
        return self._responses.pop(0)


_HTML_WITH_KEY = (
    "<html><script>"
    "var reportkey = JSON.parse(\"{'uid':'TESTKEY123','foo':'bar'}\");"
    "</script></html>"
)
_HTML_NO_KEY = "<html><body>자료가 없습니다.</body></html>"


def _r03(count: int, end: bool) -> _DummyResp:
    text = (
        f"({{'uid':'TESTKEY123','is_s':false,"
        f"'count':{count},'endReport':{'true' if end else 'false'},"
        f"'status':true}})"
    )
    return _DummyResp(text=text)


def _r09_pdf() -> _DummyResp:
    return _DummyResp(content=b"%PDF-1.4\n<binary...>")


def _r09_not_pdf() -> _DummyResp:
    return _DummyResp(content=b"<html>error</html>")


def test_empty_when_reportkey_missing() -> None:
    sess = _ScriptedSession([])
    result = export_pdf_from_html(sess, _HTML_NO_KEY)
    assert result.status == "empty"
    assert result.pdf is None
    assert result.report_key is None
    assert result.page_count == 0
    assert sess.calls == []  # R03/R09 호출 안 함


def test_found_path() -> None:
    """1회 R03 polling (endReport=true, count=3) + 1회 R09 (PDF) → found."""
    sess = _ScriptedSession([
        _r03(count=3, end=True),
        _r09_pdf(),
    ])
    result = export_pdf_from_html(
        sess, _HTML_WITH_KEY, file_name="x.pdf",
    )
    assert result.status == "found"
    assert result.pdf is not None
    assert result.pdf.startswith(b"%PDF")
    assert result.page_count == 3
    assert result.report_key == "TESTKEY123"
    # R03 + R09 = 2 calls
    assert len(sess.calls) == 2
    assert sess.calls[0]["data"]["ClipID"] == "R03"
    assert sess.calls[1]["data"]["ClipID"] == "R09"


def test_empty_when_page_count_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """R03 polling 이 끝까지 count=0 이면 empty (R09 호출 안 함)."""
    # poll_max 줄여서 테스트 빠르게
    from hometax_client.services import _clipreport as cr

    real_lookup = cr.facts.lookup

    def _fake_lookup(*path: str) -> Any:
        if path == ("services", "clipreport", "page_count_poll_max"):
            return 2
        if path == ("services", "clipreport", "page_count_poll_interval_sec"):
            return 0.0
        return real_lookup(*path)

    monkeypatch.setattr(cr.facts, "lookup", _fake_lookup)

    sess = _ScriptedSession([
        _r03(count=0, end=False),
        _r03(count=0, end=False),
    ])
    result = export_pdf_from_html(sess, _HTML_WITH_KEY)
    assert result.status == "empty"
    assert result.page_count == 0
    assert result.report_key == "TESTKEY123"
    # R03 만 2번, R09 호출 없음
    assert len(sess.calls) == 2
    assert all(c["data"]["ClipID"] == "R03" for c in sess.calls)


def test_empty_when_r09_not_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """R09 가 모든 시도에서 PDF 아님 → empty."""
    from hometax_client.services import _clipreport as cr

    real_lookup = cr.facts.lookup

    def _fake_lookup(*path: str) -> Any:
        if path == ("services", "clipreport", "pdf_export_attempts"):
            return 2
        if path == ("services", "clipreport", "page_count_poll_interval_sec"):
            return 0.0
        return real_lookup(*path)

    monkeypatch.setattr(cr.facts, "lookup", _fake_lookup)

    sess = _ScriptedSession([
        _r03(count=3, end=True),
        _r09_not_pdf(),
        _r09_not_pdf(),
    ])
    result = export_pdf_from_html(sess, _HTML_WITH_KEY)
    assert result.status == "empty"
    assert result.pdf is None
    assert result.page_count == 3  # page count 는 확보됐는데 PDF 만 미발급


def test_failed_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """R03 가 HTTP 500 응답하면 failed (empty 가 아님)."""
    sess = _ScriptedSession([
        _DummyResp(status_code=500, text="server error"),
    ])
    result = export_pdf_from_html(sess, _HTML_WITH_KEY)
    assert result.status == "failed"
    assert "R03" in result.message or "500" in result.message


def test_result_dataclass_fields() -> None:
    sess = _ScriptedSession([])
    result = export_pdf_from_html(sess, _HTML_NO_KEY)
    assert isinstance(result, ClipReportResult)
    assert hasattr(result, "raw_html")  # 디버깅 위해 보존
