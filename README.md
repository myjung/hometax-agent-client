# hometax-agent-client

Capture-and-replay HomeTax (`hometax.go.kr`) HTTP client for Python — designed
to be called from AI agents and small developer scripts.

The library wraps HomeTax's `wqAction.do` request/response convention
(JSON body + HMAC suffix signed by `nts_encrypt`) so callers can issue typed
inquiries without driving a browser. Browser-based session bootstrap is
optional and isolated to the `[bootstrap]` extras.

> ⚠️ **Status: alpha**. Public API is stabilizing; expect breaking changes
> until 0.2. Contributions and bug reports welcome.
>
> **본 프로젝트는 국세청 / 홈택스 / NTS 와 무관한 비공식(unofficial)
> 라이브러리입니다.** 국세청의 인가 / 후원 / 검수를 받지 않았으며, 홈택스의
> 변경에 대한 어떠한 호환 보장도 제공하지 않습니다.

## 주요 특징

- **HTTP-only 데이터 평면.** 라이브러리 본체는 `curl_cffi` 위에서 동작하며
  Playwright 같은 브라우저 의존을 코어에서 제거했다. 인증 부트스트랩이
  필요할 때만 `[bootstrap]` extras 를 설치한다.
- **두 층 API.** `client.<service>.<method>()` 로 typed 결과를 받거나,
  `client.wq_action(...)` raw 통로로 직접 호출할 수 있다. 홈택스가 응답
  shape 을 바꿔도 raw 통로로 즉시 우회 가능.
- **Drift-tolerant 모델.** 모든 dataclass 가 `raw` 를 들고 있어, 라이브러리가
  알지 못하는 새 필드도 보존된다. 응답 핵심 필드가 사라진 경우는
  `ResponseSchemaDriftError` 로 raise.
- **Facts as data.** 액션 ID, 화면 ID 같은 식별자는
  `hometax_client/facts/current.toml` 에 데이터로 분리해 두어, 코드 변경
  없이 catalog 만 갱신하면 된다.
- **타입화된 에러 계층.** 모든 라이브러리 예외가 `HometaxError` 를 상속.
  `SessionExpiredError`, `LoginRequiredError`, `ProtectedLoginError`,
  `AuthGradeInsufficientError` 등으로 세분화되어 agent 가 string 매칭 없이
  분기 가능.
- **다중 세션 관리.** `SessionStore` 한 디렉토리에 여러 고객 세션을
  `<client_id>.json` 으로 보관. list / open / health / find_by_tin 등
  일관 API. 세무사 사무실 다중 클라이언트 워크플로용
  ([`docs/sessions.md`](docs/sessions.md)).
- **Service-health 도구.** `python -m hometax_client.health` 로 NTS_KEYS
  drift 즉시 검출, `--refresh` 로 자동 cache 갱신.

## English summary

