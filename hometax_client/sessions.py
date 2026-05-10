"""다중 세션 관리 — ``SessionStore``.

세무사 사무실처럼 여러 고객 세션을 동시에 보유해야 할 때 사용한다. 디렉토리
하나에 ``<client_id>.json`` 형태로 세션 파일을 보관하고, 사람-친화 ``label``
(예: "김철수") 과 ``auth_method`` 메타를 같이 저장한다.

설계 원칙
=========

- **파일 IO 만**. 세션 lock / 자동 refresh / 진행 상태 / UI 모두 호출자
  책임 (``architecture.md`` 의 라이브러리/워크플로 경계).
- **client_id 는 사용자 책임**. 동명이인 처리 / slug 규칙은 워크플로 layer.
  허용 문자 ``[A-Za-z0-9_-]`` (filesystem 안전, 1~64자).
- **drift-tolerant**. 알지 못하는 필드는 ``SessionEntry.raw`` 에 보존.
- **마지막-쓰기 우선**. 동시성 제어 없음. 필요 시 OS 레벨 lock 으로 호출자가
  처리.

기본 사용
=========

::

    from hometax_client import SessionStore

    store = SessionStore()                            # captures/sessions/
    store.save(client, client_id="kim", label="김철수", auth_method="idpw")

    for entry in store.list():
        print(entry.client_id, entry.label, entry.tin)

    client = store.open("kim")                        # last_used_at 자동 갱신
    health = store.health("kim", live=False)          # cheap meta check
    if not health.fresh:
        # 만료 처리는 호출자 책임 (재인증 흐름 분기 등)
        ...
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from .exceptions import HometaxError

if TYPE_CHECKING:
    from .client import HometaxClient


DEFAULT_STORE_DIR = "captures/sessions"
DEFAULT_FRESH_WITHIN_SEC = 1800  # 30분 — HomeTax 세션 idle timeout 추정

_CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# ----------------------------------------------------------------- #
# 데이터 모델                                                        #
# ----------------------------------------------------------------- #


@dataclass(frozen=True)
class SessionEntry:
    """세션 파일 한 개의 메타데이터 view (read-only)."""

    client_id: str
    label: str | None
    user_id: str | None
    tin: str | None
    auth_method: str | None
    saved_at: int
    last_used_at: int | None
    path: Path
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def last_active(self) -> int:
        """``last_used_at or saved_at`` — health 판단의 단일 timestamp."""
        return self.last_used_at if self.last_used_at is not None else self.saved_at


@dataclass(frozen=True)
class SessionHealth:
    """``SessionStore.health()`` 결과.

    Attributes:
        client_id: 검사 대상.
        fresh: ``True`` 면 사용 가능. ``live=True`` 검사에서는 실제 검증.
        reason: ``recent`` / ``stale`` / ``missing`` / ``verified`` /
            ``session_expired`` / ``error:<ExcClass>`` 등.
        checked_at: 검사 시각 (unix ts).
    """

    client_id: str
    fresh: bool
    reason: str
    checked_at: int


# ----------------------------------------------------------------- #
# 파일 IO 헬퍼                                                       #
# ----------------------------------------------------------------- #


def write_session_file(path: Path, payload: dict[str, Any]) -> Path:
    """세션 JSON 을 atomic 하게 저장 (0o600). 중간 디렉토리 자동 생성.

    ``HometaxClient.save_session`` 과 ``SessionStore.save`` 가 공유.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        dir=str(path.parent), prefix=".tmp.", suffix=".json",
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return path


def _read_session_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _entry_from_data(path: Path, data: dict[str, Any]) -> SessionEntry:
    return SessionEntry(
        client_id=data.get("client_id") or path.stem,
        label=data.get("label"),
        user_id=data.get("user_id"),
        tin=data.get("tin"),
        auth_method=data.get("auth_method"),
        saved_at=int(data.get("saved_at") or 0),
        last_used_at=(
            int(data["last_used_at"])
            if isinstance(data.get("last_used_at"), (int, float))
            else None
        ),
        path=path,
        raw=data,
    )


