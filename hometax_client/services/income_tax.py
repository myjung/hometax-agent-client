"""종합소득세 신고도움 서비스 (HomeTax 내부 식별자: ``agitx``).

홈택스가 종소세 신고도움 서비스 영역의 응답 필드/URL prefix 에 ``agitx`` 를
사용한다 (예: ``agitxRtnInqrDVOList``, ``agitx_index``, ``agitxCalYn``).
모듈 이름은 의미 우선으로 ``income_tax`` 로 두고, 응답 필드 이름은 와이어
무변형 원칙에 따라 그대로 유지한다.

이 서비스는 다음 화면을 다룬다.

- ``UWEICAAD32`` (TEWE): ``(간이, 용역) 본인 소득내역 조회`` — 자료구분별 그리드
- ``UWEICZAA92`` (TEWE): 위 데이터의 ClipReport HTML/PDF/Excel 출력
- ``UTERNAAT32`` (TEHT): 종합소득세 신고도움 서비스 신고안내문 데이터 + 미리보기
- ``UTERNAAD71`` (TEHT): 연금/건강/고용/산재 보험료 조회

라이브러리는 **데이터(dict / dataclass) 만 반환**한다. PDF/Excel 렌더링이나
디스크 저장은 워크플로 계층의 책임이며, 본 모듈에는 포함되지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .. import facts
from ..crypto import nts_report_signature
from ..exceptions import (
    ResponseSchemaDriftError,
    UnknownResponseError,
    WqActionFailedError,
)
from ._base import ServiceBase
from ._clipreport import ClipReportResult, export_pdf_from_html

if TYPE_CHECKING:
    pass


# ------------------------------------------------------------------ #
# Hosts / referers                                                   #
# ------------------------------------------------------------------ #

TEWE_HOST = "tewe.hometax.go.kr"
TEHT_HOST = "teht.hometax.go.kr"

INCOME_POPUP_REFERER = (
    f"https://{TEWE_HOST}/websquare/popup.html"
    f"?w2xPath=https://{TEWE_HOST}/ui/ic/a/a/d/UWEICAAD32.xml"
)
REPORT_POPUP_REFERER = (
    f"https://{TEWE_HOST}/websquare/popup.html"
    f"?w2xPath=https://{TEWE_HOST}/ui/ic/z/a/a/UWEICZAA92.xml"
)
FILING_HELP_REFERER = (
    f"https://{TEHT_HOST}/websquare/websquare.html"
    f"?w2xPath=/ui/rn/a/a/a/a/UTERNAAT32.xml"
)
INSURANCE_REFERER = (
    f"https://{TEHT_HOST}/websquare/websquare.html"
    f"?w2xPath=/ui/rn/a/a/a/a/UTERNAAD71.xml"
)


# ------------------------------------------------------------------ #
# Insurance dataset shapes                                           #
# ------------------------------------------------------------------ #

INSURANCE_DATASETS: tuple[tuple[str, str], ...] = (
    ("pplHifeRgnSbsr", "국민건강보험료 납세자"),
    ("pplHifeBman", "국민건강보험료 사업자"),
    ("pplPnsnInfee", "국민연금보험료"),
    ("empInfee", "고용보험료"),
    ("indsDsstInfee", "산재보험료"),
)


# ------------------------------------------------------------------ #
# Address probe field tables                                          #
# ------------------------------------------------------------------ #

ADDRESS_FIELD_KEYS: frozenset[str] = frozenset({
    "zip",
    "roadNmAdr",
    "ldAdr",
    "roadBscAdr",
    "ldBscAdr",
    "objpTlcAdr",
    "bldFlorAdr",
    "banAdr",
    "hoAdr",
    "bldBlckAdr",
    "bldSnoAdr",
    "bldPmnoAdr",
    "tongAdr",
    "bldDnadr",
    "bunjAdr",
    "bldHoAdr",
    "etcDadr",
})

ADDRESS_FIELD_PRIORITY: tuple[str, ...] = (
    "roadNmAdr",
    "roadBscAdr",
    "ldAdr",
    "ldBscAdr",
    "objpTlcAdr",
    "bunjAdr",
    "bldDnadr",
    "bldHoAdr",
    "hoAdr",
)


# ------------------------------------------------------------------ #
# MaterialKind catalog                                                #
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class MaterialKind:
    """``(간이, 용역) 본인 소득내역 조회`` 의 자료구분 한 행.

    홈택스 와이어에서 ``mateKndCd`` 로 식별된다.
    """

    code: str
    name: str
    action_id: str


def _load_material_kinds() -> tuple[MaterialKind, ...]:
    rows = facts.lookup(
        "services", "income_tax", "material_kinds",
    )
    return tuple(
        MaterialKind(
            code=row["code"],
            name=row["name"],
            action_id=row["action_id"],
        )
        for row in rows
    )


MATERIAL_KINDS: tuple[MaterialKind, ...] = _load_material_kinds()


# ------------------------------------------------------------------ #
# Service                                                            #
# ------------------------------------------------------------------ #

class IncomeTaxService(ServiceBase):
    """종합소득세 신고도움 서비스 영역.

    인증 등급: ID/PW 세션으로 호출 가능 (TEWE/TEHT 활성화 필요).
    """

    # ---------------- 소득내역 ----------------

    def income_details(
        self,
        attr_year: int | str,
        *,
        page_size: int = 100,
        material_kinds: tuple[MaterialKind, ...] = MATERIAL_KINDS,
    ) -> dict[str, Any]:
        """``(간이, 용역) 본인 소득내역 조회`` — 자료구분별 그리드 합본 dict.

        Returns:
            ``{"screen_id", "attr_year", "items", "groups"}`` 형태. ``items``
            는 자료구분 표시(``_materialKindCode``, ``_materialKindName``)가
            추가된 평탄 리스트. ``groups[code]`` 는 자료구분별 raw dict.
        """
        income_screen = facts.lookup(
            "services", "income_tax", "income_screen_id",
        )
        self._ensure_tin()
        self._c.activate_tewe_session(
            screen_id=income_screen,
            popup=True,
            referer=INCOME_POPUP_REFERER,
        )
        year = str(attr_year)
        out: dict[str, Any] = {
            "screen_id": income_screen,
            "attr_year": year,
            "items": [],
            "groups": {},
        }
        for kind in material_kinds:
            group = self._fetch_material_kind(
                kind, year=year, page_size=page_size, screen=income_screen,
            )
            out["groups"][kind.code] = group
            for row in group["items"]:
                enriched = dict(row)
                enriched["_materialKindCode"] = kind.code
                enriched["_materialKindName"] = kind.name
                out["items"].append(enriched)
        return out

    def report_html(
        self,
        attr_year: int | str,
        *,
        material_codes: str = "F0025,A0162,A0165",
    ) -> dict[str, Any]:
        """ClipReport 미리보기 HTML 한 덩어리 + raw export key 반환.

        Returns:
            ``{"html", "real_codes"}`` — ``html`` 은 미리보기 HTML
            (이후 PDF/Excel export 에 사용 가능), ``real_codes`` 는 홈택스가
            보정한 자료구분 코드.
        """
        report_screen = facts.lookup(
            "services", "income_tax", "report_screen_id",
        )
        self._ensure_tin()
        self._c.activate_tewe_session(
            screen_id=report_screen,
            popup=True,
            referer=REPORT_POPUP_REFERER,
        )
        year = str(attr_year)
        real_codes = self._fetch_report_material_codes(
            year, material_codes, screen=report_screen,
        )
        html = self._fetch_report_html(
            year,
            material_codes=material_codes,
            real_codes=real_codes,
            screen=report_screen,
        )
        return {"html": html, "real_codes": real_codes}

    # ---------------- 신고안내문 ----------------

    def filing_help_data(self, attr_year: int | str) -> dict[str, Any]:
        """신고안내문 raw 응답 ('ekopIcmAmtTrtDVO' + 안내메시지 등)."""
        screen = facts.lookup(
            "services", "income_tax", "filing_help_screen_id",
        )
        action = facts.lookup(
            "services", "income_tax", "filing_help_action",
        )
        self._ensure_tin()
        self._c.activate_subsystem_session(
            host=TEHT_HOST,
            screen_id=screen,
            popup=False,
            referer=FILING_HELP_REFERER,
        )
        return self._fetch_filing_help_data(
            str(attr_year), screen=screen, action=action,
        )

    def filing_help_html(self, attr_year: int | str) -> str:
        """신고안내문 ClipReport 미리보기 HTML 반환."""
        data = self.filing_help_data(attr_year)
        return self._fetch_filing_help_html(str(attr_year), data)

    def filing_help_pdf(
        self, attr_year: int | str,
    ) -> "ClipReportResult":
        """신고안내문 공식 PDF bytes (ClipReport R09 export).

        2단계: 미리보기 HTML → ``reportkey`` 추출 → ``ClipReport4/Clip.jsp``
        R03 polling + R09 export. 결과의 ``status`` 분기:

        - ``"found"``: ``result.pdf`` 가 PDF bytes.
        - ``"empty"``: HTML 에 reportkey 없거나 page count 0 또는 R09 가
          PDF 가 아닌 응답. 사용자 계정의 해당 연도 자료가 없는 정상 케이스.
        - ``"failed"``: HTTP 4xx/5xx 등 wire 실패.

        라이브러리는 PDF bytes 만 반환 — 디스크 저장 / 파일명 / 폴더 구조는
        호출자 (워크플로) 책임 (라이브러리 정책).

        라이브 검증 2026-05-11: 비회원 OACX 세션으로 5페이지 200KB PDF.
        """
        html = self.filing_help_html(attr_year)
        return export_pdf_from_html(
            self._c._session,
            html,
            file_name=f"filing_help_{attr_year}.pdf",
        )

    def report_pdf(
        self,
        attr_year: int | str,
        *,
        material_codes: str = "F0025,A0162,A0165",
    ) -> "ClipReportResult":
        """(간이/용역) 본인 소득내역 보고서 공식 PDF bytes.

        ``report_html`` 의 HTML 응답에서 reportkey 추출 → ClipReport R03/R09.
        분기 / 정책은 :meth:`filing_help_pdf` 와 동일.
        """
        bundle = self.report_html(
            attr_year, material_codes=material_codes,
        )
        return export_pdf_from_html(
            self._c._session,
            bundle["html"],
            file_name=f"income_report_{attr_year}.pdf",
        )

    # ---------------- 보험료 ----------------

    def insurance_premiums(
        self, attr_year: int | str,
    ) -> dict[str, Any]:
        """국민건강/연금/고용/산재 보험료 조회 결과 dict."""
        screen = facts.lookup(
            "services", "income_tax", "insurance_screen_id",
        )
        self._ensure_tin()
        self._c.activate_subsystem_session(
            host=TEHT_HOST,
            screen_id=screen,
            popup=False,
            referer=INSURANCE_REFERER,
        )
        year = str(attr_year)
        taxpayer = self._fetch_insurance_taxpayer(self._c.tin or "", screen)
        taxpayer_dvo = taxpayer.get("ttiabam001DVO") or {}
        taxpayer_tin = str(
            taxpayer_dvo.get("tin") or self._c.tin or "",
        )
        taxpayer_name = str(
            taxpayer_dvo.get("txprNm") or taxpayer.get("txprNm") or "",
        )

        initial = self._fetch_insurance_summary(
            year, taxpayer_tin, bman_tin="", screen=screen,
        )
        business_rows = list(initial.get("bsnoList") or [])
        businesses: list[dict[str, Any]] = []
        seen_tins: set[str] = set()
        for row in business_rows:
            bman_tin = str(row.get("bmanTin") or "").strip()
            if not bman_tin or bman_tin in seen_tins:
                continue
            seen_tins.add(bman_tin)
            detail = self._fetch_insurance_summary(
                year, taxpayer_tin, bman_tin=bman_tin, screen=screen,
            )
            businesses.append({
                "bsno": row.get("bsno") or "",
                "bman_tin": bman_tin,
                "detail": detail,
            })

        return {
            "screen_id": screen,
            "attr_year": year,
            "taxpayer_name": taxpayer_name,
            "taxpayer_tin": taxpayer_tin,
            "initial": initial,
            "businesses": businesses,
        }

    # ---------------- 주소 후보 ----------------

    def address_candidates(
        self, attr_year: int | str,
    ) -> dict[str, Any]:
        """추가 인증이 필요 없는 화면들에서 주소 필드를 찾아 후보 dict 반환.

        주된 워크플로를 깨지 않게 하기 위해 각 source 호출이 실패해도 raise
        하지 않고 ``sources`` 리스트에 상태를 기록한다.
        """
        if not self._c.tin:
            try:
                self._c.session_info()
            except Exception:
                pass
        if not self._c.tin:
            return {
                "status": "failed",
                "message": "홈택스 내부 식별번호를 확인하지 못했습니다.",
                "candidates": [],
                "sources": [],
                "skipped_sources": [],
            }

        year = str(attr_year)
        candidates: list[dict[str, str]] = []
        sources: list[dict[str, Any]] = []

        taxpayer_basic = facts.lookup(
            "services", "address", "taxpayer_basic_info",
        )
        filing_help_screen = facts.lookup(
            "services", "income_tax", "filing_help_screen_id",
        )
        filing_help_action = facts.lookup(
            "services", "income_tax", "filing_help_action",
        )
        insurance_screen = facts.lookup(
            "services", "income_tax", "insurance_screen_id",
        )
        insurance_taxpayer_action = facts.lookup(
            "services", "income_tax", "insurance_taxpayer_action",
        )

        self._probe_address_source(
            sources=sources,
            candidates=candidates,
            label="세적 기본 단건 조회",
            screen_id=taxpayer_basic["screen_id"],
            action_id=taxpayer_basic["action_id"],
            fetch=self._fetch_taxpayer_basic_info,
        )
        self._probe_address_source(
            sources=sources,
            candidates=candidates,
            label="연금건강고용산재보험료 납세자 조회",
            screen_id=insurance_screen,
            action_id=insurance_taxpayer_action,
            fetch=lambda: (
                self._activate_teht(insurance_screen, INSURANCE_REFERER)
                or self._fetch_insurance_taxpayer(
                    self._c.tin or "", insurance_screen,
                )
            ),
        )
        self._probe_address_source(
            sources=sources,
            candidates=candidates,
            label="종합소득세 신고도움서비스",
            screen_id=filing_help_screen,
            action_id=filing_help_action,
            fetch=lambda: (
                self._activate_teht(filing_help_screen, FILING_HELP_REFERER)
                or self._fetch_filing_help_data(
                    year,
                    screen=filing_help_screen,
                    action=filing_help_action,
                )
            ),
        )

        road = _first_address_candidate(
            candidates, {"roadNmAdr", "roadBscAdr"},
        )
        lot = _first_address_candidate(candidates, {"ldAdr", "ldBscAdr"})
        zip_code = _first_address_candidate(candidates, {"zip"})
        full_road_address = (
            _full_address_from_candidate(road, candidates) if road else ""
        )
        best = road or _best_address_candidate(candidates)

        if best:
            status = "found"
            message = "주소 후보값을 찾았습니다."
        elif any(
            source.get("status") == "auth_required" for source in sources
        ):
            status = "auth_required"
            message = (
                "추가 인증이 필요한 조회는 건너뛰었고, 일반 조회에서는 "
                "주소값을 찾지 못했습니다."
            )
        elif sources and all(
            source.get("status") == "failed" for source in sources
        ):
            status = "failed"
            message = "주소 후보 탐색 중 오류가 발생했습니다."
        else:
            status = "empty"
            message = "주소 후보 필드는 확인했지만 값이 비어 있습니다."

        return {
            "status": status,
            "message": message,
            "best_field": best.get("path", "") if best else "",
            "best_value": (
                full_road_address
                or (best.get("value", "") if best else "")
            ),
            "road_address": (
                full_road_address
                or (road.get("value", "") if road else "")
            ),
            "road_address_field": road.get("path", "") if road else "",
            "lot_address": lot.get("value", "") if lot else "",
            "lot_address_field": lot.get("path", "") if lot else "",
            "zip_code": zip_code.get("value", "") if zip_code else "",
            "candidates": candidates,
            "sources": sources,
            "skipped_sources": [
                {
                    "label": "대민사용자 기본정보조회",
                    "screen_id": "UTXPPBBA20",
                    "action_id": "ATXPPAAA001R22",
                    "reason": "추가 인증이 필요한 화면이라 건너뜀",
                }
            ],
        }

    # ------------------------------------------------------------------ #
    # 내부 — 소득내역                                                     #
    # ------------------------------------------------------------------ #

    def _fetch_material_kind(
        self,
        kind: MaterialKind,
        *,
        year: str,
        page_size: int,
        screen: str,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        page_num = 1
        total_count: int | None = None
        last_msg = ""

        while True:
            body = {
                "searchVO": self._income_search_body(kind.code, year),
                "pageInfoVO": {
                    "pageNum": str(page_num),
                    "pageSize": str(page_size),
                    "totalCount": (
                        "" if total_count is None else str(total_count)
                    ),
                },
            }
            data = self._c.wq_action(
                action_id=kind.action_id,
                screen_id=screen,
                body=body,
                host=TEWE_HOST,
                real_screen_id=screen,
                popup=True,
                referer=INCOME_POPUP_REFERER,
            )
            rm = data.get("resultMsg") or {}
            last_msg = rm.get("msg") or ""
            if "gridList01" not in data:
                raise ResponseSchemaDriftError(
                    action_id=kind.action_id,
                    missing=["gridList01"],
                    raw=data,
                )
            page_items = list(data.get("gridList01") or [])
            items.extend(page_items)

            page_info = data.get("pageInfoVO") or {}
            total_count = _to_int(
                page_info.get("totalCount"), total_count,
            )
            if not page_items:
                break
            if total_count is not None and len(items) >= total_count:
                break
            if len(page_items) < page_size:
                break
            page_num += 1

        return {
            "material_kind_code": kind.code,
            "material_kind_name": kind.name,
            "action_id": kind.action_id,
            "message": last_msg,
            "total_count": (
                total_count if total_count is not None else len(items)
            ),
            "items": items,
        }

    def _income_search_body(
        self, material_code: str, year: str,
    ) -> dict[str, str]:
        return {
            "mateKndCd": material_code,
            "baseYr": "",
            "trgtYrCl": "attrYr",
            "strtBaseYr": year,
            "endBaseYr": year,
            "servClCd": "all",
            "incClCd": "",
            "bsicTfbCd": "",
            "lvyRperNo": "",
            "lvyRperNm": "",
            "lvyRperTin": "",
            "ieNo": "",
            "ieNm": "",
            "ieTin": self._c.tin or "",
            "agitxCalYn": "Y",
            "ntplInfpYn": "Y",
        }

    def _fetch_report_material_codes(
        self, year: str, material_codes: str, *, screen: str,
    ) -> str:
        action = facts.lookup(
            "services", "income_tax", "report_codes_action",
        )
        body = {
            "trgtCl": "attr",
            "ieTin": self._c.tin or "",
            "lvyRperTin": "",
            "strtBaseYr": year,
            "strtBaseMm": "01",
            "endBaseYr": year,
            "endBaseMm": "12",
            "mateKndCd": material_codes,
            "realMateKndCd": "",
            "ntplInfpYn": "Y",
            "screenId": screen,
            "grdLvyRperList": [],
        }
        data = self._c.wq_action(
            action_id=action,
            screen_id=screen,
            body=body,
            host=TEWE_HOST,
            real_screen_id=screen,
            popup=True,
            referer=REPORT_POPUP_REFERER,
        )
        return str(data.get("realMateKndCd") or material_codes)

    def _fetch_report_html(
        self,
        year: str,
        *,
        material_codes: str,
        real_codes: str,
        screen: str,
    ) -> str:
        action = facts.lookup(
            "services", "income_tax", "report_html_action",
        )
        b, bb = nts_report_signature(action)
        tewe_cookie = self._cookie_value("TEWEsessionID")
        req_params = {
            "lvyRperTin": "",
            "ieTin": self._c.tin or "",
            "mateKndCd": material_codes,
            "trgtCl": "attr",
            "strtBaseYr": year,
            "strtBaseMm": "01",
            "endBaseYr": year,
            "endBaseMm": "12",
            "screenId": screen,
            "ntplInfpYn": "Y",
            "actionId": action,
            "voSepChar": "|",
            "dataSepChar": ",",
            "valSepChar": ":",
            "useType": "clip",
            "b": b,
            "bb": bb,
        }
        param = {
            "options": {
                "visibles": {
                    "open": 0,
                    "export": 1,
                    "exportxls": 1,
                    "exporthwp": 1,
                    "exportpdf": 1,
                },
                "fileNames": {"all": "detail_report"},
                "renderingMode": "client",
            },
            "type": "S",
            "fileName": "tt/ic/z/a/RWIICZA600",
            "xpath": "{%dataset.xml.root%}",
            "actionId": action,
            "con": "RWIICZA600",
            "viewType": "frame",
            "frameName": f"iframe2_{screen}",
            "removeChar": True,
            "rptSort": "HTML",
            "reqParams": req_params,
            "rptParams": _report_kind_params(real_codes),
            "targetWas": f"https://{TEWE_HOST}",
            "multiple": False,
            "width": 750,
            "height": 780,
            "secure": None,
            "cookie": (
                f"TEWEsessionID={tewe_cookie};" if tewe_cookie else ""
            ),
            "datatype": "json",
        }
        resp = self._c._session.post(
            "https://sesw.hometax.go.kr/serp/clipreport.do",
            data={
                "param": json.dumps(
                    param, ensure_ascii=False, separators=(",", ":"),
                ),
            },
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;"
                          "q=0.9,*/*;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": f"https://{TEWE_HOST}",
                "Referer": f"https://{TEWE_HOST}/",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            raise UnknownResponseError(
                f"ClipReport failed: HTTP {resp.status_code}"
            )
        return resp.text

    # ------------------------------------------------------------------ #
    # 내부 — 신고안내문                                                   #
    # ------------------------------------------------------------------ #

    def _fetch_filing_help_data(
        self, year: str, *, screen: str, action: str,
    ) -> dict[str, Any]:
        data = self._c.wq_action(
            action_id=action,
            screen_id=screen,
            body={
                "attrYr": year,
                "gridNo": "",
                "screenId": screen,
                "tin": self._c.tin or "",
            },
            host=TEHT_HOST,
            real_screen_id=screen,
            popup=False,
            referer=FILING_HELP_REFERER,
        )
        if not data.get("ekopIcmAmtTrtDVO"):
            raise ResponseSchemaDriftError(
                action_id=action,
                missing=["ekopIcmAmtTrtDVO"],
                raw=data,
            )
        return data

    def _fetch_filing_help_html(
        self, year: str, data: dict[str, Any],
    ) -> str:
        action = facts.lookup(
            "services", "income_tax", "filing_help_action",
        )
        screen = facts.lookup(
            "services", "income_tax", "filing_help_screen_id",
        )
        b, bb = nts_report_signature(action)
        teht_cookie = self._cookie_value("TEHTsessionID")
        ekop = data.get("ekopIcmAmtTrtDVO") or {}
        gdnc_msg = str(
            (data.get("srmhGdncMsgCntnDVO") or {}).get("gdncMsgCntn") or "",
        )
        gdnc_msg = gdnc_msg.replace("<br/>", "\n").replace("<br>", "\n")
        req_params = {
            "tin": self._c.tin or "",
            "attrYr": year,
            "rptGb": "Y",
            "screenId": screen,
            "actionId": action,
            "voSepChar": "|",
            "dataSepChar": ",",
            "valSepChar": ":",
            "useType": "clip",
            "b": b,
            "bb": bb,
        }
        param = {
            "options": {
                "visibles": {
                    "open": 0,
                    "export": 1,
                    "exportxls": 0,
                    "exportpdf": 1,
                    "exporthwp": 0,
                },
                "exports": {},
                "fileNames": {"all": "신고 안내 정보"},
                "renderingMode": "client",
                "renderAtOneTime": True,
                "popWidth": 900,
                "printOptions": {"pdf": False, "html": True},
            },
            "viewType": "viewer",
            "type": "S",
            "fileName": "tt/rn/a/a/RTIRNAA541",
            "xpath": "{%dataset.xml.root%}",
            "actionId": action,
            "con": "RTIRNAA541",
            "removeChar": True,
            "rptSort": "HTML",
            "reqParams": req_params,
            "rptParams": {
                "rtnAtonTfbCdNm": ekop.get("rtnAtonTfbCdNm") or "",
                "rtnAtonTfbCd": ekop.get("rtnAtonTfbCd") or "",
                "rtnAtonTfbCdCntn": "",
                "gdncMsgCntn": gdnc_msg,
            },
            "targetWas": f"https://{TEHT_HOST}",
            "multiple": False,
            "width": 900,
            "height": 780,
            "secure": None,
            "cookie": (
                f"TEHTsessionID={teht_cookie};" if teht_cookie else ""
            ),
            "datatype": "json",
        }
        resp = self._c._session.post(
            "https://sesw.hometax.go.kr/serp/clipreport.do",
            data={
                "param": json.dumps(
                    param, ensure_ascii=False, separators=(",", ":"),
                ),
            },
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;"
                          "q=0.9,*/*;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": f"https://{TEHT_HOST}",
                "Referer": f"https://{TEHT_HOST}/",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            raise UnknownResponseError(
                f"ClipReport failed: HTTP {resp.status_code}"
            )
        return resp.text

    # ------------------------------------------------------------------ #
    # 내부 — 보험료                                                        #
    # ------------------------------------------------------------------ #

    def _fetch_insurance_taxpayer(
        self, tin: str, screen: str,
    ) -> dict[str, Any]:
        action = facts.lookup(
            "services", "income_tax", "insurance_taxpayer_action",
        )
        return self._c.wq_action(
            action_id=action,
            screen_id=screen,
            body={"tin": tin},
            host=TEHT_HOST,
            real_screen_id=screen,
            popup=False,
            referer=INSURANCE_REFERER,
        )

    def _fetch_insurance_summary(
        self,
        year: str,
        taxpayer_tin: str,
        *,
        bman_tin: str = "",
        screen: str,
    ) -> dict[str, Any]:
        action = (
            facts.lookup(
                "services",
                "income_tax",
                "insurance_summary_with_bman_action",
            )
            if bman_tin
            else facts.lookup(
                "services", "income_tax", "insurance_summary_action",
            )
        )
        return self._c.wq_action(
            action_id=action,
            screen_id=screen,
            body={
                "txyr": year,
                "tin": taxpayer_tin,
                "bmanTin": bman_tin,
                "txaaId": "",
                "bkpPrxRtnPrxClCd": "02",
            },
            host=TEHT_HOST,
            real_screen_id=screen,
            popup=False,
            referer=INSURANCE_REFERER,
        )

    # ------------------------------------------------------------------ #
    # 내부 — 주소 후보                                                    #
    # ------------------------------------------------------------------ #

    def _activate_teht(self, screen_id: str, referer: str) -> None:
        self._c.activate_subsystem_session(
            host=TEHT_HOST,
            screen_id=screen_id,
            popup=False,
            referer=referer,
        )

    def _probe_address_source(
        self,
        *,
        sources: list[dict[str, Any]],
        candidates: list[dict[str, str]],
        label: str,
        screen_id: str,
        action_id: str,
        fetch: Any,
    ) -> None:
        try:
            payload = fetch()
        except WqActionFailedError as exc:
            status = (
                "auth_required"
                if _looks_like_auth_required(exc.raw_msg or str(exc))
                else "failed"
            )
            sources.append({
                "label": label,
                "screen_id": screen_id,
                "action_id": action_id,
                "status": status,
                "message": exc.raw_msg or str(exc),
                "checked_count": 0,
                "found_count": 0,
            })
            return
        except Exception as exc:
            # Probing must not break the main workflow.
            sources.append({
                "label": label,
                "screen_id": screen_id,
                "action_id": action_id,
                "status": "failed",
                "message": str(exc) or exc.__class__.__name__,
                "checked_count": 0,
                "found_count": 0,
            })
            return

        found, checked_count = _collect_address_candidates(
            payload,
            source_label=label,
            screen_id=screen_id,
            action_id=action_id,
        )
        candidates.extend(found)
        sources.append({
            "label": label,
            "screen_id": screen_id,
            "action_id": action_id,
            "status": "found" if found else "empty",
            "message": (
                "주소 후보값 확인"
                if found
                else "주소 후보 필드는 있으나 값이 비어 있음"
            ),
            "checked_count": checked_count,
            "found_count": len(found),
        })

    def _fetch_taxpayer_basic_info(self) -> dict[str, Any]:
        spec = facts.lookup(
            "services", "address", "taxpayer_basic_info",
        )
        return self._c.wq_action(
            action_id=spec["action_id"],
            screen_id=spec["screen_id"],
            host=spec["host"],
            body={
                "tin": self._c.tin or "",
                "txprClsfCd": "01",
                "txprDscmNo": "",
                "txprDscmNoClCd": "",
                "txprDscmDt": "",
                "searchOrder": "",
                "outDes": "revrNtplBscInfrInqrDVO",
                "txprNm": "",
                "crpTin": "",
                "mntgTxprIcldYn": "",
                "resnoAltHstrInqrYn": "",
                "resnoAltHstrInqrBaseDtm": "",
                "sameBmanInqrYn": "N",
                "rpnBmanRetrYn": "N",
            },
            real_screen_id="",
            popup=False,
            referer=(
                "https://hometax.go.kr/websquare/websquare.html"
                "?w2xPath=/ui/pp/b/a/UTXPPBAD23.xml"
            ),
        )


# ------------------------------------------------------------------ #
# 모듈 헬퍼                                                            #
# ------------------------------------------------------------------ #

def _to_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _report_kind_params(material_codes: str) -> dict[str, str]:
    codes = {
        code.strip()
        for code in material_codes.split(",")
        if code.strip()
    }
    return {
        "DLLBR": "F0026" if "F0026" in codes else "",
        "SMPLBR": "A0161" if "A0161" in codes else "",
        "SMPBS": "A0162" if "A0162" in codes else "",
        "SMPETC": "A0165" if "A0165" in codes else "",
        "PFBIFMT": "F0025" if "F0025" in codes else "",
    }


def _collect_address_candidates(
    payload: Any,
    *,
    source_label: str,
    screen_id: str,
    action_id: str,
) -> tuple[list[dict[str, str]], int]:
    candidates: list[dict[str, str]] = []
    checked_count = 0

    def walk(value: Any, path: str) -> None:
        nonlocal checked_count
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key in ADDRESS_FIELD_KEYS:
                    checked_count += 1
                    text = _clean_address_value(child)
                    if text:
                        candidates.append({
                            "source": source_label,
                            "screen_id": screen_id,
                            "action_id": action_id,
                            "path": child_path,
                            "field": str(key),
                            "value": text,
                        })
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "")
    return candidates, checked_count


def _clean_address_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    text = str(value).strip()
    if not text or text in {"-", "--", "null", "None"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _best_address_candidate(
    candidates: list[dict[str, str]],
) -> dict[str, str] | None:
    if not candidates:
        return None
    priority = {
        field: index for index, field in enumerate(ADDRESS_FIELD_PRIORITY)
    }
    return min(
        candidates,
        key=lambda item: (
            priority.get(item.get("field", ""), len(priority) + 1),
            len(item.get("path", "")),
        ),
    )


def _first_address_candidate(
    candidates: list[dict[str, str]],
    fields: set[str],
) -> dict[str, str] | None:
    matches = [
        candidate
        for candidate in candidates
        if candidate.get("field") in fields
    ]
    if not matches:
        return None
    priority = {
        field: index for index, field in enumerate(ADDRESS_FIELD_PRIORITY)
    }
    return min(
        matches,
        key=lambda item: (
            priority.get(item.get("field", ""), len(priority) + 1),
            len(item.get("path", "")),
        ),
    )


def _full_address_from_candidate(
    base: dict[str, str] | None,
    candidates: list[dict[str, str]],
) -> str:
    if not base:
        return ""
    base_value = base.get("value", "").strip()
    if not base_value:
        return ""

    prefix = base.get("path", "").rsplit(".", 1)[0]
    by_field = {
        candidate.get("field", ""): candidate.get("value", "").strip()
        for candidate in candidates
        if candidate.get("path", "").rsplit(".", 1)[0] == prefix
    }
    parts = [base_value]
    detail_fields = (
        "bldBlckAdr",
        "bldDnadr",
        "bldFlorAdr",
        "bldHoAdr",
        "etcDadr",
    )
    for field in detail_fields:
        text = _address_detail_part(field, by_field.get(field, ""))
        if text and text not in parts and text not in base_value:
            parts.append(text)
    return " ".join(parts)


def _address_detail_part(field: str, value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    suffixes = {
        "bldDnadr": "동",
        "bldFlorAdr": "층",
        "bldHoAdr": "호",
    }
    suffix = suffixes.get(field, "")
    if suffix and not text.endswith(suffix):
        return f"{text}{suffix}"
    return text


def _looks_like_auth_required(message: str) -> bool:
    keywords = ("인증", "휴대폰", "신용카드", "IPIN", "지문", "보안카드")
    return any(keyword in message for keyword in keywords)