`hometax-agent-client` is a small Python library that talks directly to
HomeTax (Korea's national tax portal) over HTTPS. It is built for AI agents
and developers who want to obtain HomeTax data programmatically without
running a real browser. Authentication can be done via:

- **OACX** (Kakao/Naver simple-auth): user-driven, no automation possible
  for the phone-tap step.
- **ID/PW + RRN**: HTTP-only path. May be blocked by HomeTax's 2026-05
  protection script — in that case, use the `[bootstrap]` extras to seed
  cookies once with a real browser, then switch to the cookie-based client.

Inquiries are exposed as `client.<service>.<method>()` calls returning typed
dataclasses (or raw dicts via the escape-hatch path).

See `docs/architecture.md` for the design rationale and `docs/extending.md`
for adding a new tax service.

## 설치

```bash
# 라이브러리만 (HTTP-only 코어)
uv add hometax-agent-client

# 부트스트랩 도구 함께 (브라우저로 한 번만 cookies 캡처)
uv add "hometax-agent-client[bootstrap]"
```

Python 3.12 이상.

## 빠른 시작

### 1. 쿠키 기반 (권장)

브라우저 캡처 또는 부트스트랩 도구로 받은 `cookies.json` 으로 시작한다.

```python
from hometax_client import HometaxClient

client = HometaxClient.from_cookies(
    cookies_path="captures/2026-05-01/cookies.json",
    user_id="your_id",
    tin="1234567890",
)
info = client.session_info()
print(info.user_name, info.tin)

# 지급명세서 조회 (귀속연도 2024)
statements = client.inquiries.income_statements(attr_year=2024)
for statement in statements:
    print(statement.material_kind_name, statement.payer_name)

# 종합소득세 신고도움 — 자료구분별 소득내역
income = client.income_tax.income_details(attr_year=2024)
```

### 2. ID/PW 직접 로그인 (위험: 보호 스크립트 변경에 영향)

```python
from hometax_client import HometaxClient
from hometax_client.auth import IdPwAuth

auth = IdPwAuth(
    user_id="your_id",
    password="your_password",
    rrn="900101-1",
)
client = HometaxClient.login(auth=auth)
```

`pubcLogin.do` 가 HTTP 400 또는 partial 세션을 반환할 경우
`ProtectedLoginError` 가 raise 된다. 이때는 부트스트랩 경로 또는 OACX 인증을
사용해야 한다.

### 3. Raw 통로 (escape hatch)

홈택스가 새 메뉴를 추가했거나 라이브러리가 아직 따라가지 못한 응답이라면
직접 `wq_action()` 으로 호출 가능.

```python
data = client.wq_action(
    action_id="ATERNAxxxR01",
    screen_id="UTERNAxxx",
    host="teht",
    body={"attrYr": "2024"},
)
```

### 4. 다중 세션 관리 (`SessionStore`)

여러 고객 세션을 한 디렉토리에서 일관 API 로 다룬다. 자세한 내용은
[`docs/sessions.md`](docs/sessions.md).

```python
from hometax_client import SessionStore

store = SessionStore()                    # 기본 captures/sessions/
store.save(client, client_id="kim_chulsoo", label="김철수", auth_method="idpw")

for entry in store.list():
    print(entry.client_id, entry.label, entry.tin, entry.auth_method)

client = store.open("kim_chulsoo")        # last_used_at 자동 갱신
health = store.health("kim_chulsoo")      # 'recent' / 'stale' / 'missing'
```

## 책임 / 이용 범위

- **본인 명의 자료 자동 조회 또는 적법한 위임을 받은 사용자 자료 조회만**
  의도한다. 동의 / 위임 없이 제3자 자료를 조회하면 안 된다.
- 세무대리 시: 적법한 위임 절차 (수임동의 등) 가 선행되어야 한다. 본
  라이브러리 자체는 위임 검증 / 권한 확인을 하지 않는다 — 적법성은 사용자
  책임.
- 홈택스 이용약관, 정보통신망법, 개인정보보호법, 그 외 관련 법규 준수
  여부는 사용자가 자체 판단한다. 본 라이브러리 사용에 따른 모든 법적 / 운영
  위험은 사용자에게 있다.
- raw 통로 (`wq_action`) 로 임의 액션 호출이 기술적으로 가능하다 — 호출
  결과 / 영향 / 적법성은 사용자 책임.

## 보안 / 자격증명

- **외부 통신 없음.** 라이브러리는 `hometax.go.kr` 서브도메인 + NetFunnel
  큐 (`apct.hometax.go.kr`) 외 어떤 외부 호스트와도 통신하지 않는다.
  텔레메트리 / 로깅 서버 / 분석 백엔드 일체 없음.
- **자격증명은 사용자 머신에만.** ID / 비밀번호 / 주민번호 / 세션 쿠키는
  메모리 또는 사용자가 지정한 파일 (cache_path / SessionStore) 에만 저장.
  네트워크로 나가는 곳은 홈택스 자체뿐.
- **세션 캐시 권한.** `save_session` / `SessionStore.save` 가 만드는 파일은
  `0o600` (사용자만 read/write) 권한으로 저장된다.
- **`.gitignore` 처리.** `captures/`, `out/`, `*.session.json`, `.env` 모두
  `.gitignore` 에 포함되어 있다. 임의로 제외하면 자격증명 / 세션이 git
  history 에 남을 수 있음.
- 보안 취약점 발견 시 [`SECURITY.md`](SECURITY.md) 절차로 보고.

## 예제

- [`examples/basic_inquiry.py`](examples/basic_inquiry.py) — 쿠키 기반 단건 조회
- [`examples/auth_kakao.py`](examples/auth_kakao.py) — 카카오 OACX 인증 → 세션 캐시
- [`examples/auth_idpw.py`](examples/auth_idpw.py) — ID/PW 직접 로그인
- [`examples/income_tax_inquiry.py`](examples/income_tax_inquiry.py) — 종합소득세 신고도움 서비스 호출
- [`examples/recon_login.py`](examples/recon_login.py) — Playwright 로 브라우저 로그인 통과 후 cookies / HAR 캡처 ([`docs/recon.md`](docs/recon.md))
- [`examples/web-sample/`](examples/web-sample/) — 라이브러리를 작은 웹 UI 에 연결한 단순 데모 (단건 조회 한 화면)

## 프로젝트 문서

- [`docs/architecture.md`](docs/architecture.md) — 두 층 API, 의존성 정책,
  라이브러리 vs 워크플로 경계
- [`docs/conventions.md`](docs/conventions.md) — 모듈/클래스/메서드/예외
  네이밍 규약
- [`docs/extending.md`](docs/extending.md) — 새 세목(법인세/원천세/양도세
  등) 추가 패턴
- [`docs/compatibility.md`](docs/compatibility.md) — 홈택스 변경에 대한
  내성, 안정성 계약, 응답 drift 처리
- [`docs/hometax-facts.md`](docs/hometax-facts.md) — 캡처로 검증된 사실의
  단일 출처
- [`docs/cert-login-reference.md`](docs/cert-login-reference.md) — NPKI
  공인인증서 로그인 흐름 분석 (옛 `hometax-scraper` 코드 기반, 미구현
  영역의 출발점)
- [`docs/recon.md`](docs/recon.md) — 브라우저 recon / cookies 캡처 도구 사용법
- [`docs/sessions.md`](docs/sessions.md) — 다중 세션 관리 (`SessionStore`)

## 기여 / 보안

- 기여 절차: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 보안 취약점 보고: [`SECURITY.md`](SECURITY.md)

## 라이선스

MIT — [`LICENSE`](LICENSE) 참조. 본 라이브러리는 무보증으로 제공되며 (AS IS),
홈택스 / NTS 와 무관한 비공식 프로젝트임을 다시 한 번 명시합니다.
