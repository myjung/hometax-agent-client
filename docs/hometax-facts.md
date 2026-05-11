# 홈택스 사실 카탈로그 (Hometax Facts — SSOT)

이 파일은 홈택스(`hometax.go.kr`) 시스템에 대해 **캡처/실측으로 직접 검증된**
사실들의 단일 진실 출처(Single Source of Truth)입니다.

> **운영 룰**:
>
> - 추측·가설은 이 파일에 들이지 않습니다 (캡처/실측으로 검증된 것만).
> - 모든 항목은 출처 (캡처 디렉토리 / 코드 파일) + 검증 일자를 함께 적습니다.
> - 항목이 깨졌다는 신호가 있으면 갱신하고 변경 이력은 git log 에 남깁니다.

**검증 일자 표기**
원본 분석 캡처는 `prev/` (`/home/rey/Projects/hometax-analysis/captures/`,
이 프로젝트에는 미동기) 에 있습니다. 본 카탈로그의 **검증일** 은 해당 캡처가
수집된 날짜이며, 본 프로젝트 내에서 다시 재현할 때는 `tests/` 의 회귀 스크립트로
검증합니다.

---

## 1. 서브도메인 · WAS · host pool

검증 방법: 인증된 세션으로 각 서브도메인의 `wqAction.do` 를 직접 호출,
응답 `Set-Cookie` 헤더의 `{NAME}sessionID=...{pool}wsp{NN}_servlet_{시스템명}` 추출.
검증일: 2026-04-30 / 출처: `prev/captures/1777550891_subdomain_systemnames/`.

| 서브도메인 | WAS 시스템 | host pool | 도메인 코드 | 역할 |
|-----------|-----------|----------|-----------|------|
| `hometax.go.kr` | `TXPP02`, `GPINNEW01` | `tupi` | `pp`, `cm` | 메인 포털 (모든 사용자 진입점, 세션 발급, OACX 인증) |
| `teht.hometax.go.kr` | `TEHT04` | `tupi` | `rn`/`sf`/`ab`/`ca` 다수 | **세무사 작업 본진 + 일반인 신고 통합** |
| `tewe.hometax.go.kr` | `TEWE02` | **`wupi`** ← 유일 | `ic` | 일용/간이/용역 소득자료 + welfare 일부 |
| `teys.hometax.go.kr` | `TEYS01` | `tupi` | `ys` | 연말정산 전용 (1~2월 폭주 대응) |
| `teet.hometax.go.kr` | `TEET03` | `tupi` | `et` | 전자세금계산서 발급/관리 |
| `sesw.hometax.go.kr` | `SERP01` | `tupi` | `serp`, `secs` | 보고서 출력(ClipReport4) + 정부 표준 보안 모듈(Veraport20) |
| `tewf.hometax.go.kr` | `TEWF04` | `tupi` | `wf` | 근로/자녀 장려금 |
| `tecr.hometax.go.kr` | `TECR01` | `tupi` | `cr` | 현금영수증 |
| `apct.hometax.go.kr` | NetFunnel | — | — | 트래픽 큐 (단일 엔드포인트 `/ts.wseq`) |
| `hometax.speedycdn.net` | (CDN 풀) | — | — | 정적 자원. `server: NCE`, `via: NS-CACHE` 일관 |

**확정 결론**
- 9개 hometax 서브도메인 중 8개가 `tupi` pool, **`tewe` 만 `wupi` pool** 로 분리.
- 모든 서브도메인이 자체 WAS 시스템을 따로 운영.

## 2. 공식 시스템명 · 프로젝트 코드명

JS 헤더 주석에서 일관 등장. 검증일: 2026-04-30.

```
* System Name : 차세대 국세행정시스템
* Project Name : nts-td-web
```

`NTS` = National Tax Service. 프로젝트 코드명 `nts-td-web` (`td` 는 옛 도메인 코드 prefix).

## 3. 세션 · 쿠키 구조

검증일: 2026-04-30 / 출처: `prev/captures/1777550891_subdomain_systemnames/`.

- **`JSESSIONID`** = JEE 표준 세션 쿠키.
  형식: `{값}.tupiwsp{NN}_servlet_{시스템명}` 예) `....tupiwsp26_servlet_GPINNEW01`.
  suffix 는 **세션 어피니티(sticky session)** 용 — L7 로드밸런서가 같은 세션을 같은 WAS 인스턴스로 보냄.
- **`{SYSTEM}sessionID`** = 시스템별 자체 세션 쿠키.
  - `hometax.go.kr` 응답 → `TXPPsessionID`
  - `teht.hometax.go.kr` 응답 → `TEHTsessionID`
  - `sesw.hometax.go.kr` 응답 → 자체 sessionID 발급 안 함 (`WMONID` 만)
  - 모두 `.hometax.go.kr` 도메인 쿠키 → 모든 서브도메인이 같이 받아 보냄 (SSO).
- **공통 쿠키**: `WMONID`, `NTS_LOGIN_SYSTEM_CODE_P`, `NTS_REQUEST_SYSTEM_CODE_P`.

