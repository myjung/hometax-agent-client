"""HAR reader — ``iter_wq_actions`` 회귀."""

from __future__ import annotations

import base64
import json
from pathlib import Path


from hometax_client.bootstrap import WqActionCall, iter_wq_actions


def _entry(
    *,
    url: str,
    method: str = "POST",
    request_text: str,
    response_text: str,
    status: int = 200,
    started_at: str = "2026-05-11T10:00:00.000Z",
    encode_base64: bool = True,
) -> dict:
    """HAR entry 한 개 생성. ``encode_base64=True`` 면 본문을 base64 로."""
    def encode(text: str) -> dict:
        if encode_base64:
            return {
                "text": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                "encoding": "base64",
            }
        return {"text": text}

    return {
        "startedDateTime": started_at,
        "request": {
            "method": method,
            "url": url,
            "postData": {
                "mimeType": "application/json",
                **encode(request_text),
            },
        },
        "response": {
            "status": status,
            "content": {
                "mimeType": "application/json",
                **encode(response_text),
            },
        },
    }


def _har(entries: list[dict]) -> dict:
    return {"log": {"version": "1.2", "entries": entries}}


def _write(tmp_path: Path, har: dict) -> Path:
    p = tmp_path / "trace.har"
    p.write_text(json.dumps(har, ensure_ascii=False), encoding="utf-8")
    return p


# ----------------------------------------------------------------- #
# 핵심 케이스                                                         #
# ----------------------------------------------------------------- #


def test_iter_wq_actions_extracts_action_and_screen(tmp_path: Path) -> None:
    request_body = {"attrYr": "2024", "txprDscmNo": "0000000000"}
    response_body = {"resultMsg": "정상", "agitxRtnInqrDVOList": []}
    # 홈택스 와이어 패턴: JSON body + HMAC suffix concat
    request_text = json.dumps(request_body) + "ABCDEF0123"
    response_text = json.dumps(response_body)

    har = _har([
        _entry(
            url=(
                "https://hometax.go.kr/wqAction.do"
                "?actionId=ATXPPZXA001R02"
                "&screenId=UTXPPZXA01"
                "&popupYn=false"
            ),
            request_text=request_text,
            response_text=response_text,
        ),
    ])
    calls = list(iter_wq_actions(_write(tmp_path, har)))

    assert len(calls) == 1
    c = calls[0]
    assert isinstance(c, WqActionCall)
    assert c.action_id == "ATXPPZXA001R02"
    assert c.screen_id == "UTXPPZXA01"
    assert c.host == "hometax.go.kr"
    assert c.method == "POST"
    assert c.status == 200
    assert c.request_body == request_body
    # HMAC suffix 는 request_text 에는 남고 request_body 에서는 제거됨
    assert c.request_text.endswith("ABCDEF0123")
    assert c.response_body == response_body


def test_iter_wq_actions_skips_non_wq_entries(tmp_path: Path) -> None:
    har = _har([
        _entry(
            url="https://hometax.go.kr/permission.do?screenId=X",
            request_text="{}",
            response_text="{}",
        ),
        _entry(
            url=(
                "https://teht.hometax.go.kr/wqAction.do"
                "?actionId=ATEHT01"
            ),
            request_text="{}",
            response_text="{}",
        ),
        _entry(
            url="https://hometax.go.kr/token.do",
            request_text="{}",
            response_text="{}",
        ),
    ])

    calls = list(iter_wq_actions(_write(tmp_path, har)))
    assert len(calls) == 1
    assert calls[0].host == "teht.hometax.go.kr"
    assert calls[0].action_id == "ATEHT01"
    assert calls[0].screen_id is None


def test_iter_wq_actions_handles_plain_text_bodies(tmp_path: Path) -> None:
    """``encoding=base64`` 가 없으면 text 그대로 사용."""
    har = _har([
        _entry(
            url="https://hometax.go.kr/wqAction.do?actionId=A1",
            request_text='{"a":1}suffix',
            response_text='{"ok":true}',
            encode_base64=False,
        ),
    ])
    c = list(iter_wq_actions(_write(tmp_path, har)))[0]
    assert c.request_body == {"a": 1}
    assert c.response_body == {"ok": True}


def test_iter_wq_actions_returns_empty_dict_on_parse_failure(
    tmp_path: Path,
) -> None:
    har = _har([
        _entry(
            url="https://hometax.go.kr/wqAction.do?actionId=A1",
            request_text="not json at all",
            response_text="also not json",
            encode_base64=False,
        ),
    ])
    c = list(iter_wq_actions(_write(tmp_path, har)))[0]
    assert c.request_body == {}
    assert c.response_body == {}
    assert c.request_text == "not json at all"
    assert c.response_text == "also not json"


def test_iter_wq_actions_empty_har(tmp_path: Path) -> None:
    assert list(iter_wq_actions(_write(tmp_path, _har([])))) == []


def test_iter_wq_actions_missing_entries_key(tmp_path: Path) -> None:
    p = tmp_path / "trace.har"
    p.write_text(json.dumps({"log": {}}), encoding="utf-8")
    assert list(iter_wq_actions(p)) == []
