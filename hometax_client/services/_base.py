"""서비스 모듈 공통 베이스.

모든 서비스 클래스는 ``ServiceBase`` 를 상속해 ``HometaxClient`` 를 ``self._c``
로 보유한다. 공통 동작(``tin`` 보정, 서브시스템 활성화)은 여기에 모은다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import UnknownResponseError

if TYPE_CHECKING:
    from ..client import HometaxClient


class ServiceBase:
    """``HometaxClient`` 를 보유하는 서비스 클래스의 공통 베이스."""

    def __init__(self, client: HometaxClient) -> None:
        self._c = client

    def _ensure_tin(self) -> str:
        """``client.tin`` 이 비어 있으면 ``session_info()`` 로 보충."""
        if not self._c.tin:
            self._c.session_info()
        if not self._c.tin:
            raise UnknownResponseError(
                "홈택스 내부 식별번호(tin)를 확보하지 못했습니다."
            )
        return self._c.tin

    def _cookie_value(self, name: str) -> str:
        for cookie in self._c._session.cookies.jar:
            if cookie.name == name:
                return cookie.value
        return ""