**확정 결론**
- 시스템 그룹: `TXPP`, `TEHT`, `SERP`, `GPINNEW` (4종 관측 — 더 있을 가능성).
- 인스턴스 번호 suffix: `_servlet_TEHT04`, `_servlet_TXPP02`, `_servlet_SERP01`, `_servlet_GPINNEW01` 등 — 각 그룹 안에도 다중 인스턴스.

### TEWE SSO activation (2026-05-02)

- ID/PW 로그인 직후에는 `TXPPsessionID`만으로 `tewe.hometax.go.kr`의 `wqAction.do` 조회가 실패한다.
- 브라우저 흐름처럼 `hometax.go.kr/token.do`에서 받은 `ssoToken`을
  `https://tewe.hometax.go.kr/permission.do?screenId={screenId}&domain=hometax.go.kr`
  에 `<map id="postParam"><ssoToken>...</ssoToken><popupYn>true</popupYn></map>` 형태로 POST하면 `TEWEsessionID`가 생성된다.
- `(간이, 용역) 본인 소득내역 조회` 화면 `UWEICAAD32`의 종합소득세 신고도움 호출 자료구분은 `F0025`, `A0162`, `A0165`이고 각각 `AWEICAAA019R09`, `AWEICAAA029R08`, `AWEICAAA027R09`를 호출한다.

## 4. 프레임워크 스택

검증일: 2026-04-30 / 출처: 추출 JS + 응답 본문.

- **Servlet 컨테이너**: `JSESSIONID` 쿠키 사용 → JEE 표준 (Tomcat/WebLogic/WebSphere 중 하나).
- **MVC**: 모든 액션 엔드포인트가 `.do` 매핑 → Spring MVC / Struts.
- **DAO/DTO**: 응답 객체명 `*DVO` (Data Value Object) 22종+ → MyBatis/iBatis 환경의 명명 관행.
  예: `bmanBscInfrInqrDVO`, `txprBscInfrInqrDVO`, `cvaIsnRstnInqrDVO`, `pubcUserInqrDVO`.
- **UI 프레임워크**: **Inswave WebSquare 5 (W5)**.
  - URL: `/websquare/websquare.html?w2xPath=...`
  - 화면 정의: `.wq` (XForms-XML), 컴파일 산출: AMD 모듈 `.js` (`define({declaration:..., E:[{T:1,N:'html',...}]})` 형태).
  - 표준 함수: `nts_doService`, `fn_chkOpenPage`, `scwin.action = {...}`.
  - `common_telc.js` 의 `////W5전환` 주석으로 W5 사용 확정. 옛 W4 코드는 주석으로 잔존.

## 5. 응답 캐시 / 로드밸런서

검증일: 2026-04-30 / 출처: 응답 헤더 일관성.

- **Citrix NetScaler** 사실상 확정. 헤더 패턴:
  ```
  server: NCE
  via: NS-CACHE-10.0:   8
  x-nce-cacheresult: HIT/MISS/...
  cache-control: max-age=N
  ```
- 모든 서브도메인 + CDN(`hometax.speedycdn.net`) 이 같은 헤더 패턴 → 같은 NetScaler 뒤.
- sticky session 도 NetScaler L7 처리.

## 6. 도메인 코드 ↔ 기능 매핑

`/ui/<코드>/...` URL 패턴 + 메뉴 트리(1004개) 직접 추출. 검증일: 2026-04-30.

| 코드 | 메뉴 수 | 의미 | 대표 메뉴 |
|------|--------|------|-----------|
| `rn` | 208 | **신고 (Return)** | 작성중 신고서, 부가세/종소세/법인세 신고 |
| `sf` | 165 | **자료/신고서식 (Submission Form)** | 중소기업 감면명세, 금융소득, 발급의무 |
| `et` | 66 | **전자세금계산서 (E-Tax invoice)** | 제3자 발급사실, 품목/거래처 |
| `ca` | 65 | **민원증명 (Certification — Administrative)** | 모범납세자증명, 폐업증명, 민원실 예약 |
| `ab` | 62 | **수임 관리 + 사업자 증명 (Agent-Business)** | 기장대리 수임, 나의 세무대리인 동의·해임 |
| `cr` | 61 | **현금영수증 (Cash Receipt)** | 사용내역, 매출/매입, 전용카드 |
| `pp` | 52 | **개인포털 (Personal Portal)** | 우편물·문자·송달, 세금신고내역 |
| `wf` | 33 | **근로/자녀장려금 (Welfare/Workforce)** | 근로장려금 안내, 신청, 수급사실 |
| `ys` | 29 | **연말정산 (Year-end Settlement)** | 소득·세액공제 자료, 부양가족 동의 |
| `ic` | 15 | **소득자료 (Income Confirmation)** | (일용·간이·용역) 본인 소득내역 |
| `nf` | 11 | **고지 (Notification)** | 전자고지, 체납내역, 송달 |
| `rm` | 8  | **납부 (Remittance/Payment)** | 자진납부, 타인세금 납부 |
| `cm` | 7  | **공통 (Common, 공익법인)** | 사업용·공익법인 계좌 |
| `rd` | 6  | **환급 (Refund)** | 환급금, 납부증명, 납세증명서 |
| `at` | 5  | **체납·특수업무** | 사망자 국세정보, 체납징수특례 |
| `tr` | 3  | **신고내용확인** | 신고내용확인 진행상황 |

