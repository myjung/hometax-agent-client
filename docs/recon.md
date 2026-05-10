# Recon — 브라우저로 로그인하고 cookies / HAR 캡처

`hometax_client.bootstrap` 은 Playwright 로 실제 홈택스 로그인을 통과시키고
산출물(`cookies.json`, `storage_state.json`, `trace.har`, `meta.json`) 을
저장하는 **선택적** 도구다. 라이브러리 코어는 이 모듈을 import 하지 않는다.

용도:

1. **세션 부트스트랩.** 어떤 인증이든 한 번 사람이 통과시키고 그 결과
   `cookies.json` 을 `HometaxClient.from_cookies` 로 주입해 이후 호출은
   HTTP-only 코어로 진행.
2. **응답 / 보호 스크립트 분석.** HAR 안에 모든 request/response 본문이
   embed (base64) 되어 있어 mitmproxy / Chrome DevTools 가 그대로 import.
   `pubcLogin.do` 보호 스크립트 분석, 새 메뉴의 액션 ID 발견 등.

## 설치

```bash
uv sync --extra bootstrap
# 한 번만 — Playwright 번들 chromium 다운로드
.venv/bin/playwright install chromium
```

Windows:

```pwsh
uv sync --extra bootstrap
.venv\Scripts\playwright install chromium
```

플랫폼 중립이다 (번들 chromium 은 Linux / macOS / Windows 동일).

> **갓 출시된 distro 사용자 (예: Ubuntu 26.04):** Playwright 가 해당 OS 용
> 번들 chromium 빌드를 아직 못 가질 수 있다 (`Playwright does not support
> chromium on ...` 에러). 그땐 `playwright install` 을 건너뛰고 시스템 Chrome
> 을 사용한다 — 아래 모든 명령에 `--channel chrome` 만 추가하면 된다
> (`google-chrome` 이 설치되어 있어야 함).

## 기본 사용 — CLI

```bash
.venv/bin/python examples/recon_login.py
```

브라우저 창이 **메인 포털 (`https://hometax.go.kr/`)** 로 열린다. 거기서
"로그인" 버튼을 눌러 평소대로 로그인한다 (ID/PW + RRN, 카카오 OACX,
공인인증서 등). 로그인 완료(메인 포털 진입) 후 **터미널에서 Enter** 를
누르면 산출물이 저장되고 창이 닫힌다 — 수동 확정 모드가 기본이다.

자동 종료(`--auto-close`) 도 가능하지만 **다단계 인증에는 비추**한다.
ID/PW + RRN 흐름의 경우 `NTS_LOGIN_SYSTEM_CODE_P` 가 1차(ID/PW) 통과
시점에 set 되어 RRN 입력 화면에서 잘못 종료된다. 어느 쿠키가 정확히 "완전
로그인" 후에만 발급되는지 확인된 흐름에서만 사용한다.

```bash
# 수동 (기본, 권장 — recon / 다단계 인증 모두 안전)
.venv/bin/python examples/recon_login.py --channel chrome

# 자동 (단순 단계 흐름만)
.venv/bin/python examples/recon_login.py --channel chrome --auto-close
```

> ⚠️ **메인 포털에서 출발해야 한다.** `UTXPPABA01.xml` 에 deep-link 로 직접
> 진입하면 메인 포털에서 받아야 할 priming (cookies, referer chain) 이 빠져
> ID 로그인 폼이 정상 동작하지 않는다 — 메인의 "로그인" 버튼을 통해 이동해야
> 한다. (HTTP-only `IdPwAuth._prime_hometax_login_context()` 가 `/` →
> 로그인 페이지 → `permission.do` 순으로 priming 하는 것과 동일한 이유.)
>
> 참고: `WMONID` / `TXPPsessionID` 는 익명 첫 페이지 로드부터 set 되므로
> 로그인 신호로 쓰지 않는다.

산출물:

```
captures/2026-05-10T12-34-56/
├── cookies.json        # Playwright cookies — from_cookies 가 그대로 받음
├── storage_state.json  # cookies + localStorage + ...
├── trace.har           # HAR (req/resp body embed)
└── meta.json           # URL / 쿠키 이름 목록 / 시간
```

## 라운드트립 — 캡처 → HTTP-only 호출

```python
from hometax_client import HometaxClient

client = HometaxClient.from_cookies(
    "captures/2026-05-10T12-34-56/cookies.json",
)
print(client.session_info())
statements = client.inquiries.income_statements(attr_year=2024)
```