# ----------------------------------------------------------------- #
# SessionStore                                                       #
# ----------------------------------------------------------------- #


class SessionStore:
    """디렉토리 기반 다중 세션 보관소.

    한 디렉토리에 ``<client_id>.json`` 파일들을 두고 list/open/save/health 등을
    제공. 동시성 제어 / 자동 refresh / UI 는 책임 밖.
    """

    def __init__(
        self,
        directory: str | Path = DEFAULT_STORE_DIR,
        *,
        fresh_within_sec: int = DEFAULT_FRESH_WITHIN_SEC,
    ) -> None:
        """
        Args:
            directory: 세션 파일을 보관할 디렉토리 (기본
                ``captures/sessions``, 프로젝트 상대). 그 외 경로는 명시.
            fresh_within_sec: ``health(live=False)`` 에서 fresh 로 인정할
                ``last_active`` 범위 (초). 기본 1800 (30분).
        """
        self.directory = Path(directory)
        self.fresh_within_sec = int(fresh_within_sec)

    # ----- 내부 -----

    def _validate_id(self, client_id: str) -> None:
        if not isinstance(client_id, str) or not _CLIENT_ID_PATTERN.fullmatch(
            client_id
        ):
            raise ValueError(
                "client_id 는 [A-Za-z0-9_-] 1~64 자만 허용 — "
                f"받음: {client_id!r}"
            )

    def _path_for(self, client_id: str) -> Path:
        self._validate_id(client_id)
        return self.directory / f"{client_id}.json"

    # ----- Discovery -----

    def list(self) -> list[SessionEntry]:
        """디렉토리의 모든 유효한 세션 entry 반환 (정렬: client_id)."""
        if not self.directory.exists():
            return []
        out: list[SessionEntry] = []
        for path in sorted(self.directory.glob("*.json")):
            if path.name.startswith(".tmp."):
                continue
            data = _read_session_file(path)
            if data is None:
                continue
            out.append(_entry_from_data(path, data))
        return out

    def get(self, client_id: str) -> SessionEntry | None:
        """단일 entry — 없거나 깨진 파일이면 ``None``."""
        path = self._path_for(client_id)
        if not path.exists():
            return None
        data = _read_session_file(path)
        if data is None:
            return None
        return _entry_from_data(path, data)

    def find_by_tin(self, tin: str) -> SessionEntry | None:
        """tin 일치하는 첫 entry. 없으면 ``None``."""
        for entry in self.list():
            if entry.tin == tin:
                return entry
        return None

    def find_by_user_id(self, user_id: str) -> SessionEntry | None:
        """user_id 일치하는 첫 entry. 없으면 ``None``."""
        for entry in self.list():
            if entry.user_id == user_id:
                return entry
        return None

    def __contains__(self, client_id: object) -> bool:
        if not isinstance(client_id, str):
            return False
        try:
            self._validate_id(client_id)
        except ValueError:
            return False
        return self._path_for(client_id).exists()

    def __len__(self) -> int:
        return len(self.list())

    def __iter__(self) -> Iterator[SessionEntry]:
        return iter(self.list())

    # ----- Read -----

    def open(self, client_id: str) -> HometaxClient:
        """저장된 cookies 로 ``HometaxClient`` 복원. ``last_used_at`` 자동 갱신.

        Raises:
            KeyError: client_id 가 store 에 없음.
            ValueError: client_id 형식 불량.
        """
        from .client import HometaxClient

        entry = self.get(client_id)
        if entry is None:
            raise KeyError(client_id)
        client = HometaxClient.from_cookies(entry.path)
        try:
            self.touch(client_id)
        except KeyError:
            pass
        return client

    # ----- Write -----

    def save(
        self,
        client: HometaxClient,
        *,
        client_id: str,
        label: str | None = None,
        auth_method: str | None = None,
    ) -> Path:
        """현재 client 의 세션을 ``<client_id>.json`` 으로 저장.

        Args:
            client: 저장할 ``HometaxClient``.
            client_id: 파일명 / 검색 키 ([A-Za-z0-9_-] 1~64자).
            label: 사람 친화 alias (한글 OK). 동명이인 처리는 호출자 책임.
            auth_method: ``"idpw"``/``"kakao"``/``"naver"``/``"cookies"`` 등.
                만료 시 호출자가 어떤 인증 흐름으로 재시도할지 결정에 사용.

        Returns:
            저장된 파일 ``Path``.
        """
        path = self._path_for(client_id)
        now = int(time.time())
        payload = client._session_payload(
            client_id=client_id,
            label=label,
            auth_method=auth_method,
            last_used_at=now,
        )
        return write_session_file(path, payload)

    def touch(self, client_id: str) -> None:
        """쿠키 변경 없이 ``last_used_at`` 만 현재 시각으로 갱신.

        Raises:
            KeyError: client_id 가 store 에 없음.
        """
        path = self._path_for(client_id)
        if not path.exists():
            raise KeyError(client_id)
        data = _read_session_file(path)
        if data is None:
            raise KeyError(client_id)
        data["last_used_at"] = int(time.time())
        write_session_file(path, data)

    # ----- Maintenance -----

    def remove(self, client_id: str) -> bool:
        """파일 삭제. 존재했으면 ``True``, 없었으면 ``False``."""
        path = self._path_for(client_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    # ----- Health -----

    def health(
        self,
        client_id: str,
        *,
        live: bool = False,
    ) -> SessionHealth:
        """세션 신선도 검사.

        Args:
            client_id: 검사 대상.
            live: ``True`` 면 ``session_info()`` 실호출로 권위 검증. ``False``
                (기본) 면 ``last_active`` 가 ``fresh_within_sec`` 안인지만 검사
                — 네트워크 0회.

        Returns:
            ``SessionHealth``. ``reason`` 으로 분기 가능 (``recent`` / ``stale``
            / ``missing`` / ``verified`` / ``session_expired`` /
            ``error:<ExcClass>`` 등).
        """
        now = int(time.time())
        entry = self.get(client_id)
        if entry is None:
            return SessionHealth(
                client_id=client_id,
                fresh=False,
                reason="missing",
                checked_at=now,
            )
        meta_fresh = (now - entry.last_active) < self.fresh_within_sec
        if not live:
            return SessionHealth(
                client_id=client_id,
                fresh=meta_fresh,
                reason="recent" if meta_fresh else "stale",
                checked_at=now,
            )
        # live verification
        from .client import HometaxClient
        from .exceptions import SessionExpiredError

        try:
            client = HometaxClient.from_cookies(entry.path)
            client.session_info()
        except SessionExpiredError:
            return SessionHealth(
                client_id=client_id,
                fresh=False,
                reason="session_expired",
                checked_at=now,
            )
        except HometaxError as exc:
            return SessionHealth(
                client_id=client_id,
                fresh=False,
                reason=f"error:{type(exc).__name__}",
                checked_at=now,
            )
        except Exception as exc:
            return SessionHealth(
                client_id=client_id,
                fresh=False,
                reason=f"error:{type(exc).__name__}",
                checked_at=now,
            )
        # success — touch 로 last_used_at 갱신
        try:
            self.touch(client_id)
        except KeyError:
            pass
        return SessionHealth(
            client_id=client_id,
            fresh=True,
            reason="verified",
            checked_at=now,
        )

    def health_all(
        self,
        *,
        live: bool = False,
    ) -> list[SessionHealth]:
        """전체 store 일괄 검사."""
        return [
            self.health(entry.client_id, live=live)
            for entry in self.list()
        ]


__all__ = [
    "SessionStore",
    "SessionEntry",
    "SessionHealth",
    "DEFAULT_STORE_DIR",
    "DEFAULT_FRESH_WITHIN_SEC",
    "write_session_file",
]