> 미매핑: `lc` (Levy/Collection — 옛 모듈만 존재).

## 7. 화면 ID 명명 규칙

`UT` + 도메인 + 시퀀스. 검증일: 2026-04-30.

| prefix | 도메인 | 예 |
|--------|-------|----|
| `UTERN...` | rn (신고) | `UTERNAA0B001` 종소세 신고 메인, `UTERNAAZ0Z11` 신고 셸 |
| `UTESF...` | sf (자료) | `UTESFAA0E001`, `UTESFZAA02` |
| `UTECM...` | cm (공통) | — |
| `UTECA...` | ca (민원증명) | — |
| `UTEYS...` | ys (연말정산) | — |
| `UTEET...` | et (전자세금계산서) | — |
| `UTEWF...` | wf (장려금) | — |
| `UTEWE...` | (소득자료) | — |
| `UTEAB...` | ab (수임관리) | — |
| `UTXPP...` | pp (개인포털) | — |

## 8. ab 모듈 양방향 구조

`UTEAB*` / `ATEAB*` 화면들은 **세무사 측과 고객 측 양쪽**이 같은 모듈을
공유. 같은 actionId 체계 (`ATEAB*`) 사용, statusValue 만 등록/동의/해지로 다름.
검증일: 2026-04-30.

**세무사 측 (수임 관리)**

| 화면 ID | 의미 |
|---------|------|
| `UTEABHAA01` | 기장대리 수임납세자 등록 |
| `UTEABHAA31/32/03` | 기장대리 수임납세자 해지/정정/조회 |
| `UTEABHAA07/09` | 신고대리·법인외부조정 납세자 등록/해지/조회 |
| `UTEABHAA25/26/27` | 세무대리정보 이용 신청서 |
| `UTEABHAA18` | 신고대리 정보이력 조회 |
| `UTEABACA11` | 위임자 조회 |
| `UTEABAAA31` | 수임사업자 기본사항 조회 |

**고객 측 (자기 세무대리인 관리)**

| 화면 ID | 의미 |
|---------|------|
| `UTEABHAA13` | 나의 세무대리인 조회 |
| `UTEABHAA16` | 나의 세무대리 수임동의 |
| `UTEABHAA17` | 나의 신고대리 수임동의 |
| `UTEABHAA22` | 나의 세무대리인 해임 |

## 9. OACX 간편인증 provider

13개 외부 인증사 통합 게이트웨이. 검증일: 2026-04 / 출처: `GET /oacx/api/v1.0/provider/list` 응답.

| ID | 표시명 | 분류 |
|----|-------|------|
| `kakao_v1.5` | 카카오 | gov |
| `kakaobank_v1.5` | 카카오뱅크 | gov |
| `naver_v1.5` | 네이버 | gov ✓ (2026-05-10 본인 인증 통과 검증, `examples/auth_naver.py`) |
| `toss_v1.5` | 토스 | gov |
| `banksalad_v1.5` | 뱅크샐러드 | gov |
| `pass_v1.5` | 통신사패스 | gov |
| `kica_v1.5` | 삼성패스 | gov |
| `kb_v1.5` | KB은행 | gov |
| `nh_prod` | NH인증서 | gov |
| `hana_v1.5` | 하나은행 | gov |
| `shinhan_v1.5` | 신한인증서 | gov |
| `woori_v1.5` | 우리인증서 | gov |
| `nice_v1.5` | 나이스 | iden (본인확인 전용) |

**자동화 난이도**

| 인증 방식 | 난이도 | 비고 |
|-----------|--------|------|
| NPKI 공인인증서 | 중 | `pypinksign` 등으로 직접 사용. 비밀번호 필요. 헤드리스 OK |
| 금융인증서 | 중 | NPKI 동일 흐름. 클라우드 보관이라 사용자가 직접 다운로드 |
| 카카오/네이버/토스/PASS | 하 (사람 개입 필수) | 폰에서 인증 버튼. 폴링은 자동, 인증 자체는 사람만 |
| 은행 인증서 (KB/하나/신한/우리/카뱅/NH) | 중~상 | 각 은행 앱/모바일 인증 |
| 삼성패스 (kica) | 하 | 삼성 폰 생체 인증 |
| 나이스 본인확인 | 하 | 본인 명의 휴대폰 + 인증번호 |
| `pubcLogin.do` 페이로드 | 중 | OACX 간편인증은 로그인 화면 컨텍스트 준비 후 plain hidden form 으로 통과 확인 |

## 10. NetFunnel — 트래픽 큐

검증일: 2026-04 / 출처: `prev/captures/` NetFunnel 호출.

**opcode (확정만)**

| opcode | 의미 |
|--------|------|
| `5101` | 큐 진입 / 티켓 발급 (`getTicketID`). aid 별 큐에 등록, key 발급 |
| `5004` | 큐 사용 확정 (`setComplete`). 발급 key 를 "사용했음" 처리 |

**응답 코드 (확정만)**

