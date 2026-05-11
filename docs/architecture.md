# Architecture

## 설계 원칙

`hometax-agent-client` 는 다음 원칙으로 설계된 **HTTP-only capture-and-replay
라이브러리**다.

1. **데이터 평면은 HTTP only.** 라이브러리 본체는 `curl_cffi` 위에서 동작하며
   브라우저 의존성은 코어에 들어오지 않는다. 인증 부트스트랩이 브라우저를
   필요로 하는 경우 `[bootstrap]` extras 로 격리한다.
2. **데이터 in / 데이터 out.** 모든 서비스 메서드는 dict 또는 dataclass 만
   반환한다. 파일 IO, PDF/Excel 렌더링, 한국어 stem 같은 워크플로 책임은
   라이브러리에 들이지 않는다 (그 책임은 호출 측 또는 별도 워크플로
   패키지가 진다).
3. **고수준 / 저수준 두 단계 API.** 타입화된 편의 메서드
   (`client.<service>.<method>()`) 와 저수준 직접 호출
   (`client.wq_action(...)`) 을 같이 노출한다. 홈택스가 응답 형식을 바꿔도
   호출자가 저수준 호출로 즉시 우회할 수 있다.
4. **응답 무변형 보존.** 응답 dict 의 키 이름은 홈택스 와이어 그대로 (예:
   `attrYr`, `txprDscmNo`, `lvyRperTin`) 보존한다. dataclass 도 항상
   `raw` 필드를 보유 — 라이브러리가 모르는 새 필드까지 호출자에게 노출된다.
5. **타입화된 예외.** 모든 라이브러리 예외는 `HometaxError` 를 상속.
   문자열 매칭에 의존하지 않고 `except SessionExpiredError` 같이 타입으로
   분기 가능.
6. **식별자 데이터 분리.** 액션 ID, 화면 ID 같은 식별자는 `current.toml`
   에 분리. 코드 변경 없이 카탈로그 한 줄 수정으로 정정할 수 있다.

## 패키지 구조

```
hometax_client/
├── __init__.py             # 공개 진입점
├── client.py               # HometaxClient — 핵심 HTTP 통로
├── crypto.py               # nts_encrypt + NTS_KEYS 동적 source / health
├── health.py               # python -m hometax_client.health — drift CLI
├── constants.py            # 코드 매핑, 호스트 별칭, 필수 쿠키 목록
├── exceptions.py           # HometaxError 계층 + classify_failure
├── models.py               # SessionInfo, IncomeStatement, TaxFiling
├── sessions.py             # SessionStore — 다중 세션 보관소
├── auth/
│   ├── oacx.py             # OACX 베이스 (kakao/naver 공통 흐름)
│   ├── kakao.py / naver.py # provider thin override
│   └── idpw.py             # ID/PW HTTP-only 로그인
├── bootstrap/              # [bootstrap] extras — Playwright recon 도구
│   └── capture.py          # CaptureSession / capture_login
├── services/
│   ├── _base.py            # ServiceBase (tin 보충, 쿠키 조회)
│   ├── inquiries.py        # 지급명세서 / 세금신고
│   └── income_tax.py       # 종합소득세 신고도움 서비스 (구 agitx)
└── facts/
    ├── current.toml        # 식별자 카탈로그
    └── __init__.py         # 로더
```

## 고수준 / 저수준 두 단계 API

```
┌──────────────────────────────────────────────────────────────────┐
│  Caller / Agent                                                  │
│                                                                  │
│   client.inquiries.income_statements(2024)   타입화된 편의 (안정)  │
│   client.income_tax.income_details(2024)                         │
│                                                                  │
│   client.wq_action(action_id=..., screen_id=..., body=...)       │
│                                                  ↑               │
│                                      저수준 직접 호출 (탈출구)      │
├──────────────────────────────────────────────────────────────────┤
│  Service classes (services/*.py)                                 │
│   - 응답 dict 을 dataclass / TypedDict 로 정리                     │
│   - 서브시스템 활성화 / tin 보정 / drift 감지                       │
├──────────────────────────────────────────────────────────────────┤
│  HometaxClient (client.py)                                       │
│   - wq_action 핵심: 서명 부착 + JSON 파싱 + 차단 코드 검출           │
│   - refresh_session, activate_subsystem_session                  │
│   - session_info — tin 자동 보충                                  │
├──────────────────────────────────────────────────────────────────┤
│  curl_cffi.requests.Session (외부)                                │
└──────────────────────────────────────────────────────────────────┘
```

