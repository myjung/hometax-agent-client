"""지급명세서 / 세금신고 조회.

화면 ``UTXPPBAA48`` (지급명세서) 와 ``UTXPPBAA47`` (세금신고내역) 두 메뉴를
담당. 두 메뉴 모두 ``hometax.go.kr`` 메인 호스트에서 호출된다.

식별자는 ``hometax_client.facts.current.toml`` 의
``services.inquiries.*`` 항목에 정의되어 있고 그쪽에서 읽어 사용한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import facts
from ..exceptions import ResponseSchemaDriftError
from ..models import IncomeStatement, TaxFiling
from ._base import ServiceBase

if TYPE_CHECKING:
    pass


def _require_list(
    data: dict[str, Any],
    key: str,
    *,
    action_id: str,
) -> list[Any]:
    """응답 dict 에서 list key 를 추출. 키 자체 없으면 drift.

    홈택스가 빈 결과를 "키 있고 빈 리스트" 로 보내든 "키 없음" 으로 보내든,
    "키 없음" 은 응답 구조 변경 신호이므로 silent 흡수하지 않는다 — 자료가
    실제로 0건일 때와 라이브러리가 모르는 구조 변경을 구분하기 위함.
    """
    if key not in data:
        raise ResponseSchemaDriftError(
            action_id=action_id, missing=[key], raw=data,
        )
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ResponseSchemaDriftError(
            action_id=action_id, missing=[f"{key} (list 가 아님)"], raw=data,
        )
    return value


class InquiryService(ServiceBase):
    """조회 액션들의 thin wrapper."""

    # ------------------------------------------------------------------ #
    # 지급명세서(원천징수 내역)                                            #
    # ------------------------------------------------------------------ #

    def income_statements(
        self,
        attr_year: int | str,
        *,
        material_kind_cd: str = "",
        ntpl_crp_cl_cd: str = "01",
    ) -> list[IncomeStatement]:
        """지급명세서(원천징수 내역) 조회.

        Args:
            attr_year: 귀속연도. ``int`` 또는 4자리 문자열.
            material_kind_cd: 자료종류 필터. 빈문자열이면 전체.
            ntpl_crp_cl_cd: 납세자 분류. ``"01"`` = 개인.

        Returns:
            ``IncomeStatement`` 리스트. 자료가 없으면 빈 리스트.
        """
        spec = facts.lookup(
            "services", "inquiries", "income_statements",
        )
        tin = self._ensure_tin()
        body = {
            "ieTin": tin,
            "ntplCrpClCd": ntpl_crp_cl_cd,
            "tin": "",
            "attrYr": str(attr_year),
            "mateKndCd": material_kind_cd,
        }
        data = self._c.wq_action(
            action_id=spec["action_id"],
            screen_id=spec["screen_id"],
            host=spec["host"],
            body=body,
        )
        items = _require_list(
            data, spec["items_key"], action_id=spec["action_id"],
        )
        return [IncomeStatement.from_dict(item) for item in items]

    # ------------------------------------------------------------------ #
    # 세금신고내역                                                         #
    # ------------------------------------------------------------------ #

    def tax_filings(
        self,
        *,
        start: str,
        end: str,
        ntpl_crp_cl_cd: str = "01",
    ) -> list[TaxFiling]:
        """세금신고내역 조회 (모든 세목 통합).

        Args:
            start: 신고일 시작 (``YYYYMMDD``).
            end: 신고일 종료 (``YYYYMMDD``).
            ntpl_crp_cl_cd: 납세자 분류. ``"01"`` = 개인.
        """
        spec = facts.lookup("services", "inquiries", "tax_filings")
        tin = self._ensure_tin()
        body = {
            "tin": tin,
            "ntplCrpClCd": ntpl_crp_cl_cd,
            "rtnDtSrt": start,
            "rtnDtEnd": end,
        }
        data = self._c.wq_action(
            action_id=spec["action_id"],
            screen_id=spec["screen_id"],
            host=spec["host"],
            body=body,
        )
        items = _require_list(
            data, spec["items_key"], action_id=spec["action_id"],
        )
        return [TaxFiling.from_dict(item) for item in items]

    # ------------------------------------------------------------------ #
    # raw 통로                                                            #
    # ------------------------------------------------------------------ #

    def raw_income_statements(
        self,
        attr_year: int | str,
        *,
        material_kind_cd: str = "",
        ntpl_crp_cl_cd: str = "01",
    ) -> dict[str, Any]:
        """``income_statements`` 와 동일한 호출이지만 raw dict 반환.

        라이브러리가 알지 못하는 새 필드까지 전부 보존한다. 응답 shape 이
        바뀌었을 때 호출자가 직접 우회하는 용도.
        """
        spec = facts.lookup(
            "services", "inquiries", "income_statements",
        )
        tin = self._ensure_tin()
        body = {
            "ieTin": tin,
            "ntplCrpClCd": ntpl_crp_cl_cd,
            "tin": "",
            "attrYr": str(attr_year),
            "mateKndCd": material_kind_cd,
        }
        return self._c.wq_action(
            action_id=spec["action_id"],
            screen_id=spec["screen_id"],
            host=spec["host"],
            body=body,
        )