| 응답 | 의미 |
|------|------|
| `5002:200:key=...&nwait=...&nnext=...&tps=...&ttl=...&ip=...&port=...` | 큐 진입 성공 |
| `5002:501:msg="Action is not exist"` | 해당 aid 가 큐 보호 대상 아님 — 즉시 패스 |
| `5004:200:msg="Success"` | key 사용 확정 OK |

**큐 파라미터 (5002:200 응답)**

| 필드 | 의미 |
|------|------|
| `key` | 큐 통과 증명 토큰 (256자 hex) |
| `nwait` | 현재 큐 대기 인원 수 |
| `nnext` | 본인 큐 위치 (앞에 몇 명) |
| `tps` | 초당 처리 한도 |
| `ttl` | key 유효 시간 (초) |
| `ip` / `port` | NetFunnel 서버 식별 (`apct.hometax.go.kr` / 80) |

## 11. wqAction.do `<nts<nts>nts>` 서명 형식

검증일: 2026-04-30 / 출처: 종소세 신고 흐름 캡처.

POST body 끝에 일관 등장:

```
<nts<nts>nts>{(sec+11):02d}{40자 영숫자 시그니처}{sec:02d}
```

- `sec` = 호출 시점 초(0~59).
- `sec+11` = 앞쪽 2자리 (sec+11, mod 100).
- 가운데 시그니처는 40자(가변 38~42 관측, 정확한 알고리즘은 미확정).

검증 예시:

| 서명 | 앞 2 | 가운데 길이 | 뒤 2 | 검증 |
|------|------|------------|------|------|
| `<nts<nts>nts>6620yb...c3xI55` | `66` | 40 | `55` | sec=55, sec+11=66 ✓ |
| `<nts<nts>nts>40aDEY...uE29` | `40` | 40 | `29` | sec=29, sec+11=40 ✓ |
| `<nts<nts>nts>36JMc...Wg25` | `36` | 40 | `25` | sec=25, sec+11=36 ✓ |
| `<nts<nts>nts>62owG...51` | `62` | 38(?) | `51` | sec=51, sec+11=62 ✓ |

7개 비밀키 + sec mod 7 으로 키 선택은 옛(2021) 분석과 일치 가능성이 높지만,
본 캡처만으로 키 자체는 추출 불가 (별도 리버싱 필요).

## 12. wqAction 응답 포맷 (ATXPP/ATERN/ATTRN/ATESF)

검증일: 2026-04-30 / 출처: 캡처된 직접 호출.

| 액션 prefix | 옛 포맷 | 현재 포맷 |
|-------------|---------|----------|
| `ATXPP*` | XML | **JSON** ✓ |
| `ATERN*` | XML | **JSON** ✓ |
| `ATTRN*` | XML | **JSON** ✓ |
| `ATESF*` | XML | **JSON** ✓ |
| `ATEAB*` (수임동의 등) | XML | **미검증** (직접 호출 필요) |

## 13. 핵심 액션 ID 카탈로그

### 13.1 종소세 신고 흐름

검증일: 2026-04-30 / 출처: 캡처. 화면 흐름: `UTERNAA0B001` → `UTERNAA0Z044` → `UTERNAA0B003`.

| 단계 | actionId | screenId / realScreenId |
|------|----------|--------------------------|
| 신고 진입 (메뉴 검증) | `ATXPPAAA001R037` | `screenId=index_pp` |
| 종소세 메인 진입 | `ATERNABA008R04` | `UTERNAAZ0Z11` / `UTERNAA0B001` |
| 파일 변환·제출 진입 | (변환) | `UTERNAAZ0Z11` / `UTERNAA0Z044` |
| 변환 호출 | `ATERNABB001A01` | `UTERNAAZ0Z11` / `UTERNAA0Z044` |
| 검토 화면 | (전환) | `UTERNAAZ0Z11` / `UTERNAA0B003` |

### 13.2 수임동의 (세무사 ↔ 고객)

검증일: 옛 RPA 코드 + 메뉴 트리 매핑. 직접 호출 검증 미완.

| actionId | 화면 | 의미 |
|----------|------|------|
| `ATEABHAA001C01` | `UTEABHAA01` | 기장대리 수임동의 요청 (세무사 → 고객) |
| `ATEABHAA001R06` | `UTEABHAA16` | 위임자 목록 조회 (고객 측) |
| `ATEABHAA001U05` | `UTEABHAA16` | 수임동의 등록/수정 (고객 측 수락) |
| `ATXPPABA004A40` | `UTECMABA14` | 인증/권한 확인 |

### 13.3 조회 (지급명세서 / 세금신고내역)

검증일: 2026-04-30 / 출처: `tests/test_idpw_responses.py` + `tests/fixtures/2026-05-10/`.

| 화면 | actionId | 결과 모델 |
|------|----------|-----------|
| `UTXPPBAA48` | `ATXPPBAA001R16` | 지급명세서 (`income_statements`) |
| `UTXPPBAA47` | `ATXPPBAA001R15` | 세금신고내역 (`tax_filings`) |

> 라이브러리 호출은 `client.inquiries.income_statements(...)` / `tax_filings(...)`.

### 13.4 ID/PW 주소 조회

검증일: 2026-05-03 / 출처: ID/PW 인증 세션 직접 호출.

