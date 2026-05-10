"""홈택스 ``wqAction.do`` 페이로드 서명 (``nts_encrypt``) 와 NTS_KEYS 관리.

알고리즘
========

홈택스 JS 의 ``k.k4(reqData, az)`` 와 동일::

    <nts<nts>nts>{(sec+11):d}{HMAC-SHA256(...)_b64_alnum}{sec:02d}

    HMAC 입력 = message + user_id, key = NTS_KEYS[sec % 7]

NTS_KEYS 는 hometax.go.kr 의 ``js/comm/ui/common_te-min.js`` 의 ``testVal``
배열에서 추출. 평문 노출 — 서버측 비밀이 아니라 단순 시간 기반 mixer.

키 해석 순서
============

``active_keys()`` 는 다음 순서로 NTS_KEYS 를 해석한다 (첫 매칭 사용)::

    1. ``HOMETAX_NTS_KEYS_FILE`` 환경변수가 가리키는 JSON 파일 (있으면)
    2. 사용자별 cache (``~/.cache/hometax-agent-client/nts_keys.json``,
       Windows 는 ``%LOCALAPPDATA%``)
    3. ``NTS_KEYS_BASELINE`` (이 파일에 하드코딩된 2026-04 키)

``save_keys()`` / ``python -m hometax_client.health --refresh`` 가 (2) 를
갱신한다. (1) 은 사용자가 명시적으로 가르치는 경로 (CI 에서 별도 키 사용,
오프라인 검증 등). 매 ``nts_digest`` 호출이 file read 를 한 번씩 하지만
HMAC 비용보다 작다 — memoize 안 함 (다른 프로세스의 ``save_keys`` 와 env
flip 즉시 반영).

라이브 service 헬스 체크
========================

``verify_keys_in_sync()`` 또는 ``python -m hometax_client.health`` 로 라이브
``common_te-min.js`` 와 active 키를 비교. drift 발견 시 ``--refresh`` 로
cache 갱신.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

KST: Final = ZoneInfo("Asia/Seoul")

# ------------------------------------------------------------------ #
# 상수                                                                #
# ------------------------------------------------------------------ #

NTS_MARKER: Final = "<nts<nts>nts>"

NTS_KEYS_JS_URL: Final = (
    "https://hometax.go.kr/js/comm/ui/common_te-min.js"
)

# 2026-04 시점 키 (offline-safe baseline). 라이브가 다르면
# ``verify_keys_in_sync()`` 가 drift 감지 → ``save_keys()`` 로 cache 갱신.
NTS_KEYS_BASELINE: Final = (
    "fjaS3kdHQsdfvnm359WxzmWMV8xm5qmrcRXxolOqm4",
    "qns5HuJxhT3QM8cIOSxqYw92xOpv7oMETetLjO3Zog",
    "Zomr4yL5NpOcj4EfBxdDsweUxOvGWugbJ7c9xhwm",
    "tOpenmvLO8XhwmY2Nxpi2eP3xcmniJj2e4xc8FamH0",
    "qyVMuRUwZO93CGhkWtJFFrmEKMAg9z3FBLcKAyMxxA",
    "RF413bvdLE31OL3dnmeC7r7EbMVo1oh4OrOVMMysR",
    "OINbDScmre3r8ckDpIoKAyO5B6wwKulnDJkxwFBvRX",
)

# 하위 호환 — 옛 import 가 ``from hometax_client.crypto import NTS_KEYS`` 한
# 코드를 보호. 새 코드는 ``active_keys()`` 또는 ``NTS_KEYS_BASELINE`` 사용.
NTS_KEYS: Final = NTS_KEYS_BASELINE

ENV_KEYS_FILE: Final = "HOMETAX_NTS_KEYS_FILE"

_ALNUM_FILTER = re.compile(r"[^0-9a-zA-Z]")
_TESTVAL_PATTERN = re.compile(r"testVal\s*=\s*\[([^\]]+)\]")
_KEY_LITERAL_PATTERN = re.compile(r'"([A-Za-z0-9]+)"')
_VALID_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


# ------------------------------------------------------------------ #
# 키 source / cache                                                   #
# ------------------------------------------------------------------ #


def _default_cache_path() -> Path:
    """플랫폼별 기본 cache 파일 경로."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return (
                Path(base) / "hometax-agent-client" / "nts_keys.json"
            )
    return (
        Path.home() / ".cache" / "hometax-agent-client" / "nts_keys.json"
    )


