# Naming & Code Conventions

본 라이브러리는 PEP 8 을 준수한다 (max line length 는 120 까지 허용). 다음 컨벤션을
**한 가지로 통일**한다. 새 코드는 이 표를 따라야 한다.

## 모듈

- `snake_case`. 의미 영문.
- 한 단어 우선. 두 단어가 자연스러우면 두 단어 (`income_tax`,
  `wage_statement`).
- 홈택스 내부 prefix(`agitx`) 는 **모듈 이름으로 쓰지 않는다.** 의미 영문
  으로 변환 (`agitx` → `income_tax`). 홈택스 응답 키에 들어 있는 prefix
  자체는 그대로 보존한다.

## 클래스

| 카테고리 | suffix | 예 |
|---|---|---|
| HTTP 클라이언트 | `*Client` | `HometaxClient` |
| 서비스 (도메인별 메서드 묶음) | `*Service` | `InquiryService`, `IncomeTaxService` |
| 인증 흐름 | `*Auth` | `OACXAuth`, `KakaoAuth`, `IdPwAuth` |
| 인증 산출물 | `*Result` | `OACXResult`, `IdPwResult` |
| 응답 데이터 모델 | suffix 없음, 명사형 | `SessionInfo`, `IncomeStatement`, `TaxFiling` |
| 예외 | `*Error` | `HometaxError`, `SessionExpiredError` |

`*Help`, `*Util`, `*Manager` 같은 모호한 suffix 는 사용하지 않는다.

## 메서드

- **조회 (getter)** — 명사형. 부수효과 최소화.
  ```
  client.inquiries.income_statements(year)
  client.income_tax.insurance_premiums(year)
  client.session_info()
  ```

- **부수효과 / 동작** — 동사형.
  ```
  client.refresh_session()
  client.activate_subsystem_session(host=..., screen_id=...)
  client.save_session(path)
  auth.authenticate(...)
  ```

- **Raw 통로** — `wq_action()` 한 가지로 통일.

`probe_*`, `collect_*` 같은 임시 동사는 사용하지 않는다.

## 인자 이름

사용자 표면(호출 측이 직접 입력)에서는 **일반 표기** 를 사용한다. 와이어
필드 이름은 라이브러리 내부에서만 사용.

| 와이어 (홈택스 내부) | 사용자 표면 |
|---|---|
| `id`, `userId` | `user_id` |
| `pswd` | `password` |
| `txprDscmNo` | `rrn` |
| `attrYr` | `attr_year` |
| `tin` | `tin` (그대로 — 외부 통용 약어) |

## 응답 필드

홈택스가 응답에 박는 필드 이름은 **변형하지 않고 그대로 둔다.** 예:

- `attrYr`, `mateKndCd`, `lvyRperTin`, `agitxRtnInqrDVOList` 등은 응답
  dict 그대로 노출.
- 라이브러리가 dataclass 로 추출할 때만 영문 의미명으로 변환 (`attr_year`,
  `material_kind_name`, `payer_tin`).
- dataclass 의 `raw` 는 항상 와이어 그대로 보존.

이건 capture-replay 정합성을 지키기 위한 의도된 약속이다.

## 상수

- `UPPER_SNAKE_CASE`.
- 식별자 상수: `*_ACTION`, `*_SCREEN_ID`, `*_REFERER`, `*_HOST`.
- 가능한 경우 코드 상수보다 `facts/current.toml` 로 분리.

## 예외 계층

```
HometaxError                      # 모든 라이브러리 예외의 베이스
├── WqActionFailedError           # wqAction.do result='F'
│   ├── SessionExpiredError       # 세션 만료 / 권한 부족
│   ├── ValidationError           # 필수입력/형식 오류
│   ├── LoginRequiredError        # [FWE] — 별도 인증 필요
│   ├── AuthGradeInsufficientError
│   └── BusinessAccountUnsupportedError
├── BlockedError                  # EIE2*/ECE10* 차단 코드
├── UnknownResponseError          # JSON 파싱 실패 / 비정상 응답
├── ResponseSchemaDriftError      # 라이브러리가 알던 shape 과 다름
└── ProtectedLoginError           # pubcLogin 직접 POST 거부 (2026-05+)
```

호출자는 `except HometaxError:` 한 줄로 라이브러리 예외 전체를 잡을 수
있다. 한국어 메시지 string match 강요 X — 타입으로 분기.

## 파일 IO

라이브러리 본체에는 파일 IO 가 없다. 예외는 두 가지 — 둘 다 "라이브러리
호출에 필요한 자체 상태" 저장:

1. **단일 세션 캐시** — `HometaxClient.save_session(path)` /
   `from_cookies(path)`.
2. **다중 세션 보관소** — `SessionStore` (`sessions.py`,
   [`docs/sessions.md`](sessions.md)).
3. **NTS_KEYS cache** — `python -m hometax_client.health --refresh` /
   `save_keys()` 가 사용자 cache 디렉토리에 키 7개 저장
   (`crypto.py:active_keys` 가 cache > baseline 순서로 해석).
4. **Bootstrap recon 산출물** — `[bootstrap]` extras 의
   `CaptureSession` 이 cookies/HAR 등 분석용 파일을 사용자 지정
   디렉토리에 저장 ([`docs/recon.md`](recon.md)).

PDF/Excel/CSV/사용자 산출물 등 그 외 모든 "저장" 책임은 호출 측 또는
워크플로 layer.

## Public/Private 표시

- leading `_` = private. (예: `_fetch_material_kind`, `_collect_address_candidates`).
- public 모듈 함수도 `__all__` 에 명시되지 않으면 안정성 계약 없음.
- 모듈 안의 내부 헬퍼는 leading `_` 로 시작.

## Type hints

- 모든 public 메서드/함수는 type hint 필수.
- `from __future__ import annotations` 로 forward reference 활성화.
- 반환은 dataclass / TypedDict / dict 중 의미 있는 형태.
- `Any` 는 **외부 와이어 응답** 일 때만 사용 (홈택스가 무엇을 보낼지 모름).

## Docstring

- 모든 public 메서드에 docstring (한국어 우선, 영문 보조 가능).
- Args / Returns / Raises 명시.
- 와이어 액션 ID, 화면 ID 같은 식별자는 docstring 에 명시해 추적성 확보.

## Imports

PEP 8 import 그룹 순서:

1. `from __future__ import annotations`
2. stdlib
3. third-party
4. local (`from ..`)
5. `if TYPE_CHECKING:` 블록 (forward type-only imports)

## Lint 검증

```bash
.venv/bin/pycodestyle --max-line-length=120 hometax_client/
```

PR 들어오기 전 통과 필수.