## 의존성 정책

| 패키지 | 위치 | 이유 |
|---|---|---|
| `curl-cffi` | core | 홈택스가 TLS fingerprint 매칭으로 일부 botnet 도구를 거부. `impersonate=chrome` 으로 통과. |
| `httpx` | core | 일부 보조 호출. |
| `lxml`, `beautifulsoup4` | core | HTML 응답(ClipReport 등) 파싱. |
| `playwright` | `[bootstrap]` extras | 한 번만 cookies 받기 위한 부트스트랩 도구. 데이터 평면에는 들어오지 않음. |
| `pytest` | `[test]` extras | 회귀 테스트. |

## 라이브러리 vs 워크플로 경계

라이브러리는 다음을 **하지 않는다**.

- 디스크에 파일 저장 (PDF/Excel/CSV/JSON 산출물). **예외**: 세션 캐시
  (`HometaxClient.save_session`/`from_cookies`) 와 다중 세션 보관소
  (`SessionStore`, [`sessions.md`](sessions.md)). 둘 다 "라이브러리 호출에
  필요한 자체 상태" 만 디스크에 둔다 — 사용자 산출물 (PDF/Excel 등) 은 여전히
  호출자 책임.
- 한국어 파일명/폴더명 결정
- 한국어 메시지 string 으로 분기 가능한 에러 raise (대신 타입으로)
- 일괄 조회 진행 상태 관리 / 세션 lock (단일 / 다중 모두) / 사용자 UI
- HTML → PDF 렌더링 (system Chrome subprocess 등)
- 자동 세션 refresh / 만료 시 자동 재인증 (`SessionStore.health()` 가 신호만
  주고 분기는 호출자)

이런 책임은 호출 측 또는 워크플로 패키지가 진다. 사무실 운영용 워크플로
(엑셀 일괄 조회, 바탕화면 폴더 저장, 매니페스트, 로컬 웹 UI 등) 는 별도
private repo 에 두고 본 라이브러리를 **dependency 로** 사용하는 형태.

## 인증 등급 매트릭스

| 인증 방식 | HTTP-only 가능 | 비고 |
|---|---|---|
| OACX (kakao) | ✓ | 폰 승인 단계만 사람 개입 |
| OACX (naver) | ✓ | 2026-05-10 검증 — 카카오와 동일 흐름. `examples/auth_naver.py` |
| ID/PW + RRN 7 | △ | 2026-05 보호 스크립트로 직접 POST 가 막힐 수 있음 → `ProtectedLoginError`. 지급명세서 등은 `AuthGradeInsufficientError` |
| NPKI 공인인증서 | ✗ | 미구현 (`docs/cert-login-reference.md` 참고) |

각 인증 등급으로 호출 가능한 서비스가 다르다 (예: 지급명세서/세금신고는
ID/PW 세션 거부). 서비스 모듈 docstring 에 등급 명시.

## 응답 drift 처리

응답 shape 이 라이브러리가 알던 것과 다르면 두 가지 분기.

- **새 필드 추가** — 그대로 정상 동작. dataclass 의 `raw` 에 보존.
- **핵심 필드 누락** — `ResponseSchemaDriftError(action_id, missing, raw)`
  raise. 호출자는 `exc.raw` 로 응답 전체에 접근해 우회/디버그 가능.

자세한 안정성 계약은 [`compatibility.md`](compatibility.md) 참조.