def _load_keys_from_file(path: Path) -> tuple[str, ...] | None:
    """JSON cache 에서 7개 alnum 키 로드. 검증 실패시 ``None``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(keys, list) or len(keys) != 7:
        return None
    if not all(
        isinstance(k, str) and _VALID_KEY_PATTERN.fullmatch(k)
        for k in keys
    ):
        return None
    return tuple(keys)


def active_keys() -> tuple[str, ...]:
    """현재 활성 NTS_KEYS — env > 기본 cache > baseline 순서.

    매 호출이 최대 한 번의 file read 를 하지만 HMAC 비용보다 작다. memoize
    안 해 다른 프로세스의 cache 갱신과 env flip 이 즉시 반영된다.
    """
    env_path = os.environ.get(ENV_KEYS_FILE)
    if env_path:
        keys = _load_keys_from_file(Path(env_path))
        if keys is not None:
            return keys
    cache_keys = _load_keys_from_file(_default_cache_path())
    if cache_keys is not None:
        return cache_keys
    return NTS_KEYS_BASELINE


def extract_keys_from_js(text: str) -> tuple[str, ...]:
    """``common_te-min.js`` 의 ``testVal`` 배열에서 7개 키 추출.

    Raises:
        ValueError: ``testVal`` 미발견 또는 키 개수 ≠ 7.
    """
    match = _TESTVAL_PATTERN.search(text)
    if not match:
        raise ValueError(
            "common_te-min.js: testVal 배열을 찾지 못함 — JS 구조 변경 가능"
        )
    keys = tuple(_KEY_LITERAL_PATTERN.findall(match.group(1)))
    if len(keys) != 7:
        raise ValueError(
            f"common_te-min.js: 키 개수가 7이 아님 ({len(keys)}): {keys}"
        )
    return keys


def fetch_live_keys(
    *,
    timeout: float = 15.0,
    max_retries: int = 2,
) -> tuple[str, ...]:
    """라이브 ``common_te-min.js`` 에서 NTS_KEYS 를 추출.

    ``curl_cffi`` 사용 (홈택스의 TLS fingerprint 검사 통과). connection reset
    류 transient 실패는 ``max_retries`` 만큼 0.5+0.5*n 초 backoff 로 재시도.
    """
    from curl_cffi import requests as cf

    session = cf.Session(impersonate="chrome")
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = session.get(NTS_KEYS_JS_URL, timeout=timeout)
            response.raise_for_status()
            return extract_keys_from_js(response.text)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(0.5 + 0.5 * attempt)
                continue
            raise
    raise RuntimeError("unreachable") from last_exc


def save_keys(
    keys: tuple[str, ...] | list[str],
    *,
    path: str | Path | None = None,
) -> Path:
    """7개 alnum 키를 JSON cache 로 저장. 반환은 저장된 ``Path``.

    경로 우선순위: ``path`` 인자 > ``HOMETAX_NTS_KEYS_FILE`` > 기본 cache.
    """
    keys_tuple = tuple(keys)
    if len(keys_tuple) != 7 or not all(
        isinstance(k, str) and _VALID_KEY_PATTERN.fullmatch(k)
        for k in keys_tuple
    ):
        raise ValueError(
            f"keys 는 7개 alnum 문자열이어야 합니다: {keys_tuple}"
        )

    target: Path
    if path is not None:
        target = Path(path)
    elif os.environ.get(ENV_KEYS_FILE):
        target = Path(os.environ[ENV_KEYS_FILE])
    else:
        target = _default_cache_path()

    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "keys": list(keys_tuple),
        "saved_at": int(time.time()),
        "source": NTS_KEYS_JS_URL,
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


@dataclass(frozen=True)
class KeyHealthReport:
    """``verify_keys_in_sync()`` 결과."""

    in_sync: bool
    active: tuple[str, ...]
    live: tuple[str, ...]

    @property
    def drift_indices(self) -> tuple[int, ...]:
        return tuple(
            i for i, (a, b) in enumerate(zip(self.active, self.live))
            if a != b
        )


def verify_keys_in_sync(*, timeout: float = 15.0) -> KeyHealthReport:
    """라이브 NTS_KEYS 를 fetch 해 active 키와 비교."""
    live = fetch_live_keys(timeout=timeout)
    active = active_keys()
    return KeyHealthReport(
        in_sync=(active == live), active=active, live=live,
    )


# ------------------------------------------------------------------ #
# 서명 알고리즘                                                       #
# ------------------------------------------------------------------ #


def nts_digest(
    message: str,
    *,
    sec: int | None = None,
    user_id: str = "",
) -> str:
    """홈택스 HMAC digest (transport marker 없음)."""
    if sec is None:
        sec = datetime.now(KST).second
    if not 0 <= sec <= 59:
        raise ValueError(f"sec must be 0..59, got {sec}")

    key = active_keys()[sec % 7]
    digest = hmac.digest(
        key.encode("utf8"),
        (message + (user_id or "")).encode("utf8"),
        hashlib.sha256,
    )
    return _ALNUM_FILTER.sub("", base64.b64encode(digest).decode("utf8"))


def nts_encrypt(
    message: str,
    *,
    sec: int | None = None,
    user_id: str = "",
) -> str:
    """body 문자열에 시간 기반 HMAC-SHA256 서명 부착.

    Args:
        message: ``wqAction.do`` 의 request body (JSON 직렬화된 문자열).
        sec: 0~59 의 second. None 이면 현재 KST 의 second 사용.
        user_id: ``sessionMap.userId``. message 끝에 mix-in.

    Returns:
        message 끝에 붙일 서명 문자열 (NTS_MARKER 포함).
    """
    if sec is None:
        sec = datetime.now(KST).second
    encoded = nts_digest(message, sec=sec, user_id=user_id)
    return f"{NTS_MARKER}{sec + 11}{encoded}{sec:02d}"


def nts_report_signature(
    action_id: str,
    *,
    sec: int | None = None,
) -> tuple[str, str]:
    """ClipReport service 서명 페어 ``(b, bb)`` 반환.

    HomeTax report 가 ``bb = k.k4(actionId, sec)``, ``b = (sec + 15) +
    k.k4(bb, sec) + sec`` 으로 만든다.
    """
    if sec is None:
        sec = datetime.now(KST).second
    bb = nts_digest(action_id, sec=sec)
    b = f"{sec + 15}{nts_digest(bb, sec=sec)}{sec:02d}"
    return b, bb
