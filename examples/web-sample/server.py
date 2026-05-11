"""Minimal web UI example for hometax-agent-client.

**한 화면 / 한 폼 / 한 호출** 로 압축한 데모. 라이브러리 사용 방법을 보여
주기 위한 예시이며, 일괄 조회 / 매니페스트 / 디스크 저장 / PDF 렌더링 같은
운영 기능은 의도적으로 제외했다.

운영용 사무실 워크플로는 별도 워크플로 패키지에서 본 라이브러리를
dependency 로 사용해 구현하는 것을 권장.

실행::

    uv run --env-file .env python examples/web-sample/server.py

환경변수::

    HOST            (선택, 기본 127.0.0.1)
    PORT            (선택, 기본 8787)

    # 인증 — 둘 중 하나
    HOMETAX_COOKIES   captures/cookies.json 같은 cookie 파일 경로 (권장)
    HOMETAX_USER_ID   홈택스 ID (cookies 파일에 user_id 가 박혀 있으면 생략 가능)

    # 또는 ID/PW 직접 (2026-05 보호 스크립트로 막힐 수 있음)
    HOMETAX_USER_ID   홈택스 ID
    HOMETAX_PASSWORD  홈택스 비밀번호
    HOMETAX_RRN       주민번호 13자리 또는 앞 7자리
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from hometax_client import (
    HometaxClient,
    HometaxError,
    ProtectedLoginError,
    SessionExpiredError,
)
from hometax_client.auth import IdPwAuth, IdPwAuthError

KST = ZoneInfo("Asia/Seoul")
HERE = Path(__file__).resolve().parent
INDEX_HTML_PATH = HERE / "index.html"


# ------------------------------------------------------------------ #
# 환경 / 클라이언트 빌더                                                #
# ------------------------------------------------------------------ #


def default_year() -> int:
    return datetime.now(KST).year - 1


def env_status() -> dict[str, Any]:
    return {
        "has_cookies": bool(os.environ.get("HOMETAX_COOKIES")),
        "has_user_id": bool(os.environ.get("HOMETAX_USER_ID")),
        "has_password": bool(os.environ.get("HOMETAX_PASSWORD")),
        "has_rrn": bool(os.environ.get("HOMETAX_RRN")),
        "default_year": default_year(),
    }


def build_client() -> HometaxClient:
    """쿠키 파일 우선, 없으면 ID/PW 로 fallback."""
    cookies_path = os.environ.get("HOMETAX_COOKIES")
    user_id = os.environ.get("HOMETAX_USER_ID") or ""

    if cookies_path and Path(cookies_path).exists():
        return HometaxClient.from_cookies(
            cookies_path=cookies_path,
            user_id=user_id,
        )

    password = os.environ.get("HOMETAX_PASSWORD")
    rrn = os.environ.get("HOMETAX_RRN")
    if not (user_id and password and rrn):
        raise RuntimeError(
            "HOMETAX_COOKIES 또는 (HOMETAX_USER_ID + HOMETAX_PASSWORD + HOMETAX_RRN) 가 필요합니다."
        )
    auth = IdPwAuth(user_id=user_id, password=password, rrn=rrn)
    return HometaxClient.login(auth=auth)


# ------------------------------------------------------------------ #
# 조회 동작                                                            #
# ------------------------------------------------------------------ #


def lookup_year(year: int) -> dict[str, Any]:
    """단건 조회 — 한 귀속연도에 대해 여러 메뉴를 순서대로 호출.

    각 메뉴는 인증 등급에 따라 거부될 수 있다. 한 메뉴가 실패해도 다른
    메뉴는 계속 진행하며, 결과 dict 의 해당 항목에 ``status: "error"``
    로 표기된다.
    """
    started = time.time()
    client = build_client()
    info = client.session_info()

    inquiries: dict[str, Any] = {}

    # 지급명세서 — OACX 등급 필요. ID/PW 세션은 LoginRequiredError.
    try:
        statements = client.inquiries.income_statements(year)
        inquiries["income_statements"] = {
            "status": "ok",
            "count": len(statements),
            "items": [
                {
                    "kind": s.material_kind_name,
                    "payer": s.payer_name,
                    "period": f"{s.period_start}~{s.period_end}",
                }
                for s in statements
            ],
        }
    except HometaxError as exc:
        inquiries["income_statements"] = _error_payload(exc)

    # 세금신고내역 — OACX 등급 필요.
    try:
        filings = client.inquiries.tax_filings(
            start=f"{year}0101",
            end=f"{year}1231",
        )
        inquiries["tax_filings"] = {
            "status": "ok",
            "count": len(filings),
            "items": [
                {
                    "kind": f.statement_kind_name,
                    "date": f.return_date,
                    "computed_tax": f.computed_tax,
                }
                for f in filings
            ],
        }
    except HometaxError as exc:
        inquiries["tax_filings"] = _error_payload(exc)

    # 종소세 신고도움 안내문 — ID/PW 등급에서도 가능.
    try:
        notice = client.income_tax.filing_help_data(year)
        ekop = notice.get("ekopIcmAmtTrtDVO") or {}
        inquiries["filing_help"] = {
            "status": "ok",
            "filing_kind": ekop.get("rtnAtonTfbCdNm"),
            "filing_kind_code": ekop.get("rtnAtonTfbCd"),
        }
    except HometaxError as exc:
        inquiries["filing_help"] = _error_payload(exc)

    # 주소 후보 — ID/PW 등급에서 시도, 추가 인증 필요한 source 는 자체 skip.
    try:
        address = client.income_tax.address_candidates(year)
        inquiries["address"] = {
            "status": address.get("status", "unknown"),
            "road_address": address.get("road_address") or "",
            "lot_address": address.get("lot_address") or "",
            "zip_code": address.get("zip_code") or "",
        }
    except HometaxError as exc:
        inquiries["address"] = _error_payload(exc)

    return {
        "user_name": info.user_name,
        "tin": info.tin,
        "attr_year": year,
        "inquiries": inquiries,
        "elapsed_sec": round(time.time() - started, 2),
    }


def _error_payload(exc: HometaxError) -> dict[str, Any]:
    return {
        "status": "error",
        "type": type(exc).__name__,
        "message": str(exc),
    }


# ------------------------------------------------------------------ #
# HTML / 핸들러                                                        #
# ------------------------------------------------------------------ #


def _read_index_html() -> bytes:
    return INDEX_HTML_PATH.read_bytes()


class Handler(BaseHTTPRequestHandler):
    """단건 조회 한 화면짜리 HTTP 핸들러."""

    server_version = "HometaxSampleUI/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        if path == "/":
            self._send(
                HTTPStatus.OK,
                "text/html; charset=utf-8",
                _read_index_html(),
            )
        elif path == "/api/health":
            self._json(HTTPStatus.OK, {"env": env_status()})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"message": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        if path == "/api/lookup":
            self._handle_lookup()
        else:
            self._json(HTTPStatus.NOT_FOUND, {"message": "Not found"})

    # ------------- handlers -------------

    def _handle_lookup(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            year = int(payload.get("year") or default_year())
            if year < 2010 or year > datetime.now(KST).year:
                raise ValueError("귀속연도가 유효 범위를 벗어났습니다.")
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error_type": "ValidationError", "message": str(exc)},
            )
            return

        try:
            result = lookup_year(year)
        except ProtectedLoginError as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {
                "error_type": "ProtectedLoginError",
                "message": str(exc),
            })
            return
        except IdPwAuthError as exc:
            self._json(HTTPStatus.UNAUTHORIZED, {
                "error_type": "IdPwAuthError",
                "message": str(exc),
            })
            return
        except SessionExpiredError as exc:
            self._json(HTTPStatus.UNAUTHORIZED, {
                "error_type": "SessionExpiredError",
                "message": str(exc),
            })
            return
        except HometaxError as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "error_type": type(exc).__name__,
                "message": str(exc),
            })
            return
        except RuntimeError as exc:
            # 환경변수 미설정 등 사용자 입력 단계 오류.
            self._json(HTTPStatus.BAD_REQUEST, {
                "error_type": "ConfigurationError",
                "message": str(exc),
            })
            return

        self._json(HTTPStatus.OK, result)

    # ------------- helpers -------------

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


# ------------------------------------------------------------------ #
# 진입점                                                              #
# ------------------------------------------------------------------ #


def main() -> int:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"hometax-agent-client web sample listening on http://{host}:{port}/")
    print("Stop with Ctrl-C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
