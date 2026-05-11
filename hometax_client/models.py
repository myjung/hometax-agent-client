"""응답 데이터 모델.

캡처에서 관찰된 필드 위주로 dataclass 화. 모든 dataclass 는 ``raw`` 필드를
들고 있어서, 라이브러리가 알지 못하는 새 필드도 호출자가 직접 꺼내 쓸 수
있다. 홈택스가 응답 shape 을 바꿔도 핵심 필드만 ``None`` 이 되고 raw 는
보존된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionInfo:
    """``sessionMap`` 응답에서 추출한 사용자 식별 정보."""

    user_id: str | None
    user_name: str | None
    tin: str | None
    pubc_user_no: str | None
    txpr_dscm_no: str | None       # 마스킹된 주민번호 (예: "990101*******")
    user_class_cd: str | None      # lgnUserClCd: 01=회원, 02=비회원
    user_cert_cl_cd: str | None
    cert_uqno: str | None          # crtfUqno: 인증 수단 흔적
    client_ip: str | None
    raw: dict[str, Any]

    @classmethod
    def from_session_map(cls, sm: dict[str, Any]) -> SessionInfo:
        return cls(
            user_id=sm.get("userId"),
            user_name=sm.get("userNm"),
            tin=sm.get("tin"),
            pubc_user_no=sm.get("pubcUserNo"),
            txpr_dscm_no=sm.get("txprDscmNo"),
            user_class_cd=sm.get("lgnUserClCd"),
            user_cert_cl_cd=sm.get("userCertClCd"),
            cert_uqno=sm.get("crtfUqno"),
            client_ip=sm.get("lgnClientIp"),
            raw=dict(sm),
        )

    @property
    def is_guest(self) -> bool:
        """비회원 세션 여부.

        ``lgnUserClCd == "02"`` 가 비회원 시그니처 (검증일 2026-05-11,
        ``docs/hometax-facts.md §16``). 비회원 세션은 종소세 신고도움 등
        일부 메뉴만 접근 가능 — 호출 전에 거르고 사용자에게 안내할 수 있게
        한다. 회원=``"01"``.

        ``user_class_cd`` 가 ``None`` 이면 ``False`` (보수적 default — 회원
        가정). raw sessionMap 안에 필드가 들어오지 않은 응답이면 호출자가
        ``raw.get("lgnUserClCd")`` 로 직접 확인.
        """
        return self.user_class_cd == "02"


@dataclass(frozen=True)
class IncomeStatement:
    """지급명세서 한 건 — ``ATXPPBAA001R16`` 의 ``dsdEtcSbmsBrkdNtplDVOList`` 항목."""

    attr_year: str | None
    material_kind_name: str | None  # mateKndNm
    payer_name: str | None          # sbmtNm
    payer_no: str | None            # sbmtNo
    payer_tin: str | None           # sbmtTin
    period_start: str | None        # txnrmStrtYm  YYYYMM
    period_end: str | None          # txnrmEndYm   YYYYMM
    receive_method: str | None      # rcatMthdCdNm
    cva_id: str | None              # 변환작업 ID
    apply_dtm: str | None           # cvaAplnDtm  YYYYMMDD
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IncomeStatement:
        return cls(
            attr_year=d.get("attrYr"),
            material_kind_name=d.get("mateKndNm"),
            payer_name=d.get("sbmtNm"),
            payer_no=d.get("sbmtNo"),
            payer_tin=d.get("sbmtTin"),
            period_start=d.get("txnrmStrtYm"),
            period_end=d.get("txnrmEndYm"),
            receive_method=d.get("rcatMthdCdNm"),
            cva_id=d.get("cvaId"),
            apply_dtm=d.get("cvaAplnDtm"),
            raw=dict(d),
        )


@dataclass(frozen=True)
class TaxFiling:
    """세금신고내역 한 건 — ``ATXPPBAA001R15`` 의 ``myntsTaxRtnBrkdDVOList`` 항목.

    ``*Amt`` / ``*Txamt`` 필드들은 상황별로 채워지는 값이 다르다. 산출세액은
    보통 ``computed_tax`` (stasAmt) 에 들어 있고, ``cmptTxamt`` 는 종종
    ``None`` 으로 비어 있다.
    """

    period_ym: str | None              # txnrmYm "YYYYMM"
    return_kind_name: str | None       # rtnClNm  "정기(확정)" 등
    return_kind_detail: str | None     # rtnClDetailNm
    statement_kind_name: str | None    # stmnKndNm
    write_method_name: str | None      # stmnWrtMthdNm
    return_date: str | None            # rtnDt YYYYMMDD
    computed_tax: int | None           # stasAmt 산출세액
    final_tax: int | None              # cmptTxamt 결정세액 (보통 None)
    withholding_offset: int | None     # ogntxSbtrScpmTxamt 원천세 가산/차감
    return_cva_id: str | None
    interface_cd: str | None           # itrfCd
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaxFiling:
        return cls(
            period_ym=d.get("txnrmYm"),
            return_kind_name=d.get("rtnClNm"),
            return_kind_detail=d.get("rtnClDetailNm"),
            statement_kind_name=d.get("stmnKndNm"),
            write_method_name=d.get("stmnWrtMthdNm"),
            return_date=d.get("rtnDt"),
            computed_tax=d.get("stasAmt"),
            final_tax=d.get("cmptTxamt"),
            withholding_offset=d.get("ogntxSbtrScpmTxamt"),
            return_cva_id=d.get("rtnCvaId"),
            interface_cd=d.get("itrfCd"),
            raw=dict(d),
        )
