"""OACX 간편인증 공통 흐름 — 회원 / 비회원.

캡처 + 옛 hometax-scraper(2021) 의 ``user.py`` 흐름 분석에서 재구성::

    [0]. (비회원만) /oacx/index.jsp 에 이름+RRN POST → server-side 등록
    1. trans       : POST /oacx/api/v1.0/trans            → JWT(token) + txId
    2. provider    : GET  /oacx/api/v1.0/provider/list    (검증용)
    3. NetFunnel   : GET  apct.hometax.go.kr/ts.wseq?aid=…
                                                        → key + 쿠키
    4. authen-req  : POST /oacx/api/v1.0/authen/request   → cxId + 새 토큰
       (사용자가 폰 앱에서 인증 버튼 누름 — 사람 개입 필수)
    5. authen-res  : POST /oacx/api/v1.0/authen/result    (폴링)
                                                  → cert_token (signedData)
    6. pubcLogin   : POST /pubcLogin.do?domain=…  → 홈택스 세션 쿠키 SET
       (비회원이면 ``nMemberLoginYn / txprNm / ssn1 / ssn2`` 추가)

각 provider 는 ``PROVIDER_ID`` / ``PROVIDER`` / ``NETFUNNEL_AID`` 만 다르고
흐름은 동일하다. ``ssn`` 인자 유무로 회원/비회원 모드 분기.
"""

from __future__ import annotations

import base64
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from ..exceptions import HometaxError

if TYPE_CHECKING:
    from ..client import HometaxClient


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf8")).decode("utf8")


def _post_with_tls_retry(
    session: Any,
    url: str,
    *,
    retries: int = 1,
    delay: float = 0.5,
    **kwargs: Any,
) -> Any:
    """``session.post`` + transient transport 에러 1회 재시도.

    curl_cffi 의 Chrome impersonation TLS handshake 가 가끔 RST 당하는
    케이스 대응 (`Recv failure: Connection reset by peer` / curl error 35).
    같은 IP 에서 일반 ``curl`` 은 200 OK 인 시점에도 발생 — fingerprint
    일시 mismatch / WAF 일시 거부 추정.

    ``ConnectionError`` (``SSLError`` 포함) / ``Timeout`` 만 retry. HTTP 4xx
    /5xx 는 retry 하지 않는다 (서버 의도 응답).
    """
    from curl_cffi.requests.exceptions import (
        ConnectionError as CCEConnectionError,
        Timeout,
    )
    for attempt in range(retries + 1):
        try:
            return session.post(url, **kwargs)
        except (CCEConnectionError, Timeout):
            if attempt >= retries:
                raise
            time.sleep(delay * (1 + attempt))
    # unreachable — raise re-issued in loop
    raise RuntimeError("unreachable")


@dataclass
class OACXResult:
    """OACX 인증 성공 시 결과."""

    cert_token: str
    user_id: str | None
    tin: str | None
    cookies: dict[str, str]


class OACXAuthError(HometaxError):
    """OACX 인증 흐름 자체에서 발생한 오류."""


