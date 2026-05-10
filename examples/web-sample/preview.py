"""의존성 없이 web sample 페이지만 미리보는 stub 서버.

``hometax_client`` 라이브러리를 import 하지 않고 stdlib 만으로 동작한다.
실제 홈택스 호출은 하지 않으며 ``/api/lookup`` 은 mock 데이터를 반환해
UI 흐름(폼 → 결과 표시)을 그대로 확인할 수 있다.

실행::

    python3 examples/web-sample/preview.py

브라우저에서 ``http://127.0.0.1:8787/`` 접속.

실제 홈택스 호출이 필요하면 ``server.py`` 를 사용 (라이브러리 설치 필요).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

KST = timezone(timedelta(hours=9))
HERE = Path(__file__).resolve().parent
INDEX_HTML_PATH = HERE / "index.html"


def default_year() -> int:
    return datetime.now(KST).year - 1


def mock_lookup(year: int) -> dict[str, Any]:
    """실제 호출 없이 응답 형식만 보여주는 mock 데이터."""
    return {
        "user_name": "홍길동 (mock)",
        "tin": "1234567890",
        "attr_year": year,
        "inquiries": {
            "income_statements": {
                "status": "ok",
                "count": 2,
                "items": [
                    {
                        "kind": "근로소득지급명세서",
                        "payer": "주식회사 가나다 (mock)",
                        "period": f"{year}01~{year}12",
                    },
                    {
                        "kind": "사업소득 간이지급명세서",
                        "payer": "주식회사 라마바 (mock)",
                        "period": f"{year}03~{year}11",
                    },
                ],
            },
            "tax_filings": {
                "status": "ok",
                "count": 1,
                "items": [
                    {
                        "kind": "종합소득세 정기확정신고서 (mock)",
                        "date": f"{year + 1}0531",
                        "computed_tax": 1_234_567,
                    },
                ],
            },
            "filing_help": {
                "status": "ok",
                "filing_kind": "단순경비율 (mock)",
                "filing_kind_code": "S",
            },
            "address": {
                "status": "found",
                "road_address": "서울특별시 종로구 사직로 8길 (mock)",
                "lot_address": "서울특별시 종로구 적선동 (mock)",
                "zip_code": "03044",
            },
        },
        "elapsed_sec": 0.0,
    }


class PreviewHandler(BaseHTTPRequestHandler):
    """라이브러리 없이 동작하는 stub 핸들러."""

    server_version = "HometaxSampleUI-Preview/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        if path == "/":
            self._send(
                HTTPStatus.OK,
                "text/html; charset=utf-8",
                INDEX_HTML_PATH.read_bytes(),
            )
        elif path == "/api/health":
            self._json(HTTPStatus.OK, {
                "preview": True,
                "env": {
                    "has_cookies": False,
                    "has_user_id": False,
                    "has_password": False,
                    "has_rrn": False,
                    "default_year": default_year(),
                },
            })
        else:
            self._json(HTTPStatus.NOT_FOUND, {"message": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        if path == "/api/lookup":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                year = int(payload.get("year") or default_year())
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {
                    "error_type": "ValidationError",
                    "message": str(exc),
                })
                return
            self._json(HTTPStatus.OK, mock_lookup(year))
        else:
            self._json(HTTPStatus.NOT_FOUND, {"message": "Not found"})

    def _send(
        self,
        status: HTTPStatus,
        content_type: str,
        body: bytes,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(
            f"[{datetime.now(KST).strftime('%H:%M:%S')}] "
            f"{self.address_string()} {format % args}\n"
        )


def main() -> int:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer((host, port), PreviewHandler)
    print(
        f"hometax-agent-client web sample (PREVIEW) on http://{host}:{port}/"
    )
    print("의존성 없이 stub 데이터로 응답합니다. Stop with Ctrl-C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