| 화면 | actionId | 결과 모델 |
|------|----------|-----------|
| `UTXPPBAD23` | `ATTABZAA001R01` | 세적 기본 단건 조회 (`ntplBscInfrInqrDVO`) |

도로명 풀주소는 `roadBscAdr`에 상세주소 조각 `bldBlckAdr`, `bldDnadr`, `bldFlorAdr`,
`bldHoAdr`, `etcDadr`를 붙여 구성한다. 실제 고객 주소, ID, 비밀번호, 주민등록번호는
문서에 저장하지 않는다.

### 13.5 근로소득 원천징수영수증 PDF

검증일: 2026-05-10 / 출처: 손택스 화면 소스와 라이브 ClipReport export.

| 화면/action | 역할 |
|------|------|
| `UTBSFAAM10` | `지급명세서(원천징수영수증) 제출내역` 모바일 화면 |
| `ATXPPBAA001R16` | 공식 제출내역 목록 조회. ID/PW 세션에서는 FWE로 거부됨 |
| `ATERNABA152R01` | 근로소득 경정청구 흐름에서 지급명세서 식별자 조회 |
| `ATERNABA151R01` | ID/PW 세션에서 실제 근로소득 지급명세서 상세 데이터 조회 |
| `ATTSFAAA005R01` | 공식 제출건 중간 조회. ID/PW 세션에서는 FWE로 거부됨 |
| `ATESFAAA011P01` | 근로소득 원천징수영수증/지급명세서 공식 ClipReport 양식 생성 |

2024년 귀속 근로소득 기준 리포트 파일은 `/tt/sf/a/a/RTISFAAE81`, `con=RTISFAAE81`이다.
`ATTSFAAA005R01`은 ID/PW 세션에서 FWE로 막히지만, `ATERNABA152R01`에서 얻은 행을
`UTBSFAAM10`의 `bmanBscMttrAdmDVOList` 형태로 보강하면 `ATESFAAA011P01` 공식 ClipReport에
값이 바인딩된다. 보강 필드는 `indvTin=ieTin`, `mateKndCd=A0051`, `myntsYn=Y`, `pblsRpt=N`,
`mskApplcYn=Y`이다. 요청 연도가 아니라 행의 실제 `attrYr` 기준으로 리포트 파일을 선택해야 한다.
샘플 검증 결과 공식 양식은 값이 들어간 3페이지 PDF, `Producer=iText 4.2.0 by 1T3XT`.

## 14. 자동화 가능/불가 현황

| 영역 | 상태 | 비고 |
|------|------|------|
| 카카오/네이버 OACX 간편인증 | ✓ 가능 (사람의 폰 승인 필요) | 그 외 흐름은 자동 |
| 세션 복원 + SSO 토큰 자동 갱신 | ✓ 가능 | `cookies.json` 시작 + `refresh_session()` |
| `nts_encrypt` 시간 기반 HMAC 서명 (현재 키셋) | ✓ 가능 | 7개 키 + userId mixin (`tests/test_crypto.py`). 키 source 는 `crypto.active_keys()` 가 env > cache > baseline 순서로 해석 |
| NTS_KEYS 동적 fetch / drift 검출 / 자동 갱신 | ✓ 가능 | `python -m hometax_client.health [--refresh]` (CLI), `tests/test_keys_live.py` (`HOMETAX_LIVE=1` 게이트) |
| 지급명세서 / 세금신고내역 조회 | ✓ 가능 | OACX 세션 기준 `client.inquiries.*` |
| 근로소득 지급명세서 데이터 조회 | ✓ 가능 | ID/PW/주민번호 세션 + `ATERNABA151R01` 응답값 |
| 근로소득 원천징수영수증 공식 PDF | ✓ 가능 | `ATERNABA152R01` 식별자 + `UTBSFAAM10` 공식 ClipReport 3페이지 원본 PDF |
| Connection reset 자동 retry | ✓ 가능 | 라이브러리 내장 |
| 신고/제출/저장 | ✗ 미구현 | 현재 미지원 — 향후 scope 확장 가능 |
| NPKI 공인인증서 로그인 | ✗ 미구현 | 별도 클라이언트 필요 |
| `<nts<nts>nts>` 서명 키셋 | ✓ 가능 | `common_te-min.js` 의 `testVal` 배열 — 평문 노출. `crypto.fetch_live_keys()` 가 직접 추출 |
| `ATEAB*` JSON 응답 여부 | ⚠️ 미검증 | 직접 호출로 확인 필요 |

**2026-05-10 추가 검증 (네이버 OACX)**

- `naver_v1.5` provider 로 ``examples/auth_naver.py`` 실행 → `trans` →
  `netfunnel` → `authen/request` → `poll_result` → `pubcLogin.do` →
  `session_info` 6단계 모두 카카오와 동일 흐름으로 통과. `OACXAuth` base
  class 의 ``_build_authen_body`` provider-specific 필드 그대로 동작.
- 발급 세션 등급으로 `client.inquiries.income_statements(2024)` 통과 (3 rows
  반환). ID/PW 등급에서 `AuthGradeInsufficientError` 거부되는 액션이 OACX
  네이버 등급에서는 정상.