class OACXAuth:
    """OACX 간편인증 base class. provider 별 서브클래스에서 클래스 변수 override."""

    PROVIDER_ID: str = ""
    PROVIDER: str = ""
    NETFUNNEL_AID: str = ""

    BASE_URL = "https://hometax.go.kr"
    NETFUNNEL_URL = "https://apct.hometax.go.kr/ts.wseq"
    LOGIN_PAGE_URL = (
        "https://hometax.go.kr/websquare/websquare.html"
        "?w2xPath=/ui/comm/a/b/UTXPPABA01.xml&w2xHome=/ui/pp/&w2xDocumentRoot="
    )

    def __init__(
        self,
        *,
        name: str,
        phone: str,
        birthday: str,
        ssn: str | None = None,
        impersonate: str = "chrome",
    ) -> None:
        """
        Args:
            name: 실명 (한글 가능).
            phone: 휴대폰번호. ``010-1234-5678`` / ``01012345678`` 둘 다 OK.
            birthday: 생년월일 8자리 ``YYYYMMDD``.
            ssn: 주민등록번호 13자리 (``-`` 무관). 주어지면 **비회원 모드** —
                ``initiate()`` 직전에 ``/oacx/index.jsp`` 에 이름+RRN POST
                하여 server-side 에 비회원 식별자 등록 + ``pubcLogin`` body
                에 ``nMemberLoginYn=Y / txprNm / ssn1 / ssn2`` 추가. ``None``
                이면 회원 모드 (기본).

                근거: ``UTXPPABA01.js`` ``fn_prcsLoginSimpleCallBack`` 의
                ``if (scwin.nrgtMmbrSpmcCertYn)`` 분기 + ``UTECMADA02.js``
                ``scwin.nts_start`` 의 ``/oacx/index.jsp`` form submit.
                ``docs/hometax-facts.md`` §16 참조.
        """
        if not (self.PROVIDER_ID and self.PROVIDER and self.NETFUNNEL_AID):
            raise OACXAuthError(
                "PROVIDER_ID/PROVIDER/NETFUNNEL_AID 가 설정되지 않은 base class"
            )
        self.name = name
        digits = re.sub(r"\D", "", phone)
        self.phone_full = digits
        self.phone1 = digits[:3]
        self.phone2 = digits[3:]
        self.birthday = birthday
        if ssn is not None:
            ssn_digits = re.sub(r"\D", "", ssn)
            if len(ssn_digits) != 13:
                raise OACXAuthError(
                    f"ssn 은 13자리 숫자여야 함 (got {len(ssn_digits)}자리)"
                )
            self._ssn1 = ssn_digits[:6]
            self._ssn2 = ssn_digits[6:]
        else:
            self._ssn1 = None
            self._ssn2 = None
        from curl_cffi import requests as cf
        self.session: Any = cf.Session(impersonate=impersonate)
        self._tx_id: str | None = None
        self._token: str | None = None
        self._cx_id: str | None = None
        self._cert_token: str | None = None

    @property
    def is_guest(self) -> bool:
        """비회원 모드 여부 (``ssn`` 인자로 결정)."""
        return self._ssn1 is not None

    # ------------------------------------------------------------------ #
    # 흐름                                                                #
    # ------------------------------------------------------------------ #

    def initiate(self) -> tuple[str, str]:
        """1단계: ``trans`` → JWT + ``txId``.

        비회원 모드 (``ssn`` 주어짐) 면 ``trans`` 직전에 ``/oacx/index.jsp``
        에 이름+RRN form POST 하여 server-side 에 비회원 식별자 등록.
        """
        if self.is_guest:
            self._register_guest_identity()
        else:
            try:
                self.session.get(
                    f"{self.BASE_URL}/oacx/index.jsp", timeout=15,
                )
            except Exception:
                pass

        response = _post_with_tls_retry(
            self.session,
            f"{self.BASE_URL}/oacx/api/v1.0/trans",
            json={"token": ""},
            headers=self._json_headers(),
            timeout=15,
        )
        try:
            data = response.json()
        except Exception as exc:
            raise OACXAuthError(
                f"trans 응답 파싱 실패: {response.text[:200]!r}"
            ) from exc
        if data.get("oacxCode") != "OACX_SUCCESS":
            raise OACXAuthError(f"trans 실패: {data}")
        self._tx_id = data["txId"]
        self._token = data["token"]
        return self._token, self._tx_id

    def get_provider_list(self) -> list[dict[str, Any]]:
        """2단계: ``provider/list`` (필수는 아님, 디버그/검증용)."""
        response = self.session.get(
            f"{self.BASE_URL}/oacx/api/v1.0/provider/list",
            headers=self._json_headers(),
            timeout=15,
        )
        return response.json()

    def get_netfunnel(self) -> str | None:
        """3단계: NetFunnel 큐 통과 → key + ``NetFunnel_ID`` 쿠키 set.

        provider 의 aid 가 NetFunnel 에 등록 안 된 경우(``5002:501``)는
        skip 으로 간주하고 ``None`` 반환 — 네이버 등 NetFunnel 안 타는
        provider 대응.
        """
        ts = int(time.time() * 1000)
        url = (
            f"{self.NETFUNNEL_URL}"
            f"?opcode=5101&nfid=0&prefix=NetFunnel.gRtype=5101;"
            f"&sid=service_1&aid={self.NETFUNNEL_AID}&js=yes&{ts}"
        )
        response = self.session.get(
            url,
            headers={
                "Referer": self.BASE_URL + "/",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )
        match = re.search(
            r"NetFunnel\.gControl\.result='([^']+)'", response.text,
        )
        if not match:
            raise OACXAuthError(
                f"NetFunnel 응답 파싱 실패: {response.text[:200]!r}"
            )
        result = match.group(1)
        if result.startswith("5002:200"):
            self.session.cookies.set(
                "NetFunnel_ID", result, domain="hometax.go.kr",
            )
            return result
        if result.startswith("5002:501"):
            return None
        raise OACXAuthError(f"NetFunnel 거부: {result[:200]}")

    def request_authentication(self) -> str:
        """4단계: ``authen/request`` → ``cxId`` + 새 토큰.

        이 시점에 사용자 폰에 알림이 도착한다.
        """
        if not (self._tx_id and self._token):
            raise OACXAuthError("initiate() 가 먼저 호출되어야 함")
        body = self._build_authen_body(self._token)
        response = self.session.post(
            f"{self.BASE_URL}/oacx/api/v1.0/authen/request",
            json=body,
            headers=self._json_headers(),
            timeout=15,
        )
        data = response.json()
        sys_msg = data.get("systemMessage") or ""
        cli_msg = data.get("clientMessage") or ""
        oacx_code = data.get("oacxCode") or ""
        success = (
            sys_msg == "성공"
            or cli_msg == "성공"
            or (
                oacx_code == "OACX_SUCCESS"
                and data.get("cxId")
                and data.get("token")
            )
        )
        if not success:
            raise OACXAuthError(f"authen/request 실패: {data}")
        self._cx_id = data["cxId"]
        self._token = data["token"]
        return self._cx_id

    def poll_result(
        self,
        *,
        max_attempts: int = 10,
        interval_sec: float = 15.0,
        on_wait: Callable[[int], None] | None = None,
        on_response: Callable[[int, dict[str, Any]], None] | None = None,
    ) -> str:
        """5단계: ``authen/result`` 폴링. 사용자 폰 인증을 기다린다."""
        if not (self._tx_id and self._token and self._cx_id):
            raise OACXAuthError(
                "request_authentication() 가 먼저 호출되어야 함"
            )
        body = self._build_authen_body(self._token, with_cx_id=True)
        for attempt in range(1, max_attempts + 1):
            if on_wait:
                try:
                    on_wait(attempt)
                except Exception:
                    pass
            time.sleep(interval_sec)
            try:
                self.get_netfunnel()
            except Exception:
                pass
            response = self.session.post(
                f"{self.BASE_URL}/oacx/api/v1.0/authen/result",
                json=body,
                headers=self._json_headers(),
                timeout=20,
            )
            try:
                data = response.json()
            except Exception:
                if on_response:
                    try:
                        on_response(attempt, {"_raw": response.text[:300]})
                    except Exception:
                        pass
                continue
            if on_response:
                try:
                    on_response(attempt, data)
                except Exception:
                    pass

            status = (data.get("oacxStatus") or "").upper()
            sys_msg = data.get("systemMessage") or ""
            cli_msg = data.get("clientMessage") or ""
            oacx_code = data.get("oacxCode") or ""
            success = (
                status == "AFTER_RESULT"
                or sys_msg == "성공"
                or cli_msg == "성공"
                or (oacx_code == "OACX_SUCCESS" and "signedData" in data)
            )
            if success and data.get("token"):
                self._cert_token = data["token"]
                return self._cert_token
        raise OACXAuthError(
            f"인증 시간초과 ({max_attempts * interval_sec:.0f}s) — "
            "폰 승인 미발생 또는 응답 패턴이 예상과 다름"
        )

    def login_to_hometax(self) -> dict[str, str]:
        """6단계: ``pubcLogin.do`` — 인증 토큰을 홈택스 세션 쿠키로 변환.

        비회원 모드면 회원 form 에 ``nMemberLoginYn=Y / txprNm / ssn1 / ssn2``
        를 추가한다 (``UTXPPABA01.js`` ``fn_prcsLoginSimpleCallBack`` 의
        ``scwin.nrgtMmbrSpmcCertYn`` 분기와 1:1 매핑).
        """
        if not self._cert_token:
            raise OACXAuthError("poll_result() 가 먼저 성공해야 함")

        self._prime_hometax_login_context()

        data: dict[str, str] = {}
        if self.is_guest:
            assert self._ssn1 is not None and self._ssn2 is not None
            data["nMemberLoginYn"] = "Y"
            # JS 는 txprNm 만 raw, ssn1/ssn2 만 base64. 일관성 없어도 그대로 흉내.
            data["txprNm"] = self.name
            data["ssn1"] = _b64(self._ssn1)
            data["ssn2"] = _b64(self._ssn2)
        data["moisCertYn"] = "Y"
        data["newGpinYn"] = "Y"
        data["reqTxId"] = self._cert_token
        data["ssoStatus"] = ""
        data["portalStatus"] = ""
        data["scrnId"] = "UTXPPABA01"
        data["userScrnRslnXcCnt"] = "1920"
        data["userScrnRslnYcCnt"] = "1080"
        response = self.session.post(
            f"{self.BASE_URL}/pubcLogin.do?domain=hometax.go.kr&mainSys=Y",
            data=data,
            headers={
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.BASE_URL,
                "Referer": self.LOGIN_PAGE_URL,
                "User-Agent": "Mozilla/5.0",
            },
            timeout=20,
        )
        text = response.text
        if "'code' : 'F'" in text or "'code':'F'" in text:
            msg = self._extract_pubc_login_error(text)
            raise OACXAuthError(
                f"pubcLogin 거부됨: {msg or text[:300]!r}"
            )
        return {c.name: c.value for c in self.session.cookies.jar}

    def _register_guest_identity(self) -> None:
        """비회원 OACX 진입 단계 — ``/oacx/index.jsp`` 에 이름+RRN POST.

        ``UTECMADA02.js`` ``scwin.nts_start`` 의 form submit (``ssn``,
        ``userName``) 흉내. server-side 가 이 ssn/userName 을 다음 ``trans``
        로 생성될 txId 에 묶어 둔다 (이후 ``authen/request`` body 의
        ``ssn1/ssn2`` 가 빈 채로 가도 동작).

        값은 두 키 모두 base64 인코딩. ``userName`` 은 한글 UTF-8 base64.
        """
        assert self._ssn1 is not None and self._ssn2 is not None
        ssn_raw = self._ssn1 + self._ssn2  # 13자리 평문
        body = {
            "popupType": "layer",
            "userType": "R",
            "ssn": _b64(ssn_raw),
            "userName": _b64(self.name),
        }
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;"
                      "q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.BASE_URL,
            "Referer": self.LOGIN_PAGE_URL,
            "User-Agent": "Mozilla/5.0",
        }
        try:
            _post_with_tls_retry(
                self.session,
                f"{self.BASE_URL}/oacx/index.jsp",
                data=body,
                headers=headers,
                timeout=20,
            )
        except Exception as exc:
            raise OACXAuthError(
                f"비회원 식별자 등록 실패 (/oacx/index.jsp): {exc}"
            ) from exc

    def _prime_hometax_login_context(self) -> None:
        """실제 로그인 화면이 ``pubcLogin`` 전에 만드는 TXPP 컨텍스트를 준비."""
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;"
                      "q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": self.BASE_URL + "/",
            "User-Agent": "Mozilla/5.0",
        }
        for url in (self.BASE_URL + "/", self.LOGIN_PAGE_URL):
            try:
                self.session.get(url, headers=headers, timeout=20)
            except Exception:
                pass

        permission_body = (
            "<map id='postParam'><popupYn>false</popupYn></map>"
        )
        try:
            self.session.post(
                self.BASE_URL
                + "/permission.do?screenId=UTXPPABA01&domain=hometax.go.kr",
                data=permission_body.encode("utf-8"),
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                    "Content-Type": "application/xml; charset=UTF-8",
                    "Origin": self.BASE_URL,
                    "Referer": self.LOGIN_PAGE_URL,
                    "User-Agent": "Mozilla/5.0",
                },
                timeout=20,
            )
        except Exception:
            pass

    @staticmethod
    def _extract_pubc_login_error(text: str) -> str | None:
        match = re.search(r"decodeURIComponent\('([^']*)'\)", text)
        if not match:
            return None
        try:
            return urllib.parse.unquote(match.group(1)).replace("+", " ")
        except Exception:
            return match.group(1)

    # ------------------------------------------------------------------ #
    # 한 번에 — authenticate                                              #
    # ------------------------------------------------------------------ #

    def authenticate(
        self,
        *,
        on_wait: Callable[[int], None] | None = None,
        max_attempts: int = 10,
        interval_sec: float = 15.0,
    ) -> OACXResult:
        """전체 흐름 한 번에 → 결과 반환."""
        self.initiate()
        self.get_netfunnel()
        self.request_authentication()
        cert_token = self.poll_result(
            max_attempts=max_attempts,
            interval_sec=interval_sec,
            on_wait=on_wait,
        )
        cookies = self.login_to_hometax()
        return OACXResult(
            cert_token=cert_token,
            user_id=None,
            tin=None,
            cookies=cookies,
        )

    def to_client(
        self,
        *,
        user_id: str | None = None,
        tin: str | None = None,
        host: str = "hometax.go.kr",
        teht_host: str = "teht.hometax.go.kr",
        max_retries: int = 1,
        refresh_interval_sec: float = 0.0,
    ) -> HometaxClient:
        """``authenticate()`` 후 ``HometaxClient`` 로 직접 전환."""
        from ..client import HometaxClient
        return HometaxClient(
            session=self.session,
            user_id=user_id or "",
            tin=tin,
            host=host,
            teht_host=teht_host,
            max_retries=max_retries,
            refresh_interval_sec=refresh_interval_sec,
        )

    # ------------------------------------------------------------------ #
    # 내부                                                                #
    # ------------------------------------------------------------------ #

    def _json_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Language": "ko-KR",
            "Content-Type": "application/json",
            "Origin": self.BASE_URL,
            "Referer": (
                f"{self.BASE_URL}/oacx/index.jsp"
                "?popupType=layer&userType=R&ssn=&userName="
            ),
            "User-Agent": "Mozilla/5.0",
        }

    def _build_authen_body(
        self,
        token: str,
        *,
        with_cx_id: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": "",
            "provider": self.PROVIDER,
            "token": token,
            "txId": self._tx_id,
            "appInfo": {"code": "", "path": "", "type": ""},
            "userInfo": {
                "isMember": False,
                "name": _b64(self.name),
                "phone": _b64(self.phone_full),
                "phone1": _b64(self.phone1),
                "phone2": _b64(self.phone2),
                "ssn1": "",
                "ssn2": "",
                "birthday": _b64(self.birthday),
                "privacy": 1,
                "policy3": 0,
                "policy4": 1,
                "terms": 0,
                "telcoTycd": None,
                "access_token": "",
                "token_type": "",
                "state": "",
                "mtranskeySsn2": None,
            },
            "deviceInfo": {
                "code": "PC",
                "browser": "WB",
                "os": "",
                "universalLink": False,
            },
            "contentInfo": {
                "signTarget": "",
                "signTargetTycd": "nonce",
                "signType": "GOV_SIMPLE_AUTH",
                "requestTitle": "",
                "requestContents": "",
            },
            "providerOptionInfo": {
                "callbackUrl": "",
                "reqCSPhoneNo": "1",
                "upmuGb": "",
                "isUseTss": "Y",
                "isNotification": "Y",
                "isPASSVerify": "Y",
                "isUserAgreement": "Y",
            },
            "compareCI": False,
        }
        if with_cx_id:
            body["cxId"] = self._cx_id
            body["providerId"] = self.PROVIDER_ID
            body["providerName"] = self._provider_display_name()
            body["deeplinkUri"] = ""
            body["naverAppSchemeUrl"] = ""
            body["telcoTxid"] = ""
            body["mdlAppHash"] = ""
            body["useMdlSsn"] = False
        return body

    def _provider_display_name(self) -> str:
        return {
            "kakao": "카카오톡",
            "naver": "네이버",
        }.get(self.PROVIDER_ID, self.PROVIDER_ID)
