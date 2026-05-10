# Compatibility & Stability

홈택스는 외부 API 가 아닌 정부 포털이고, 응답 shape / 액션 ID / 보호
스크립트가 분기 단위로 바뀐다. 본 라이브러리는 이 변경에 **유연하게
대응**하면서도 **공개 API 안정성**을 유지하기 위해 다음 계약과 패턴을
가진다.

## 안정성 계약

| 항목 | 안정 보장 |
|---|---|
| `HometaxClient` 의 public 메서드 시그니처 | 마이너 버전 안에서 호환 |
| `client.<service>.<method>()` 시그니처 | 마이너 버전 안에서 호환 |
| `wq_action(...)` raw 통로 | 메이저 버전 안에서 호환 |
| `HometaxError` 계층 구조 | 메이저 버전 안에서 호환 |
| typed 반환의 기존 필드 | 제거되지 않음 (값은 None 가능) |
| typed 반환의 새 필드 추가 | 마이너 버전에서 가능 |
| 모듈 내부 `_parse_*` / `_fetch_*` / `_*` 상수 | 안정 보장 없음 |
| `services.*` 서브모듈 경로 | 안정 보장 없음 (재구성 가능) |
| `facts/current.toml` 의 식별자 값 | 안정 보장 없음 (홈택스 변경 시 갱신) |

## 응답 shape drift

라이브러리가 알던 shape 과 다른 응답이 도착한 경우의 분기.

### 새 필드가 추가됨

→ 그대로 정상 동작. dataclass 의 `raw` 에 보존되며 호출자가 꺼내 쓸 수
있다.

```python
statement = client.inquiries.income_statements(2024)[0]
new_value = statement.raw.get("homeTaxNewField2027")
```

### 기존 필드가 사라짐 (정보성 필드)

→ dataclass 필드가 ``None`` 이 된다. raise 하지 않는다.

### 핵심 필드가 사라짐 (서비스 자체가 동작 못 할 정도)

→ `ResponseSchemaDriftError(action_id, missing, raw)` raise.

```python
try:
    data = client.income_tax.filing_help_data(2024)
except ResponseSchemaDriftError as exc:
    logger.warning(
        "filing_help shape drift: action=%s missing=%s",
        exc.action_id, exc.missing,
    )
    # 직접 raw 응답 확인 → 우회
    data = exc.raw
    # ...
```

## 식별자 변경

홈택스가 액션 ID 또는 화면 ID 를 살짝 바꾼 경우.

### 가벼운 변경 — `current.toml` 한 줄 수정

```diff
 [services.inquiries.income_statements]
-action_id = "ATXPPBAA001R16"
+action_id = "ATXPPBAA001R17"
```

라이브러리 코드는 건드리지 않고 patch release.

### 큰 변경 — 메뉴 폐지 / 응답 구조 재편

새 메서드 추가 + 옛 메서드 alias 처리:

```python
class InquiryService(ServiceBase):
    def filings(self, ...):  # 새 표준
        ...

    @deprecated("Use filings()", since="0.4")
    def tax_filings(self, ...):
        return self.filings(...)
```

한 메이저 버전 동안 deprecation warn → 다음 메이저에서 제거.

## 알고리즘 변경

`nts_encrypt` 의 7개 비밀키는 홈택스 측에서 회전 가능.

**감지 채널** — 두 가지 회귀 테스트가 다른 종류의 변경을 잡는다:

- `tests/test_crypto.py` — **알고리즘 회귀**. HMAC 동작/형식/키 source 해석
  순서를 검증. fixture (`tests/fixtures/2026-05-10/common_te-min_excerpt.js`)
  로 parser 도 고정. CI/오프라인에서 항상 실행. 키 회전은 못 잡음.
- `tests/test_keys_live.py` — **라이브 drift 회귀**. 라이브 `common_te-min.js`
  를 fetch 해 `active_keys()` 와 비교. 평소엔 skip, `HOMETAX_LIVE=1` 환경
  변수에서만 실행. 개발자 머신/cron 에 걸어 두면 회전 시점 즉시 검출.

수동 점검이 필요하면 ``python -m hometax_client.health`` (옵션 `--refresh`
로 cache 자동 갱신).

**회전 시 절차**:

1. ``python -m hometax_client.health --refresh`` 실행 — 라이브 키를 사용자
   cache (`~/.cache/hometax-agent-client/nts_keys.json`) 에 저장. 즉시 모든
   호출이 새 키 사용 (``active_keys()`` 가 cache > baseline 순서로 해석).
2. (선택) ``hometax_client/crypto.py:NTS_KEYS_BASELINE`` 갱신 + 새 fixture
   ``tests/fixtures/<일자>/common_te-min_excerpt.js`` 추가 + 회귀 테스트의
   기대 키 값 갱신 → patch release.
3. 캡처된 실제 호출에서 시그니처 일치 재확인.

라이브러리는 cache 갱신만으로도 동작. baseline 갱신은 오프라인 환경 / 새
설치 사용자를 위한 단계.

## 보호 스크립트

`pubcLogin.do` 보호 스크립트(2026-05~) 같은 동적 보호는 capture-replay
범위를 벗어날 수 있다. 두 가지 대응:

1. **보호 스크립트 RE** (정공법) — 본문 random protected fields 의 변환
   알고리즘을 분석해 Python 으로 포트. 성공하면 `IdPwAuth` 가 직접
   동작.
2. **부트스트랩 격리** (현재) — `[bootstrap]` extras 의 도구로 한 번만
   브라우저로 cookies 받고, 그 다음부터는 `HometaxClient.from_cookies`
   로 HTTP-only.

본 라이브러리는 (2) 가 default. 직접 POST 가 거부되면
`ProtectedLoginError` 가 raise 된다.

## 버전 정책

[Semantic Versioning](https://semver.org/) 따른다.

| 변경 종류 | 버전 |
|---|---|
| 식별자 ``current.toml`` 갱신만 | patch |
| typed 반환에 새 필드 추가 | minor |
| 새 서비스 / 새 메서드 추가 | minor |
| 메서드 시그니처 변경 / 제거 | major |
| `wq_action` 시그니처 변경 | major |
| 예외 계층 재배치 | major |

## 회귀 테스트 안전망

`tests/fixtures/` 의 캡처된 응답으로 파서가 잘 동작하는지 분기별로
회귀:

```
tests/fixtures/
├── 2026q2/
│   ├── income_statements_R16.json
│   └── filing_help_R02.json
└── 2026q3/
    └── ...
```

새 분기 fixture 가 추가되어도 옛 분기 fixture 도 통과해야 한다 (호환
보장).

## Drift 모니터링 (옵션)

호출 측이 drift 신호를 받고 싶다면:

```python
import logging
logger = logging.getLogger("hometax_client.drift")

# 향후: client.on_schema_drift(callback) 형태로 노출 예정.
```

당분간은 `ResponseSchemaDriftError` 로 raise 되는 경우만 신호로 받는다.
