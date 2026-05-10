"""ID/PW 직접 로그인 — OACX 우회, ``pubcLogin`` hidden form.

캡처 흐름::

    1. ATXPPABA001R07 : POST /wqAction.do        → 사전 검증 ('S' 응답)
    2. pubcLogin      : POST /pubcLogin.do?…     → hidden form, tin + 세션쿠키

캡처 검증된 인코딩:

- R07 의 ``id``: ``",".join(list(id))+","`` → base64
- R07 의 ``pswd``: base64(pswd)
- pubcLogin 의 ``id``: base64(id)
- pubcLogin 의 ``pswd``: base64(pswd)
- 2차 확인 사용 시 ``txprDscmNo=base64(주민번호 앞 6자리 + 뒤 1자리)``,
  ``sq2LgnYn=Y``

⚠️ **2026-05 이후 보호 스크립트 변경**: 홈택스가 ``pubcLogin.do`` 요청 본문을
브라우저 보호 스크립트로 random protected fields 형태로 감싸기 시작했다.
직접 form POST 가 HTTP 400 또는 partial ``TXPPsessionID`` 만 만들고 끝나는
케이스가 있다. 이 경우 ``ProtectedLoginError`` 가 raise 된다. 별도 부트스트랩
도구(``[bootstrap]`` extras)로 cookies 를 받아 ``HometaxClient.from_cookies``
로 주입하는 것을 권장. 향후 보호 스크립트가 RE 되면 이 모듈 안에서 직접
재구성한다.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..crypto import nts_encrypt
from ..exceptions import HometaxError, ProtectedLoginError

if TYPE_CHECKING:
    from ..client import HometaxClient


class IdPwAuthError(HometaxError):
    """ID/PW 인증 흐름에서 발생한 오류."""


@dataclass
class IdPwResult:
    """ID/PW 인증 성공 결과."""

    user_id: str
    tin: str | None
    cookies: dict[str, str]


class IdPwAuth:
    """ID/PW 로그인. ``KakaoAuth``/``NaverAuth`` 와 동일한 인터페이스
    (``authenticate`` / ``to_client``).
    """

    BASE_URL = "https://hometax.go.kr"
    NETFUNNEL_URL = "https://apct.hometax.go.kr/ts.wseq"
    LOGIN_PAGE_URL = (
        "https://hometax.go.kr/websquare/websquare.html"
        "?w2xPath=/ui/comm/a/b/UTXPPABA01.xml&w2xHome=/ui/pp/&w2xDocumentRoot="
    )

    def __init__(
        self,
        *,
        user_id: str,
        password: str,
        rrn: str | None = None,
        impersonate: str = "chrome",
    ) -> None:
        """
        Args:
            user_id: 홈택스 로그인 ID.
            password: 홈택스 로그인 비밀번호.
            rrn: 주민등록번호 13자리 또는 앞 7자리 ("YYMMDDS" / "YYMMDD-S").
                ID/PW 로그인 2차 인증(``sq2LgnYn=Y``)에 사용. 일부 계정은
                필수, 일부 계정은 선택적이다. 라이브러리 안에서 base64
                인코딩과 ``txprDscmNo`` 변환을 처리.
        """
        if not user_id or not password:
            raise IdPwAuthError("user_id, password 모두 필수")
        self.user_id = user_id
        self.password = password
        self._rrn_input = rrn
        self.txpr_dscm_no = self._encode_sq2_txpr_dscm_no(rrn)
        from curl_cffi import requests as cf
        self.session: Any = cf.Session(impersonate=impersonate)
        self._tin: str | None = None
        self._validated: bool = False
        self._login_id_value: str = user_id
        self._login_pswd_value: str = password

    # ------------------------------------------------------------------ #
    # 흐름                                                                #
    # ------------------------------------------------------------------ #

    def authenticate(self, on_wait: Any = None, **_: Any) -> IdPwResult:
        """전체 흐름. ``on_wait`` 인자는 OACX 호환용 (폴링 없음).

        브라우저 캡처(2026-05-10, ``docs/hometax-facts.md §15``) 와 정렬된
        순서로 호출:

            GET /                                        (포털 진입)
            POST wqAction ATXPPABA001A25                 (메인 포털 warmup)
            POST wqAction ATXPPCBA001R020                (메인 포털 warmup)
            GET LOGIN_PAGE_URL                           (로그인 화면 진입)
            POST permission.do?screenId=UTXPPABA01       (로그인 화면 권한)
            POST wqAction ATXPPABA001R07                 (ID/PW 사전 검증)
            GET netfunnel                                (트래픽 큐)
            POST pubcLogin.do                            (1차)
            ── if RRN 필요 ──
            POST permission.do?screenId=UTXPPABC12       (RRN 화면 활성화)
            POST pubcLogin.do                            (2차, txprDscmNo 포함)
        """
        self._prime_hometax_login_context()
        self.validate_credentials()
        self._get_netfunnel("public_m_id_login")
        cookies, tin = self.login_to_hometax()
        self._tin = tin
        return IdPwResult(
            user_id=self.user_id,
            tin=tin,
            cookies=cookies,
        )

    def validate_credentials(self) -> None:
        """``ATXPPABA001R07`` — ID/PW 사전 검증.

        ``result='S'`` 통과시 부수 효과로 잠금카운트 등 처리.
        """
        encoded_pw = base64.b64encode(
            self.password.encode("utf8"),
        ).decode("utf8")
        body = {
            "pswd": encoded_pw,
            "id": self._encode_id_r07(self.user_id),
        }
        body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        signed = body_json + nts_encrypt(body_json, user_id="")
        url = (
            f"{self.BASE_URL}/wqAction.do"
            "?actionId=ATXPPABA001R07&screenId=UTXPPABA01"
            "&popupYn=false&realScreenId="
        )
        response = self.session.post(
            url,
            data=signed,
            headers=self._wqaction_headers(),
            timeout=15,
        )
        try:
            data = response.json()
        except Exception as exc:
            raise IdPwAuthError(
                f"R07 응답 파싱 실패: {response.text[:300]!r}"
            ) from exc
        rmsg = data.get("resultMsg") or {}
        result = rmsg.get("result")
        if result != "S":
            msg = rmsg.get("msg") or rmsg.get("detailMsg") or "(no msg)"
            code = rmsg.get("code") or ""
            raise IdPwAuthError(
                f"R07 검증 실패 result={result!r} code={code} msg={msg}"
            )
        login_values = self._extract_r07_login_values(data)
        if login_values:
            self._login_id_value, self._login_pswd_value = login_values
        self._validated = True

    def login_to_hometax(self) -> tuple[dict[str, str], str | None]:
        """``pubcLogin.do`` — 직접 hidden form POST.

        Returns:
            (cookies dict, tin) — tin 은 응답 ``tin`` 값 또는 None.

        Raises:
            ProtectedLoginError: 2026-05 부터 활성화된 브라우저 보호 스크립트로
                인해 직접 POST 가 거부된 경우. 호출자는 부트스트랩 경로를
                사용하거나 보호 스크립트 RE 가 필요.
            IdPwAuthError: 그 외 거부 (자격증명 오류 / 추가 인증 필요 등).
        """
        if not self._validated:
            raise IdPwAuthError(
                "validate_credentials() 가 먼저 호출되어야 합니다."
            )
        id_enc = base64.b64encode(
            self._login_id_value.encode("utf8"),
        ).decode("utf8")
        pw_enc = base64.b64encode(
            self._login_pswd_value.encode("utf8"),
        ).decode("utf8")
        data = {
            "ssoLoginYn": "Y",
            "secCardLoginYn": "",
            "secCardId": "",
            "cncClCd": "01",
            "id": id_enc,
            "pswd": pw_enc,
            "ssoStatus": "",
            "portalStatus": "",
            "scrnId": "UTXPPABA01",
            "userScrnRslnXcCnt": "1920",
            "userScrnRslnYcCnt": "1080",
        }
        response = self._post_pubc_login(data)
        if getattr(response, "status_code", 200) >= 400:
            raise ProtectedLoginError(
                "pubcLogin.do 가 HTTP "
                f"{response.status_code} 로 거부되었습니다. "
                "2026-05 이후 보호 스크립트로 직접 POST 가 막힐 수 있습니다. "
                "[bootstrap] extras 의 부트스트랩 도구로 cookies 를 받아 "
                "HometaxClient.from_cookies 로 주입하세요."
            )
        text = response.text

        if self._extract_lgn_rslt_cd(text) == "30":
            if not self.txpr_dscm_no:
                raise IdPwAuthError(
                    "ID/PW 로그인 2차 인증이 필요합니다. "
                    "rrn 인자에 주민번호 앞 7자리 또는 13자리를 전달하세요."
                )
            self._activate_rrn_screen()
            data.update({
                "txprDscmNo": self.txpr_dscm_no,
                "pkcLoginYn": "N",
                "sq2LgnYn": "Y",
            })
            sq2_cert_yn = self._extract_field(text, "sq2LgnCertYn")
            if sq2_cert_yn:
                data["sq2LgnCertYn"] = sq2_cert_yn
            response = self._post_pubc_login(data)
            if getattr(response, "status_code", 200) >= 400:
                raise ProtectedLoginError(
                    "pubcLogin.do (2차) 가 HTTP "
                    f"{response.status_code} 로 거부되었습니다. "
                    "보호 스크립트 또는 일시적 차단 가능성."
                )
            text = response.text

        rslt_cd = self._extract_lgn_rslt_cd(text)
        if self._is_pubc_failure(text) or rslt_cd == "30":
            err = self._extract_err_msg(text) or text[:300]
            raise IdPwAuthError(f"pubcLogin 거부: {err!r}")

        tin = self._extract_field(text, "tin")
        cookies = {c.name: c.value for c in self.session.cookies.jar}
        return cookies, tin

    # ------------------------------------------------------------------ #
    # 클라이언트 전환                                                      #
    # ------------------------------------------------------------------ #

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
        """``authenticate()`` 후 ``HometaxClient`` 로 전환.

        ``user_id`` 는 입력 ID 와 ``sessionMap.userId`` 가 다를 수 있어 빈
        값으로 시작 → ``client.session_info()`` 가 실제 ``sessionMap.userId``
        를 자동 채운다.
        """
        from ..client import HometaxClient
        return HometaxClient(
            session=self.session,
            user_id=user_id or "",
            tin=tin or self._tin,
            host=host,
            teht_host=teht_host,
            max_retries=max_retries,
            refresh_interval_sec=refresh_interval_sec,
        )

    # ------------------------------------------------------------------ #
    # 내부                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _encode_id_r07(user_id: str) -> str:
        """캡처 검증: ``'testuser'`` → ``'t,e,s,t,u,s,e,r,'`` → base64."""
        joined = ",".join(list(user_id)) + ","
        return base64.b64encode(joined.encode("utf8")).decode("utf8")

    @staticmethod
    def _extract_r07_login_values(
        data: dict[str, Any],
    ) -> tuple[str, str] | None:
        """Return the latest HomeTax R07 login values from known shapes."""
        candidates: list[Any] = [
            data,
            data.get("response"),
            data.get("reponse"),
            data.get("dma_search_r2"),
            data.get("map"),
        ]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            login_id = item.get("id")
            login_pswd = item.get("pswd")
            if login_id and login_pswd:
                return str(login_id), str(login_pswd)
        return None

    @staticmethod
    def _encode_sq2_txpr_dscm_no(value: str | None) -> str | None:
        if not value:
            return None
        digits = re.sub(r"\D", "", value)
        if len(digits) not in {7, 13}:
            raise IdPwAuthError(
                "rrn 은 주민번호 앞 7자리 또는 전체 13자리여야 합니다."
            )
        sq2 = digits[:7]
        return base64.b64encode(sq2.encode("utf8")).decode("utf8")

    def _post_pubc_login(self, data: dict[str, str]) -> Any:
        return self.session.post(
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

    @staticmethod
    def _is_pubc_failure(text: str) -> bool:
        return "'code' : 'F'" in text or "'code':'F'" in text

    @staticmethod
    def _extract_lgn_rslt_cd(text: str) -> str | None:
        return IdPwAuth._extract_field(text, "lgnRsltCd")

    @staticmethod
    def _extract_field(text: str, key: str) -> str | None:
        pattern = (
            r"['\"]" + re.escape(key) + r"['\"]\s*:\s*['\"]([^'\"]*)['\"]"
        )
        match = re.search(pattern, text)
        return match.group(1) if match else None

    def _prime_hometax_login_context(self) -> None:
        """브라우저 진입 흐름을 모방해 cookies / referer chain 을 구축.

        브라우저 캡처(2026-05-10) 와 정렬된 순서:
        ``GET /`` → 메인 포털 warmup (A25 + R020) → ``GET LOGIN_PAGE_URL`` →
        ``POST permission.do?screenId=UTXPPABA01``.
        """
        get_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;"
                      "q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": self.BASE_URL + "/",
            "User-Agent": "Mozilla/5.0",
        }
        try:
            self.session.get(
                self.BASE_URL + "/", headers=get_headers, timeout=20,
            )
        except Exception:
            pass
        self._warmup_main_portal()
        try:
            self.session.get(
                self.LOGIN_PAGE_URL, headers=get_headers, timeout=20,
            )
        except Exception:
            pass
        try:
            self.session.post(
                self.BASE_URL
                + "/permission.do?screenId=UTXPPABA01&domain=hometax.go.kr",
                data=(
                    "<map id='postParam'><popupYn>false</popupYn></map>"
                ).encode("utf-8"),
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

    def _warmup_main_portal(self) -> None:
        """메인 포털에서 트리거되는 두 wqAction (best-effort).

        2026-05-10 캡처(``captures/2026-05-10T23-12-46/``) 의 entry 230, 231
        과 동일. 일부 계정/조건에서는 이 사전 호출이 누락되면 후속
        ``pubcLogin.do`` 가 거부될 수 있어 방어적으로 호출한다. 실패해도 메인
        흐름은 진행 — 본 사용자 계정처럼 영향 없는 경우엔 단순 latency.
        """
        portal_referer = (
            f"{self.BASE_URL}/websquare/websquare.html"
            "?w2xPath=/ui/pp/index_pp.xml&menuCd=index3"
        )
        warmup_calls: list[tuple[str, dict[str, Any]]] = [
            ("ATXPPABA001A25", {"ipUData": ""}),
            (
                "ATXPPCBA001R020",
                {
                    "scrnId": "0900000000",
                    "pageInfoVO": {
                        "totalCount": "0",
                        "pageSize": "10",
                        "pageNum": "1",
                    },
                },
            ),
        ]
        for action_id, body in warmup_calls:
            body_json = json.dumps(
                body, ensure_ascii=False, separators=(",", ":"),
            )
            signed = body_json + nts_encrypt(body_json, user_id="")
            url = (
                f"{self.BASE_URL}/wqAction.do"
                f"?actionId={action_id}&screenId=UTXPPABA01"
                "&popupYn=false&realScreenId="
            )
            try:
                self.session.post(
                    url,
                    data=signed,
                    headers={
                        "Accept": "application/json",
                        "Accept-Language": "ko-KR",
                        "Content-Type": "application/json; charset=UTF-8",
                        "Origin": self.BASE_URL,
                        "Referer": portal_referer,
                        "User-Agent": "Mozilla/5.0",
                    },
                    timeout=15,
                )
            except Exception:
                pass

    def _activate_rrn_screen(self) -> None:
        """1차 ↔ 2차 사이 RRN 화면 (``UTXPPABC12``) 활성화 (best-effort).

        2026-05-10 캡처의 entry 240. 본문은 빈 JSON ``{}`` — 기존
        ``HometaxClient.activate_subsystem_session`` 의 ``ssoToken`` XML
        본문과는 다른 가벼운 화면 활성화. 실패해도 메인 흐름은 진행.
        """
        try:
            self.session.post(
                f"{self.BASE_URL}/permission.do?screenId=UTXPPABC12",
                data=b"{}",
                headers={
                    "Accept": "application/json; charset=UTF-8",
                    "Accept-Language": "ko-KR",
                    "Content-Type": "application/json; charset=UTF-8",
                    "Origin": self.BASE_URL,
                    "Referer": self.LOGIN_PAGE_URL,
                    "User-Agent": "Mozilla/5.0",
                },
                timeout=15,
            )
        except Exception:
            pass

    def _get_netfunnel(self, action_id: str) -> str | None:
        ts = int(time.time() * 1000)
        url = (
            f"{self.NETFUNNEL_URL}"
            f"?opcode=5101&nfid=0&prefix=NetFunnel.gRtype=5101;"
            f"&sid=service_1&aid={action_id}&js=yes&{ts}"
        )
        try:
            response = self.session.get(
                url,
                headers={
                    "Referer": self.LOGIN_PAGE_URL,
                    "User-Agent": "Mozilla/5.0",
                },
                timeout=15,
            )
        except Exception:
            return None
        match = re.search(
            r"NetFunnel\.gControl\.result='([^']+)'", response.text,
        )
        if not match:
            return None
        result = match.group(1)
        if result.startswith("5002:200"):
            self.session.cookies.set(
                "NetFunnel_ID", result, domain="hometax.go.kr",
            )
            return result
        return None

    @staticmethod
    def _extract_err_msg(text: str) -> str | None:
        match = re.search(r"decodeURIComponent\('([^']*)'\)", text)
        if match:
            try:
                return urllib.parse.unquote(match.group(1)).replace("+", " ")
            except Exception:
                return match.group(1)
        return None

    def _wqaction_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Language": "ko-KR",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": self.BASE_URL,
            "Referer": self.LOGIN_PAGE_URL,
            "User-Agent": "Mozilla/5.0",
        }