- ``sessionMap`` 차이: ID/PW (``lgnCertCd=03``, ``userCertClCd=11``) vs 네이버
  OACX (``lgnCertCd=01``, ``userCertClCd=19``).

**2026-05-02 추가 검증**
- 현재 `UTXPPABA01.xml` 의 `fn_prcsLoginSimpleCallBack` 은 `moisCertYn=Y`,
  `newGpinYn=Y`, `reqTxId=<OACX token>` 를 `$c.biz.nts_loginAction` 으로 전달.
- `pubcLogin.do` 호출 전 `/`, 로그인 화면, `permission.do?screenId=UTXPPABA01`
  를 순서대로 호출해 TXPP 로그인 컨텍스트를 만든 뒤
  `/pubcLogin.do?domain=hometax.go.kr` 로 POST 하면 카카오 OACX 세션 발급 확인.
- 검증 명령: `uv run --env-file .env python examples/auth_kakao.py`.

## 15. ID/PW + RRN 2차 인증 흐름 (브라우저 캡처)

검증일: 2026-05-10 / 출처: `captures/2026-05-10T23-12-46/trace.har` (사용자 본인
계정, Chrome 148 via Playwright `--channel chrome`).

브라우저 흐름 entry 순서 (관련 부분만):

| # | 요청 | 비고 |
|---|---|---|
| 0 | `GET /` | 익명에 `WMONID`, `TXPPsessionID` 발급 (servlet sticky 세션) |
| 230 | `POST wqAction ATXPPABA001A25` (UTXPPABA01) | 로그인 화면 사전 호출 (idpw.py `_warmup_main_portal`) |
| 231 | `POST wqAction ATXPPCBA001R020` (UTXPPABA01) | 로그인 화면 사전 호출 (idpw.py `_warmup_main_portal`) |
| 233 | `POST wqAction ATXPPABA001R07` (UTXPPABA01) | ID/PW 사전 검증 (idpw.py 일치) |
| 234 | `GET apct/ts.wseq` (NetFunnel) | `aid=public_m_id_login` |
| 235 | **`POST /pubcLogin.do?...&mainSys=Y`** (1차) | id/pw POST → `lgnRsltCd=='30'` (RRN 필요). **set-cookie: `NTS_LOGIN_SYSTEM_CODE_P=TXPP`** |
| 237 | `GET UTXPPABC12.js` | 2차 인증(RRN) 화면 JS — 브라우저 자산 (HTTP-only 클라이언트는 JS 로드 불필요) |
| 240 | `POST permission.do?screenId=UTXPPABC12` | RRN 화면 활성화 |
| 241 | `POST /token.do` | SSO 토큰 |
| 242 | **`POST /pubcLogin.do?...&mainSys=Y`** (2차) | RRN POST. **set-cookie: `NTS_REQUEST_SYSTEM_CODE_P=null`, `NTS_LOGIN_SYSTEM_CODE_P=TXPP`, `TXPPsessionID=...tupiwsp18_servlet_TXPP06` (값 회전)** |
| 243 | `POST permission.do?screenId=UTXPPABA01` | **set-cookie: `NTS_REQUEST_SYSTEM_CODE_P=TXPP`** (이전 null → 실값) |
| 244 | `POST /userAthEvtxMenuUtil` | 인증 이벤트 로그 |
| 245 | `POST wqAction ATXPPCBA001R17` (`screenId=index_pp`) | 메인 포털 진입 첫 액션 |

확정 결론

- **post-RRN 신호**: `NTS_REQUEST_SYSTEM_CODE_P` 가 2차 pubcLogin.do (entry 242) 에서
  처음 set 되며, 이후 `permission.do?screenId=UTXPPABA01` (entry 243) 에서 실값
  (`TXPP`) 으로 갱신. **부트스트랩 도구의 자동 종료 indicator 로 사용 적합**.
- **1차 신호**: `NTS_LOGIN_SYSTEM_CODE_P` 는 1차 pubcLogin (entry 235) 에서 set —
  RRN 입력 화면 진입 시점에 이미 잡혀 indicator 로 부적합.
- **TXPPsessionID 값 회전**: 2차 pubcLogin 응답에서 servlet 세션 ID 가 새 값으로
  교체된다 (anonymous → authenticated transition). pool: `tupiwsp18`, system:
  `TXPP06`.
- **JS 가 set 하는 쿠키들**: `nts_hometax:userId`, `nts_hometax:pkckeyboard`,
  `naviOpenYn`, `naviOpenRfsYn`, `naviWrtCmplFlag`, `gdnpInfr`, `TMPR_MAIN`,
  `Veraport20PlatformInfo` 는 응답 set-cookie 가 아니라 페이지 JS 의
  `document.cookie` 로 설정. HAR set-cookie 추적엔 안 잡힘.
- **idpw.py 반영 상태** (2026-05-11): (a) `_warmup_main_portal()` —
  ATXPPABA001A25 / ATXPPCBA001R020 사전 호출. (b) `_activate_rrn_screen()` —
  1·2차 사이 `permission.do?screenId=UTXPPABC12` 활성화. 둘 다 best-effort
  (실패해도 메인 흐름 진행). 본 사용자 계정에서는 둘 없이도 통과 — 다른
  계정/시점 효과는 미검증.