`from_cookies` 가 Playwright 의 cookies array 포맷을 직접 받기 때문에
별도 변환 불필요. `ESSENTIAL_COOKIES` 에 등록된 쿠키만 추려 주입한다.

## 코드에서 직접 사용 — `CaptureSession`

CLI 가 부족하면 컨텍스트 매니저로 직접:

```python
from hometax_client.bootstrap import CaptureSession

with CaptureSession(output_dir="captures/recon-pubclogin") as cap:
    # 원하는 화면 직접 이동
    cap.page.goto("https://hometax.go.kr/...")

    # 사람이 무언가 클릭 / 입력
    cap.wait_for_login(timeout=900)

    # 추가로 임의 페이지 더 둘러보고 나서
    cap.page.goto("https://teht.hometax.go.kr/...")

    paths = cap.dump()

print(paths["har"])
```

`cap.page` / `cap.context` 로 Playwright API 직접 접근 가능. 추가 페이지
방문, 스크린샷, 네트워크 인터셉트 등 모두 사용 가능.

## CLI 옵션

| 플래그 | 기본 | 의미 |
|---|---|---|
| `--output` / `-o` | `captures/<timestamp>` | 산출물 저장 위치 |
| `--url` | `https://hometax.go.kr/` (메인 포털) | 시작 URL — 메인에서 출발해야 priming 정상 |
| `--auto-close` | off (= 수동 Enter) | 쿠키 indicator 가 잡히면 자동 종료. 다단계 인증에는 비추 |
| `--headless` | off (= headed) | 창 없이 실행 |
| `--no-har` | off (= HAR 수집) | HAR 끔 |
| `--channel` | (번들 chromium) | `chrome` / `msedge` 등 시스템 브라우저 |
| `--timeout` | 600 | `--auto-close` 모드 대기 초 |
| `--indicator` | `NTS_REQUEST_SYSTEM_CODE_P` | `--auto-close` 신호 쿠키 (post-RRN. 반복 가능) |

## 분석 팁 — HAR

```bash
# Chrome DevTools 로 보기
#   chrome://inspect → "Open dedicated DevTools for Node"
#   Network 탭 → import HAR

# mitmproxy 로 보기
mitmproxy -r captures/.../trace.har
mitmweb -r captures/.../trace.har

# 특정 액션만 jq 로
jq '.log.entries[] | select(.request.url | contains("pubcLogin"))' \
   captures/.../trace.har
```

## 보안 / 위생

- `captures/` 는 `.gitignore` 됨. 임의로 제외 금지.
- HAR 에는 ID/PW 인증의 경우 비밀번호·주민번호 7자리·세션 토큰이 모두
  들어간다. 외부 공유 / 업로드 / 첨부 금지.
- 분석 끝나면 디렉토리 통째로 삭제. 필요한 불변 사실만 `docs/hometax-facts.md`
  에 검증일 + 캡처 디렉토리 이름과 함께 기록.
- 본인 명의 자료 분석에만 사용. 제3자 자료 자동 조회는 동의 없이 금지.

## 트러블슈팅

| 증상 | 원인 / 대응 |
|---|---|
| `ImportError: hometax_client.bootstrap requires the [bootstrap] extra` | `uv sync --extra bootstrap` 후 `playwright install chromium` |
| `Executable doesn't exist at .../chrome` 류 | `playwright install chromium` 안 돌렸음 |
| `Playwright does not support chromium on ubuntu26.04-x64` 류 (또는 다른 갓 나온 distro) | Playwright 가 해당 distro 용 번들 chromium 빌드를 아직 안 가짐. 시스템 Chrome 으로 우회: `--channel chrome` (시스템에 `google-chrome` 설치되어 있어야 함, `playwright install` 불필요) |
| `--channel chrome` 인데 실패 | 시스템 Chrome 미설치. `apt install google-chrome-stable` 또는 `--channel msedge`/번들 chromium 시도 |
| `TimeoutError: 로그인 완료 신호…` | 대기 시간 안에 `TXPPsessionID` 미발급. `--timeout` 늘리거나 `--indicator` 로 다른 쿠키 지정 |
| 헤드리스에서 자동화하려는데 보호 스크립트가 막음 | 헤드리스는 ID/PW 직접 로그인에 부적합. headed 로 사람이 통과 → cookies 재사용 |
