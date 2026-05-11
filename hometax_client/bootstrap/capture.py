"""Headed Playwright recon for HomeTax 로그인.

산출물 (1 캡처당):

- ``cookies.json``       — Playwright cookies array. ``HometaxClient.from_cookies``
                            가 그대로 받는다.
- ``storage_state.json`` — Playwright storage_state (cookies + localStorage 등).
- ``trace.har``          — HAR (request/response body 포함, ``content=embed``).
                            mitmproxy / Chrome DevTools 가 그대로 import.
- ``meta.json``          — 캡처 메타데이터 (시작/종료 시간, URL, 쿠키 이름 목록).

플랫폼 중립:

- 기본은 Playwright 번들 chromium (Linux / macOS / Windows 모두 동일).
- ``channel="chrome"`` 으로 시스템 Chrome 사용도 가능.
- 경로/타임스탬프 모두 Windows-safe (콜론 미사용).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

_KST = ZoneInfo("Asia/Seoul")

DEFAULT_PORTAL_URL = "https://hometax.go.kr/"

# UTXPPABA01.xml 에 deep-link 로 직접 진입하면 메인 포털을 거쳐 가는 priming
# (cookies, referer chain) 이 빠져 ID 로그인 폼이 정상 동작하지 않는다. 사람이
# 직접 캡처할 때는 메인 포털에서 출발해 "로그인" 버튼으로 이동하는 게 맞다.
# 이 상수는 호환용 / 자동화용으로만 보존.
DEFAULT_LOGIN_URL = (
    "https://hometax.go.kr/websquare/websquare.html"
    "?w2xPath=/ui/comm/a/b/UTXPPABA01.xml&w2xHome=/ui/pp/&w2xDocumentRoot="
)

DEFAULT_START_URL = DEFAULT_PORTAL_URL

# 로그인 완료 신호 쿠키.
#
# 2026-05-10 캡처 검증 (`captures/2026-05-10T23-12-46/`):
# - entry 0 (anon GET /)        → `WMONID`, `TXPPsessionID` (익명에도 set, 부적합)
# - entry 235 (1차 pubcLogin.do) → `NTS_LOGIN_SYSTEM_CODE_P=TXPP` (RRN 전 fire, 부적합)
# - entry 242 (2차 pubcLogin.do) → `NTS_REQUEST_SYSTEM_CODE_P` (post-RRN, 적합)
#
# `NTS_REQUEST_SYSTEM_CODE_P` 는 RRN 통과한 2차 pubcLogin 응답에서만 set 된다.
# RRN 이 필요 없는 계정은 단일 pubcLogin 응답에 같이 들어올 가능성이 높지만
# 미검증 — manual mode 가 안전한 default.
LOGIN_INDICATOR_COOKIES: tuple[str, ...] = ("NTS_REQUEST_SYSTEM_CODE_P",)

_DEFAULT_VIEWPORT = (1280, 900)


def _timestamp_dir() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%dT%H-%M-%S")


def _chmod_0o600(path: Path) -> None:
    """PII 가능성 있는 산출물을 ``0o600`` 으로. Windows / 권한 없는 fs 는 noop.

    ``save_session`` / ``write_session_file`` 의 동일 정책을 bootstrap 산출물
    (cookies / storage_state / HAR / meta) 에도 적용한다. 실제 PII 가 들어갈
    수 있는 파일들 (특히 HAR: ID/PW 인증 시 비밀번호·RRN 7자리 포함 가능).
    """
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _import_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright 미설치. [bootstrap] extras 를 설치하세요:\n"
            "    uv sync --extra bootstrap   # 또는\n"
            "    pip install 'hometax-agent-client[bootstrap]'\n"
            "이후 한 번만:\n"
            "    playwright install chromium"
        ) from exc
    return sync_playwright


class CaptureSession:
    """Headed Playwright 세션. 컨텍스트 매니저로 사용한다.

    Example::

        with CaptureSession(output_dir="captures/recon-idpw") as cap:
            cap.open_start_page()           # 메인 포털 (/)
            cap.wait_for_login()            # 사람이 직접 로그인할 때까지 대기
            paths = cap.dump()              # cookies / HAR / meta 저장
        print(paths["cookies"])
    """

    def __init__(
        self,
        *,
        output_dir: str | Path,
        headed: bool = True,
        record_har: bool = True,
        channel: str | None = None,
        viewport: tuple[int, int] = _DEFAULT_VIEWPORT,
        user_agent: str | None = None,
        locale: str = "ko-KR",
        storage_state: str | Path | None = None,
    ) -> None:
        """
        Args:
            output_dir: 산출물 저장 경로 (없으면 생성).
            headed: ``False`` 면 헤드리스. 사람이 폰 승인/2차 인증을 해야 하는
                흐름은 항상 headed 가 자연스럽다.
            record_har: HAR 수집 여부. 보호 스크립트 / 응답 분석용.
            channel: ``"chrome"``/``"msedge"`` 등 Playwright channel. ``None``
                이면 번들 chromium.
            viewport: 창 크기. 모바일 UA 가 필요하면 user_agent 도 같이 지정.
            user_agent: UA 오버라이드. ``None`` 이면 chromium 기본.
            locale: 브라우저 locale. 홈택스는 ``ko-KR`` 가정.
            storage_state: 이전 캡처의 ``storage_state.json`` 경로. 지정하면
                해당 cookies + localStorage 상태로 컨텍스트가 시작되어 재로그인
                없이 둘러보기가 가능하다. 세션이 만료되었으면 홈택스가 로그인
                페이지로 리다이렉트하므로 호출자가 인지 가능.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.headed = headed
        self.record_har = record_har
        self.channel = channel
        self.viewport = viewport
        self.user_agent = user_agent
        self.locale = locale
        self.storage_state = (
            Path(storage_state) if storage_state is not None else None
        )
        if self.storage_state is not None and not self.storage_state.exists():
            raise FileNotFoundError(
                f"storage_state 파일이 없습니다: {self.storage_state}"
            )
        self._pw: Any = None
        self._browser: Any = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._har_path = self.output_dir / "trace.har"
        self._started_at: str | None = None
        self._closed = False

    # ------------------------------------------------------------------ #
    # 라이프사이클                                                        #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> CaptureSession:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def start(self) -> None:
        """브라우저 / 컨텍스트 / 페이지 기동."""
        sync_playwright = _import_playwright()
        self._pw = sync_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": not self.headed}
        if self.channel:
            launch_kwargs["channel"] = self.channel
        self._browser = self._pw.chromium.launch(**launch_kwargs)

        context_kwargs: dict[str, Any] = {
            "viewport": {
                "width": self.viewport[0],
                "height": self.viewport[1],
            },
            "locale": self.locale,
        }
        if self.user_agent:
            context_kwargs["user_agent"] = self.user_agent
        if self.storage_state is not None:
            # cookies + localStorage 복원. 세션 만료 시 홈택스가 로그인 페이지로
            # 리다이렉트하므로 호출자가 인지 가능.
            context_kwargs["storage_state"] = str(self.storage_state)
        if self.record_har:
            context_kwargs["record_har_path"] = str(self._har_path)
            # "embed" = HAR 안에 base64 본문 인라인. mitmproxy / Chrome
            # DevTools 모두 그대로 import 가능.
            context_kwargs["record_har_content"] = "embed"

        self._context = self._browser.new_context(**context_kwargs)
        self._page = self._context.new_page()
        self._started_at = datetime.now(_KST).isoformat()

    def close(self) -> None:
        """역순으로 정리. HAR 은 context.close() 시점에 finalize 된다."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        # HAR 은 context.close() 직후 finalize 된다. 그 시점 이후에야 정상적인
        # chmod 가능 (Playwright 가 쓰는 중에는 호출 안 함).
        if self.record_har and self._har_path.exists():
            _chmod_0o600(self._har_path)

    # ------------------------------------------------------------------ #
    # 접근자                                                              #
    # ------------------------------------------------------------------ #

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("CaptureSession 이 start 되지 않았습니다.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("CaptureSession 이 start 되지 않았습니다.")
        return self._context

    # ------------------------------------------------------------------ #
    # 네비게이션 / 대기                                                    #
    # ------------------------------------------------------------------ #

    def open_start_page(self, url: str = DEFAULT_START_URL) -> None:
        """시작 페이지를 연다. 기본은 메인 포털 (``/``).

        UTXPPABA01.xml 같은 로그인 deep-link 로 바로 가면 priming 이 안 되어
        ID 로그인 폼이 정상 동작하지 않는다. 메인 포털에서 출발해 "로그인"
        버튼으로 이동하는 정상 흐름을 따른다.
        """
        self.page.goto(url, wait_until="load")

    def wait_for_login(
        self,
        *,
        timeout: float = 600.0,
        indicator_cookies: tuple[str, ...] = LOGIN_INDICATOR_COOKIES,
        poll_interval: float = 1.0,
    ) -> None:
        """``indicator_cookies`` 중 하나라도 set 되면 return.

        ⚠️ 쿠키 기반 자동 종료는 다단계 로그인(예: ID/PW + RRN 2차)에서 1차
        통과 시점에 fire 할 수 있다. 어떤 쿠키가 정확히 "완전 로그인" 후에만
        set 되는지 검증되지 않은 흐름이라면 :meth:`wait_for_user` 를 쓴다.

        Args:
            timeout: 초. 사람이 로그인하기 충분한 여유 (기본 10분).
            indicator_cookies: 로그인 완료 신호 쿠키. 기본은
                ``NTS_LOGIN_SYSTEM_CODE_P`` / ``NTS_REQUEST_SYSTEM_CODE_P``
                (인증 통과 후 발급). ``TXPPsessionID``/``WMONID`` 는 익명
                첫 로드부터 set 되어 신호로 부적절.
            poll_interval: 폴링 간격 (초).

        Raises:
            TimeoutError: timeout 안에 신호 쿠키가 잡히지 않음.
        """
        targets = set(indicator_cookies)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            names = {c["name"] for c in self.context.cookies()}
            if names & targets:
                return
            time.sleep(poll_interval)
        raise TimeoutError(
            f"로그인 완료 신호({list(indicator_cookies)}) 가 "
            f"{timeout:.0f}초 내에 잡히지 않았습니다."
        )

    def wait_for_user(
        self,
        prompt: str = (
            "[recon] 로그인을 완료하고 (메인 포털 진입 확인) 이 터미널에서 "
            "Enter 를 누르세요... "
        ),
    ) -> None:
        """사람이 직접 종료를 알려줄 때까지 차단.

        다단계 인증 / 알 수 없는 새 흐름을 처음 분석할 때 사용. 쿠키 기반
        자동 종료가 어느 단계에서 fire 하는지 모를 때 안전한 default.
        """
        try:
            input(prompt)
        except EOFError:
            # stdin 이 닫혔거나 비대화형 — 그냥 return.
            pass

    # ------------------------------------------------------------------ #
    # 산출물 dump                                                         #
    # ------------------------------------------------------------------ #

    def dump(
        self,
        *,
        cookies_name: str = "cookies.json",
        storage_name: str = "storage_state.json",
        meta_name: str = "meta.json",
    ) -> dict[str, Path]:
        """모든 산출물 저장 후 경로 dict 반환.

        HAR 은 ``record_har=True`` 인 경우 ``output_dir/trace.har`` 에 저장되며
        ``close()`` 시점에 finalize 된다 (``with`` 블록을 빠져나갈 때 완료).
        """
        cookies_path = self.output_dir / cookies_name
        storage_path = self.output_dir / storage_name
        meta_path = self.output_dir / meta_name

        cookies = self.context.cookies()
        cookies_path.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _chmod_0o600(cookies_path)
        self.context.storage_state(path=str(storage_path))
        _chmod_0o600(storage_path)

        meta = {
            "started_at": self._started_at,
            "dumped_at": datetime.now(_KST).isoformat(),
            "url": self.page.url,
            "cookie_names": sorted({c["name"] for c in cookies}),
            "har": (
                str(self._har_path) if self.record_har else None
            ),
        }
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _chmod_0o600(meta_path)

        result: dict[str, Path] = {
            "output_dir": self.output_dir,
            "cookies": cookies_path,
            "storage_state": storage_path,
            "meta": meta_path,
        }
        if self.record_har:
            result["har"] = self._har_path
        return result


def capture_login(
    output_dir: str | Path | None = None,
    *,
    url: str = DEFAULT_START_URL,
    headed: bool = True,
    record_har: bool = True,
    channel: str | None = None,
    wait_mode: str = "manual",
    timeout: float = 600.0,
    indicator_cookies: tuple[str, ...] = LOGIN_INDICATOR_COOKIES,
    storage_state: str | Path | None = None,
) -> dict[str, Path]:
    """원샷 헬퍼: 브라우저 띄우고 → 로그인 대기 → 산출물 저장.

    Args:
        output_dir: 산출물 경로. ``None`` 이면 ``captures/<KST timestamp>/``.
        url: 시작 URL. 기본은 메인 포털 (``https://hometax.go.kr/``). 메인의
            "로그인" 버튼으로 진입해야 priming 이 걸려 ID/PW 폼이 동작한다.
            로그인 deep-link 직접 진입은 ID 로그인 폼이 안 뜬다.
        headed: ``False`` 면 헤드리스. 사람이 직접 로그인하는 흐름에서는
            항상 ``True`` (기본).
        record_har: HAR 수집.
        channel: ``"chrome"`` 등으로 시스템 브라우저 사용 가능.
        wait_mode: ``"manual"`` (기본) — 사람이 터미널 Enter 로 종료 알림.
            ``"cookie"`` — ``indicator_cookies`` 중 하나라도 발견되면 자동
            종료. 다단계 인증(예: ID/PW + RRN 2차) 에서는 1차 통과 시점에
            잘못 fire 할 수 있어 recon 용으로는 ``manual`` 권장.
        timeout: ``cookie`` 모드의 최대 대기 초.
        indicator_cookies: ``cookie`` 모드의 신호 쿠키.
        storage_state: 이전 캡처의 ``storage_state.json`` 경로. 지정하면
            재로그인 없이 둘러보기 모드 (만료 시 로그인 페이지로 리다이렉트).

    Returns:
        ``output_dir``, ``cookies``, ``storage_state``, ``meta``,
        ``har`` (수집 시) 키의 ``Path`` dict.
    """
    if output_dir is None:
        output_dir = Path("captures") / _timestamp_dir()
    if wait_mode not in {"manual", "cookie"}:
        raise ValueError(
            f"wait_mode 는 'manual' 또는 'cookie' 중 하나 (받음: {wait_mode!r})"
        )

    with CaptureSession(
        output_dir=output_dir,
        headed=headed,
        record_har=record_har,
        channel=channel,
        storage_state=storage_state,
    ) as cap:
        cap.open_start_page(url)
        if wait_mode == "manual":
            cap.wait_for_user()
        else:
            cap.wait_for_login(
                timeout=timeout,
                indicator_cookies=indicator_cookies,
            )
        return cap.dump()