---

## 16. 비회원 로그인 흐름 (브라우저 캡처)

검증일: 2026-05-11 / 출처: `captures/2026-05-11T13-38-50/trace.har`
(사용자 본인 명의 이름 + RRN, 카카오 OACX, Chrome 148 via Playwright
`--channel chrome`, `recon_login.py` 익명 시작).

홈택스 메인 → "로그인" → **비회원 로그인 탭 (`UTXPPBAC65`)** 에서 이름 +
주민번호 입력 후 카카오 인증 통과한 흐름.

### 핵심 식별자

| 항목 | 값 | 비고 |
|---|---|---|
| 비회원 로그인 진입 screen | `UTXPPBAC65` | 메뉴명 "비회원로그인", `childCount:12` (비회원 사용 가능 메뉴 12개) |
| 본인인증 endpoint | `/oacx/api/v1.0/*` | 회원 OACX 와 **동일** (`trans`, `authen/request`, `authen/result`) |
| 세션 발급 endpoint | `POST /pubcLogin.do?domain=hometax.go.kr&mainSys=Y` | 회원 ID/PW 와 **동일 endpoint**. body 는 암호화된 단일 문자열 (~3KB) — 평문 RRN/이름 없음. nts_encrypt 류 인코딩 추정 |
| 비회원 종소세 신고도움 진입 screen | `UTERNAAZ0Z11` | 회원의 `UTERNAAT32` 와 다름 |
| 비회원 종소세 진입 actions | `ATERNABA244R06`, `ATERNABA244R07` | 회원의 `ATERNABA134R02` (filing_help) 와 다른 prefix (244 vs 134) |

### sessionMap shape — 회원과 거의 동일 (단 권한은 다름)

`permission.do?screenId=UTXPPBAC65` 응답의 sessionMap 은 회원 흐름과
**필드 구성이 거의 같다** (`userId / tin / txprDscmNo` 등이 다 채워짐).
다만 라이브 호출로 확인된 결과 **권한 범위는 회원과 다르다** (아래
§"비회원 권한 매핑" 참조).

### sessionMap 의 회원/비회원 분기 필드 (확정 2026-05-11)

회원 e2e (`captures/naver-e2e/trace.har`, 2026-05-11) 와 비회원 캡처
(`captures/2026-05-11T13-38-50/trace.har`) 의 `permission.do` 응답
sessionMap 비교:

| 필드 | 회원 | 비회원 | 결론 |
|---|---|---|---|
| **`lgnUserClCd`** | `"01"` | `"02"` | **분기 시그니처 확정**. 라이브러리에서 비회원 세션 판별 시 이 값 사용 |
| `lgnCertCd` | `"01"` | `"01"` | 인증 수단 코드 (둘 다 카카오 OACX — 같음). 분기 신호 아님 |
| `haboCl` | `"Z"` | `"Z"` | 분기 신호 아님 |
| `athGrpCd` | (index_pp 응답에 부재) | `"0000005"` | 화면별 상이 — 분기 후보 약함. 확정 미완 |

다음 필드는 **분기 신호가 아니라 wqAction body 에 forward 되는 단순
분류 코드**. 옛 `hometax-scraper` (`user.py:361,383`) 의 수임동의
(`ATEABHAA001U05`) 호출에서 `permission` 응답의 `userClsfCd` 를 그대로
다음 요청 body 에 전달하는 패턴이 강한 증거. 회원/비회원 모두 동일 값 = 분기 아님 재확인.

| 필드 | 회원 | 비회원 | 용도 |
|---|---|---|---|
| `userClsfCd` | `"01"` | `"01"` | 사용자 분류 — wqAction 호출 시 forward |
| `txprClsfCd` | `"01"` | `"01"` | 납세자 분류 — wqAction 호출 시 forward |

### 비회원 권한 매핑 (라이브 검증 2026-05-11)

`captures/2026-05-11T13-38-50/cookies.json` 으로 1시간 후 라이브 호출
시도한 결과:

| 메뉴 / 호출 | 비회원 권한 |
|---|---|
| 종소세 신고도움 (`teht` / `UTERNAAT32` / `ATERNABA134R02`) | ✓ 가능 |
| 보험료 조회 (`teht` / `insurance_taxpayer_action`) | ✓ 가능 |
| 세적 기본 단건 조회 (`hometax` / `taxpayer_basic_info`) | ✓ 가능 |
| `income_tax.address_candidates(...)` 묶음 호출 | ✓ 10건 후보 + 3개 source 통과 |
| **지급명세서 조회 (`hometax` / `UTXPPBAA48` / `ATXPPBAA001R16`)** | **✗ "권한이 없는 화면입니다" (code `0000005,|+|0000001`)** |
| **세금신고내역 (`hometax` / `UTXPPBAA47` / `ATXPPBAA001R15`)** | **✗ 같은 메시지** |
| 대민사용자 기본정보조회 (`UTXPPBBA20` / `ATXPPAAA001R22`) | ✗ 추가 인증 필요 (`address_candidates` 의 skip 분기) |

