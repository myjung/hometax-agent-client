"""홈택스 코드 매핑 — 캡처 + 메뉴트리에서 추출한 의미 사전.

값 자체보다는 응답에 들어 있는 코드값의 의미를 디버깅 / 로깅 시 풀어 보기
위한 보조 자료. 라이브러리 동작은 이 매핑이 비어 있어도 정상 동작한다.
"""

from __future__ import annotations

from typing import Final

# 인터페이스 코드 — 세목/신고종류 식별. action body 의 ``itrfCd``.
ITRF_CD: Final[dict[str, str]] = {
    "10": "종합소득세",
    "14": "원천세",
    "31": "법인세",
    "41": "부가가치세",
    "51": "양도소득세",
    "65": "법인세 연결납세",
}

# 보안분류 코드 — ``bsafClCd``. 종소세는 004 가 일관됨.
BSAF_CL_CD: Final[dict[str, str]] = {
    "004": "종합소득세",
}

# 신고분류 코드 — ``rtnClCd``.
RTN_CL_CD: Final[dict[str, str]] = {
    "01": "정기신고",
    "03": "수정신고",
    "06": "경정청구",
}

# 인증 사용자 분류 — ``sessionMap.lgnUserClCd``.
LGN_USER_CL_CD: Final[dict[str, str]] = {
    "01": "개인 일반",
    "03": "고객(피수임자)",
}

# 인증 코드 — ``sessionMap.lgnCertCd``.
LGN_CERT_CD: Final[dict[str, str]] = {
    "01": "공인인증서/카카오 등 OACX 인증",
    "02": "ID/PW",
    "05": "비로그인 가능 메뉴",
}

# OACX provider 목록 — 2026-04 캡처 기준.
OACX_PROVIDERS: Final[dict[str, str]] = {
    "kakao_v1.5": "카카오",
    "kakaobank_v1.5": "카카오뱅크",
    "naver_v1.5": "네이버",
    "toss_v1.5": "토스",
    "banksalad_v1.5": "뱅크샐러드",
    "pass_v1.5": "통신사패스",
    "kica_v1.5": "삼성패스 (SignGate)",
    "kb_v1.5": "KB은행",
    "nh_prod": "NH인증서",
    "hana_v1.5": "하나은행",
    "shinhan_v1.5": "신한인증서",
    "woori_v1.5": "우리인증서",
    "nice_v1.5": "나이스 (본인확인)",
}

# 세션 유지에 필수적인 쿠키들. UI 부가 쿠키(recentConnectMenuInfo 등)는
# 한글이 들어 있어 latin-1 인코딩 충돌을 일으키므로 제외한다.
#
# 시스템별 sessionID 9개는 2026-04-30 직접 호출로 확정된 목록. 신규
# 서브시스템이 등장하면 추가 필요 (응답 set-cookie 의 ``{NAME}sessionID``
# 패턴 관찰).
ESSENTIAL_COOKIES: Final[frozenset[str]] = frozenset({
    "JSESSIONID",
    # 시스템별 sessionID — 각 서브도메인의 wqAction.do 가 발급
    "TXPPsessionID",   # hometax.go.kr (메인 포털)
    "TEHTsessionID",   # teht.hometax.go.kr (세무대리/신고/자료)
    "TEETsessionID",   # teet.hometax.go.kr (전자세금계산서)
    "TEYSsessionID",   # teys.hometax.go.kr (연말정산)
    "TEWEsessionID",   # tewe.hometax.go.kr (소득자료)
    "TEWFsessionID",   # tewf.hometax.go.kr (근로/자녀 장려금)
    "TECRsessionID",   # tecr.hometax.go.kr (현금영수증)
    # 공통
    "NTS_LOGIN_SYSTEM_CODE_P",
    "NTS_REQUEST_SYSTEM_CODE_P",
    "NetFunnel_ID",
    "WMONID",
    "gdnpInfr",
    "TMPR_MAIN",
})

# 서브시스템 호스트 별칭 — 새 서비스 추가 시 여기에 한 줄 등록.
SUBSYSTEM_HOSTS: Final[dict[str, str]] = {
    "hometax": "hometax.go.kr",
    "teht": "teht.hometax.go.kr",
    "teet": "teet.hometax.go.kr",
    "teys": "teys.hometax.go.kr",
    "tewe": "tewe.hometax.go.kr",
    "tewf": "tewf.hometax.go.kr",
    "tecr": "tecr.hometax.go.kr",
    "mob": "mob.hometax.go.kr",
}
