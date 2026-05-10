"""HometaxClient — wqAction.do 직접 호출 코어.

세션 자체의 발급(카카오/공인인증서 인증)은 범위 밖이다. 이미 발급된 세션
쿠키를 ``from_cookies`` 로 주입하거나, ``login(auth=...)`` 으로 OACX 인증을
한 번 거친다.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import string
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from zoneinfo import ZoneInfo

from .constants import ESSENTIAL_COOKIES, SUBSYSTEM_HOSTS
from .crypto import nts_encrypt
from .exceptions import (
    BlockedError,
    SessionExpiredError,
    UnknownResponseError,
    classify_failure,
)
from .models import SessionInfo

if TYPE_CHECKING:
    from .auth.oacx import OACXAuth
    from .services.income_tax import IncomeTaxService
    from .services.inquiries import InquiryService

# 세션 캐시 기본 경로 — captures/ 는 .gitignore 에 포함되므로 안전.
DEFAULT_SESSION_CACHE = "captures/.session.json"

_KST = ZoneInfo("Asia/Seoul")
_BLOCK_PATTERN = re.compile(r"\b(EIE2\d{3}|ECE10\d{2})\b")
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)


def _random_query(length: int = 21) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _normalize_cookie_domain(domain: str | None) -> str:
    """Playwright 쿠키 도메인 (.hometax.go.kr) → curl_cffi 형식."""
    if not domain:
        return "hometax.go.kr"
    return domain.lstrip(".") or "hometax.go.kr"


def _resolve_host(host: str) -> str:
    """별칭(``"teht"``)이면 풀 호스트로, 풀 호스트면 그대로 반환."""
    return SUBSYSTEM_HOSTS.get(host, host)


class HometaxClient:
    """홈택스 ``wqAction.do`` 호출 클라이언트."""

    def __init__(
        self,
        *,
        session: Any,
        user_id: str,
        tin: str | None = None,
        host: str = "hometax.go.kr",
        teht_host: str = "teht.hometax.go.kr",
        max_retries: int = 1,
        refresh_interval_sec: float = 0.0,
    ) -> None:
        """
        Args:
            session: HTTP 세션 (``curl_cffi.requests.Session`` 또는 호환).
            user_id: ``sessionMap.userId``.
            tin: 납세자통합관리번호. 없으면 ``session_info()`` 첫 호출 시 자동 보정.
            host / teht_host: 메인 / teht 서브시스템 도메인.
            max_retries: connection reset / SSL 일시 오류 시 재시도 횟수.
            refresh_interval_sec: 0 보다 크면 ``wq_action`` 호출 직전 자동
                ``refresh_session()`` 을 호출 (마지막 refresh 후 N 초 경과 시).
        """
        self._session = session
        self.user_id = user_id
        self.tin = tin
        self.host = host
        self.teht_host = teht_host
        self.max_retries = max_retries
        self.refresh_interval_sec = refresh_interval_sec
        self._last_refresh_ts: float = 0.0
        self.sso_token: str | None = None
        self.user_cl_cd: str | None = None
        self._inquiries: InquiryService | None = None
        self._income_tax: IncomeTaxService | None = None

    # ------------------------------------------------------------------ #
    # 생성자                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_cookies(
        cls,
        cookies_path: str | Path,
        *,
        user_id: str | None = None,
        tin: str | None = None,
        host: str = "hometax.go.kr",
        teht_host: str = "teht.hometax.go.kr",
        impersonate: str = "chrome",
        max_retries: int = 1,
        refresh_interval_sec: float = 0.0,
    ) -> HometaxClient:
        """쿠키 파일에서 클라이언트 생성. 두 형식 자동 감지.

        1. **Playwright cookies.json** = ``[{name, value, domain, path, ...}]``
           (배열) — ``user_id`` 인자 필수.
        2. **save_session() 캐시** = ``{"user_id": ..., "tin": ...,
           "cookies": [...]}`` (객체) — ``user_id``/``tin`` 이 없으면 캐시값 사용.

        두 형식 모두 ``ESSENTIAL_COOKIES`` 만 추려 주입한다 (UI 한글 쿠키 제외).
        """
        from curl_cffi import requests as cf

        raw = json.loads(Path(cookies_path).read_text(encoding="utf-8"))
        if isinstance(raw, list):
            cookies = raw
            cache_user_id = user_id or ""
            cache_tin = tin
        else:
            cookies = raw.get("cookies", [])
            cache_user_id = (user_id or raw.get("user_id") or "") or ""
            cache_tin = tin if tin is not None else raw.get("tin")

        session = cf.Session(impersonate=impersonate)
        for cookie in cookies:
            if cookie.get("name") not in ESSENTIAL_COOKIES:
                continue
            try:
                session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=_normalize_cookie_domain(cookie.get("domain")),
                )
            except Exception:
                # Cookie injection failures are non-fatal — session probe will
                # surface a clear SessionExpiredError if the jar is broken.
                pass
        return cls(
            session=session,
            user_id=cache_user_id,
            tin=cache_tin,
            host=host,
            teht_host=teht_host,
            max_retries=max_retries,
            refresh_interval_sec=refresh_interval_sec,
        )

    # ------------------------------------------------------------------ #
    # 세션 저장 / 캐시-or-인증                                             #
    # ------------------------------------------------------------------ #

    def _session_payload(self, **extra: Any) -> dict[str, Any]:
        """세션 직렬화 dict — ``ESSENTIAL_COOKIES`` 만, ``extra`` 메타 병합.

        ``save_session`` 과 ``SessionStore.save`` 가 공유하는 내부 헬퍼.
        """
        cookies = []
        for cookie in self._session.cookies.jar:
            if cookie.name not in ESSENTIAL_COOKIES:
                continue
            cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path or "/",
            })
        data: dict[str, Any] = {
            "user_id": self.user_id,
            "tin": self.tin,
            "cookies": cookies,
            "saved_at": int(time.time()),
        }
        data.update(extra)
        return data

    def save_session(
        self,
        path: str | Path = DEFAULT_SESSION_CACHE,
    ) -> Path:
        """현재 cookie jar + ``user_id``/``tin`` 을 JSON 캐시로 저장.

        ``ESSENTIAL_COOKIES`` 에 등록된 쿠키만 보존. 파일 권한 0o600. 반환은
        저장된 ``Path``. 다중 세션 관리는 ``SessionStore`` 사용 권장.
        """
        from .sessions import write_session_file
        return write_session_file(Path(path), self._session_payload())

    @classmethod
    def login(
        cls,
        auth: OACXAuth,
        *,
        user_id: str | None = None,
        cache_path: str | Path = DEFAULT_SESSION_CACHE,
        force_reauth: bool = False,
        on_authenticate: Callable[[], None] | None = None,
        on_wait: Callable[[int], None] | None = None,
        host: str = "hometax.go.kr",
        teht_host: str = "teht.hometax.go.kr",
        max_retries: int = 1,
        refresh_interval_sec: float = 0.0,
    ) -> HometaxClient:
        """캐시 살아있으면 재사용, 없거나 만료시 인증 후 캐시 저장.

        Args:
            auth: ``OACXAuth`` 인스턴스 (``KakaoAuth``/``NaverAuth`` 등).
                캐시 hit 시엔 인증 단계를 거치지 않으므로 폰 승인이 필요 없다.
            user_id: ``sessionMap.userId``. 캐시에 박혀있으면 그쪽 우선.
            cache_path: JSON 캐시 위치. 기본은 ``captures/.session.json``.
            force_reauth: ``True`` 면 캐시 무시하고 재인증.
            on_authenticate: 인증으로 빠질 때 한 번 호출.
            on_wait: 인증 폴링 시 매 시도마다 호출 (``attempt: int``).
        """
        cache_path = Path(cache_path)

        if not force_reauth and cache_path.exists():
            try:
                client = cls.from_cookies(
                    cache_path,
                    user_id=user_id,
                    host=host,
                    teht_host=teht_host,
                    max_retries=max_retries,
                    refresh_interval_sec=refresh_interval_sec,
                )
                info = client.session_info()
                client.tin = client.tin or info.tin
                return client
            except SessionExpiredError:
                # 캐시 stale — 재인증 경로로 fall-through.
                pass
            except (json.JSONDecodeError, FileNotFoundError, OSError):
                pass

        if on_authenticate:
            try:
                on_authenticate()
            except Exception:
                pass

        if on_wait:
            auth.authenticate(on_wait=on_wait)
        else:
            auth.authenticate()

        client = auth.to_client(
            user_id=user_id,
            host=host,
            teht_host=teht_host,
            max_retries=max_retries,
            refresh_interval_sec=refresh_interval_sec,
        )
        try:
            info = client.session_info()
        except SessionExpiredError:
            client.refresh_session()
            info = client.session_info()
        client.tin = info.tin
        client.save_session(cache_path)
        return client

    # ------------------------------------------------------------------ #
    # 핵심 호출 (raw 통로)                                                #
    # ------------------------------------------------------------------ #

    def wq_action(
        self,
        *,
        action_id: str,
        screen_id: str,
        body: dict[str, Any] | None = None,
        host: str | None = None,
        real_screen_id: str = "",
        popup: bool = False,
        referer: str | None = None,
    ) -> dict[str, Any]:
        """``wqAction.do`` 호출 — 서명 부착, 응답 JSON 파싱까지.

        Args:
            action_id: 예 ``"ATXPPBAA001R16"``.
            screen_id: 예 ``"UTXPPBAA48"``.
            body: 요청 본문 dict (JSON 직렬화됨). ``None`` 이면 빈 dict.
            host: 호스트 별칭(``"teht"``) 또는 풀 호스트. ``None`` 이면 ``self.host``.
            real_screen_id: ``realScreenId`` 쿼리 파라미터.
            popup: ``popupYn=true`` 로 보낼지.
            referer: ``Referer`` 헤더 override.

        Returns:
            응답 본문을 dict 로 파싱한 결과 (raw 그대로). 호출자가 알지 못하는
            새 필드도 그대로 보존된다.

        Raises:
            BlockedError: 응답에 EIE2*/ECE10* 코드.
            SessionExpiredError: 세션 만료/권한 부족 의심.
            ValidationError / LoginRequiredError: 메시지 패턴별 분기.
            UnknownResponseError: JSON 파싱 실패 / 비정상 응답.
        """
        body = body or {}
        target_host = _resolve_host(host) if host else self.host

        if self.refresh_interval_sec > 0:
            now = time.time()
            if now - self._last_refresh_ts >= self.refresh_interval_sec:
                try:
                    self.refresh_session()
                except Exception:
                    # refresh 실패해도 메인 호출은 진행 — wq_action 이 직접
                    # SessionExpiredError 를 raise 한다.
                    pass

        body_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        url = (
            f"https://{target_host}/wqAction.do"
            f"?actionId={action_id}"
            f"&screenId={screen_id}"
            f"&popupYn={'true' if popup else 'false'}"
            f"&realScreenId={real_screen_id}"
        )
        ref = referer or (
            f"https://{target_host}/websquare/websquare.html"
            f"?w2xPath=/ui/pp/index_pp.xml&menuCd=index4"
        )

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            signed = body_json + nts_encrypt(body_json, user_id=self.user_id)
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "ko-KR",
                "Content-Type": "application/json",
                "Origin": f"https://{target_host}",
                "Referer": ref,
                "User-Agent": _DEFAULT_USER_AGENT,
                "Sec-Ch-Ua": (
                    '"Chromium";v="147", "Not.A/Brand";v="8"'
                ),
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Linux"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
            try:
                resp = self._session.post(
                    url,
                    data=signed.encode("utf-8"),
                    headers=headers,
                    timeout=30,
                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 + 0.5 * attempt)
                    continue
                raise UnknownResponseError(
                    f"{action_id} 호출 실패 ({type(exc).__name__}: {exc})"
                ) from exc

        text = resp.content.decode("utf-8", errors="replace")
        match = _BLOCK_PATTERN.search(text)
        if match:
            raise BlockedError(match.group(0), text[:200])

        try:
            data = json.loads(text, strict=False)
        except json.JSONDecodeError as exc:
            raise UnknownResponseError(
                f"JSON 파싱 실패: {exc}. body 처음 200: {text[:200]!r}"
            ) from exc

        rm = data.get("resultMsg") or {}
        sm = rm.get("sessionMap") or {}
        if not sm.get("userId"):
            if rm.get("result") == "F" or "로그인" in (rm.get("msg") or ""):
                raise classify_failure(rm, action_id=action_id)

        return data

    # 하위 호환을 위해 옛 이름도 alias 로 유지.
    call_action = wq_action

    # ------------------------------------------------------------------ #
    # 세션 갱신 / 정보                                                    #
    # ------------------------------------------------------------------ #

    def refresh_session(self) -> dict[str, Any]:
        """``/token.do`` 호출로 SSO 토큰 재발급 + 세션 활성 유지."""
        params = {
            "query": _random_query(21),
            "postfix": datetime.now(_KST).strftime("%Y_%m_%d"),
        }
        url = f"https://{self.host}/token.do"
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ko-KR",
            "Referer": f"https://{self.host}/",
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        resp = self._session.get(
            url, params=params, headers=headers, timeout=15,
        )
        text = resp.content.decode("utf-8", errors="replace")
        try:
            data = json.loads(text, strict=False)
        except json.JSONDecodeError as exc:
            data = self._parse_legacy_token_jsonp(text)
            if data is None:
                raise UnknownResponseError(
                    f"/token.do 응답 파싱 실패: {text[:200]!r}"
                ) from exc

        if not data.get("ssoToken") or data["ssoToken"] == "null":
            raise UnknownResponseError(
                f"/token.do 응답에 ssoToken 없음: {text[:300]!r}"
            )

        self.sso_token = data["ssoToken"]
        self.user_cl_cd = data.get("userClCd")
        self._last_refresh_ts = time.time()
        return data

    @staticmethod
    def _parse_legacy_token_jsonp(text: str) -> dict[str, Any] | None:
        """옛 JSONP (``nts_reqPortalCallback("...")``) 응답 fallback."""
        marker = 'nts_reqPortalCallback("'
        if marker not in text:
            return None
        start = text.find(marker) + len(marker)
        end = text.find('");', start)
        inner = text[start:end] if end != -1 else text[start:]
        token_match = re.search(r"<ssoToken>([^<]+)</ssoToken>", inner)
        cls_match = re.search(r"<userClCd>([^<]+)</userClCd>", inner)
        return {
            "ssoToken": token_match.group(1) if token_match else None,
            "userClCd": cls_match.group(1) if cls_match else None,
        }

    def activate_subsystem_session(
        self,
        *,
        host: str,
        screen_id: str,
        popup: bool = True,
        referer: str | None = None,
    ) -> dict[str, Any]:
        """Create/refresh a HomeTax subsystem session from the SSO token."""
        target_host = _resolve_host(host)
        ref = referer or (
            f"https://{target_host}/websquare/websquare.html"
            f"?w2xPath=/ui/pp/index_pp.xml&menuCd=index4"
        )
        last_exc: Exception | None = None
        for attempt in range(3):
            token_data = self.refresh_session()
            token = token_data.get("ssoToken")
            if not token:
                raise UnknownResponseError(
                    f"{target_host} activation failed: empty SSO token"
                )

            body = (
                f'<map id="postParam"><ssoToken>{token}</ssoToken>'
                f"<popupYn>{'true' if popup else 'false'}</popupYn></map>"
            )
            resp = self._session.post(
                (
                    f"https://{target_host}/permission.do"
                    f"?screenId={screen_id}&domain=hometax.go.kr"
                ),
                data=body.encode("utf-8"),
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "ko-KR",
                    "Content-Type": "application/xml; charset=UTF-8",
                    "Origin": f"https://{target_host}",
                    "Referer": ref,
                    "User-Agent": _DEFAULT_USER_AGENT,
                },
                timeout=20,
            )
            text = resp.content.decode("utf-8", errors="replace")
            try:
                data = json.loads(text, strict=False)
            except json.JSONDecodeError as exc:
                raise UnknownResponseError(
                    f"{target_host} permission response parse failed: "
                    f"{text[:200]!r}"
                ) from exc
            rm = data.get("resultMsg") or {}
            if rm.get("errorMsg"):
                exc = classify_failure(
                    rm, action_id=f"permission:{screen_id}",
                )
                last_exc = exc
                if isinstance(exc, SessionExpiredError) and attempt < 2:
                    time.sleep(0.8 + attempt * 0.7)
                    continue
                raise exc
            return data

        if last_exc:
            raise last_exc
        raise UnknownResponseError(f"{target_host} activation failed")

    def activate_tewe_session(
        self,
        *,
        screen_id: str,
        popup: bool = True,
        referer: str | None = None,
    ) -> dict[str, Any]:
        """``tewe.hometax.go.kr`` 서브시스템 활성화 alias."""
        return self.activate_subsystem_session(
            host="tewe",
            screen_id=screen_id,
            popup=popup,
            referer=referer,
        )

    def session_info(self) -> SessionInfo:
        """현재 세션의 사용자 정보 조회 (``ATXPPAAA001R037``).

        부수효과: ``self.user_id`` / ``self.tin`` 이 비어 있으면 응답값으로
        자동 보충한다. ``nts_encrypt`` 의 ``user_id`` mixin 이 이후 호출에서
        자동으로 맞춰진다.
        """
        data = self.wq_action(
            action_id="ATXPPAAA001R037",
            screen_id="index_pp",
            body={"ttxppal032DVO": {"menuId": ""}},
        )
        sm = (data.get("resultMsg") or {}).get("sessionMap") or {}
        if not sm:
            raise UnknownResponseError(
                "sessionMap 없음 — 세션 만료 또는 비정상 응답"
            )
        info = SessionInfo.from_session_map(sm)
        if not self.user_id and info.user_id:
            self.user_id = info.user_id
        if not self.tin and info.tin:
            self.tin = info.tin
        return info

    # ------------------------------------------------------------------ #
    # 서비스 네임스페이스 (lazy)                                          #
    # ------------------------------------------------------------------ #

    @property
    def inquiries(self) -> InquiryService:
        """지급명세서/세금신고 조회."""
        if self._inquiries is None:
            from .services.inquiries import InquiryService
            self._inquiries = InquiryService(self)
        return self._inquiries

    @property
    def income_tax(self) -> IncomeTaxService:
        """종합소득세 신고도움 서비스 조회."""
        if self._income_tax is None:
            from .services.income_tax import IncomeTaxService
            self._income_tax = IncomeTaxService(self)
        return self._income_tax