결론: 비회원 세션은 **종소세 신고 준비에 필요한 일부 메뉴만 접근 가능**.
지급명세서 / 세금신고내역 등은 회원 권한 필요. **"비회원 = 회원과 거의
같은 권한" 가설은 폐기**.

### `pubcLogin.do` body 비교 — 회원 vs 비회원 (2026-05-11)

같은 endpoint 지만 body 구조가 완전히 다르다.

**회원 OACX** (본 라이브러리 `auth/oacx.py:279-288` 의 hard-coded form):
```
moisCertYn=Y&newGpinYn=Y&reqTxId=<cert_token>&ssoStatus=&portalStatus=
&scrnId=UTXPPABA01&userScrnRslnXcCnt=1920&userScrnRslnYcCnt=1080
```
Content-Type `application/x-www-form-urlencoded`, 평문, ~수십 bytes.

**비회원 OACX** (`captures/2026-05-11T13-38-50/`):
```
NLRoVo4=xtqrpELgolLupeP6QkCANZzejBdDfBC59k7DVGO5cuw0... (~2,959 bytes)
```
첫 key 자체가 의미 없는 영숫자 (`NLRoVo4`) — **브라우저 JS 가 키 이름까지
obfuscate 한 form**. value 도 client-side 암호화. 회원 form 의 의미적
키들 (`moisCertYn`, `reqTxId` 등) 과 매핑 불명.

**라이브러리 구현 블로커**:
- 비회원 흐름의 라이브러리 구현 (`auth/guest_kakao.py` 등) 은 회원 OACX
  처럼 단순 dict POST 로 재현 불가.
- 필요 작업: 브라우저 devtools 에서 pubcLogin 호출하는 JS 함수
  breakpoint → 의미 있는 input (이름 / RRN / cert_token / 화면 ID 등) →
  obfuscated key/value 매핑 추적. 또는 protected-login 보호 스크립트
  자체의 알고리즘 분석.
- 본 라이브러리의 `nts_encrypt` (wqAction 서명용) 과는 다른 알고리즘.
- 다음 세션 후보: 비회원 로그인 JS bundle 분석 (URL 확보 →
  beautified → 의미 추출).

### 미해결 / 추정

- **`TMPR_MAIN` cookie 출처**: dump 시점 cookies.json 에 존재하지만 HAR 의 어떤 응답 set-cookie 헤더에도 등장 안 함. §15 와 동일하게 페이지 JS 의 `document.cookie` 로 set 되는 메타 cookie 추정 (시그니처 cookie 아님).
- **`/userAthEvtxMenuUtil`**: 인증 endpoint 가 아니라 **메뉴 카탈로그 fetch**. body `type=0` (익명용) → `type=10` (인증 후 비회원 12개 메뉴). 회원도 같은 endpoint 호출.
- **`ATERNABA244R06` vs `R07` 의 역할 분담**: 비회원 진입 시 둘 다 발동. R06 / R07 의 차이 미확인 — 메뉴 1개만 클릭한 미니 캡처로 분리 관찰 필요.

### 라이브러리 함의 (구현은 다음 세션)

- 비회원도 회원과 같은 endpoint / 같은 sessionMap shape 라 별도 클래스
  부담은 작다 — 기존 OACX 흐름 + `pubcLogin` 호출 시 비회원 파라미터만
  추가하면 될 가능성. **단 `pubcLogin.do` body encoding 분석이 선행
  조건**.
- 호출 시 권한 부족 시 받는 응답 (`권한이 없는 화면입니다` /
  `0000005,|+|0000001`) 이 현재 `SessionExpiredError` 로 분류됨 →
  **classify_failure 의 분기 개선 후보** (P1 신규). 권한 부족과 실제 만료
  구분되어야 호출자가 적절히 분기.
- 진입 메뉴별 action_id (`ATERNABA244R06/R07`) 는 회원과 분리되어 있어
  `facts/current.toml` 에 별도 entry 가 적절 (이미 등록됨).
- `SessionInfo` 에 typed 비회원 표시 추가는 분기 필드 확정 (`lgnUserClCd`
  등) 후. 라이브러리 사용자가 "이 세션이 비회원인지" 판단할 수 있어야
  권한 없는 메뉴 호출 전에 짧게 거를 수 있음.

---

## 갱신 이력

본 카탈로그의 변경은 git log 에 남는다 (별도 changelog 미운영).

## 재검증 방법

| 항목 | 명령 |
|------|------|
| 알고리즘 / 키 source / parser 회귀 (오프라인) | `pytest -q` |
| NTS_KEYS 라이브 drift 검사 (네트워크 필요) | `HOMETAX_LIVE=1 pytest tests/test_keys_live.py` |
| NTS_KEYS health 점검 + 자동 갱신 (CLI) | `python -m hometax_client.health [--refresh]` |
| 카카오 인증으로 세션 받아 두기 | `uv run --env-file .env python examples/auth_kakao.py` |
| 네이버 인증 (verbose 로그) | `uv run --env-file .env python examples/auth_naver.py` |
| ID/PW + RRN 인증 | `uv run --env-file .env python examples/auth_idpw.py` |
| 브라우저 recon / cookies 캡처 | `python examples/recon_login.py --channel chrome` |
