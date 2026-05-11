# Web sample

`hometax-agent-client` 라이브러리를 작은 웹 UI 에 연결하는 단순 예제.

**한 화면 / 한 폼 / 한 호출** 로 압축한 형태. 라이브러리 사용 방법을
보여주기 위한 데모이며, 실제 사무실 운영에 그대로 쓰기 위한 것이 아니다.

## 특징

- stdlib `http.server` 만 사용 — Flask/FastAPI 등 추가 의존성 없음
- 단건 조회 한 화면. 일괄 / 매니페스트 / ZIP 다운로드 / PDF 저장 없음
- 한 폼: 귀속연도 1개 입력 → 결과 JSON 표시
- 인증은 cookies 파일 우선 (가장 안정), 없으면 ID/PW fallback
- 라이브러리의 typed 에러를 HTTP 상태 코드와 `error_type` 으로 매핑

## 파일 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 페이지 (HTML/CSS/JS 한 덩어리) |
| `server.py` | 실제 서버. `hometax_client` import. 라이브러리 설치 필요 |
| `preview.py` | UI 미리보기용 stub 서버. **stdlib 만으로 동작**, mock 데이터 |

## 페이지만 미리 보기 (의존성 설치 없이)

라이브러리 설치 없이 페이지 레이아웃과 JS 동작만 확인하고 싶을 때:

```sh
python3 examples/web-sample/preview.py
```

브라우저에서 `http://127.0.0.1:8787/` 접속. `/api/lookup` 은 실제
홈택스 호출 없이 mock 데이터로 응답하므로 폼 → 결과 표시 흐름 전체를
볼 수 있다. 페이지 상단에 "Preview 모드" 배너가 표시된다.

Python 3.10+ 면 다른 의존성 전혀 없음.

## 실행

`.env` 에 인증 정보 설정 (둘 중 하나):

**A. cookies 파일 (권장)** — 부트스트랩 도구나 브라우저 캡처로 한 번 받아둔 cookies 파일.

```sh
HOMETAX_COOKIES=captures/cookies.json
HOMETAX_USER_ID=your_id
```

**B. ID/PW 직접** — 2026-05 보호 스크립트로 막힐 수 있음.

```sh
HOMETAX_USER_ID=your_id
HOMETAX_PASSWORD=your_password
HOMETAX_RRN=990101-1
```

서버 실행:

```sh
uv run --env-file .env python examples/web-sample/server.py
```

브라우저에서 `http://127.0.0.1:8787/` 접속 → 귀속연도 입력 → 조회 버튼.

호스트/포트 변경:

```sh
HOST=0.0.0.0 PORT=8080 uv run --env-file .env python examples/web-sample/server.py
```

## 응답 형식

조회 성공 시:

```json
{
  "user_name": "...",
  "tin": "...",
  "attr_year": 2024,
  "inquiries": {
    "income_statements": {"status": "ok", "count": 5, "items": [...]},
    "tax_filings":       {"status": "ok", "count": 1, "items": [...]},
    "filing_help":       {"status": "ok", "filing_kind": "..."},
    "address":           {"status": "found", "road_address": "..."}
  },
  "elapsed_sec": 1.23
}
```

각 inquiry 가 인증 등급 부족 등으로 거부되면 그 항목만 `status: "error"`
+ `type` (라이브러리 예외 클래스 이름) + `message` 로 표기. 다른 항목은
계속 진행됨.

호출 자체가 실패하면 HTTP 4xx/5xx + `error_type` 으로 응답.

## 인증 등급별 동작

조회 메뉴에 따라 인증 등급 요구가 다르다 (`docs/architecture.md` 참조).

| 메뉴 | 쿠키/카카오 OACX | ID/PW 세션 |
|---|---|---|
| `income_statements` | ✓ | ✗ (`LoginRequiredError`) |
| `tax_filings` | ✓ | ✗ (`LoginRequiredError`) |
| `filing_help` | ✓ | ✓ |
| `address` | ✓ | ✓ |

ID/PW 만 가지고 실행하면 `income_statements` / `tax_filings` 가 error
status 로 떨어지지만, `filing_help` / `address` 는 정상 동작.

## 운영 워크플로 (사무실 등) 와의 차이

이 데모에서 의도적으로 빠진 기능들:

- 일괄 조회 (엑셀 업로드)
- 디스크 저장 / ZIP 다운로드 / 매니페스트 영속화
- 동시성 제어 (lock/queue/busy state)
- UI 비밀번호 보호
- 다중 사용자 격리
- PDF / Excel 렌더링 (`_html_to_pdf` 같은 subprocess Chrome 호출)
- 한국어 파일명 stem 결정
- 바탕화면 폴더 구조 자동 생성

이런 기능이 필요한 사무실 워크플로는 **별도 워크플로 패키지** 에서 본
라이브러리를 dependency 로 사용해 구현하는 것을 권장한다 (라이브러리는
HTTP-only 데이터 평면만, 워크플로는 사무실 운영 책임).

## 보안 주의

- 이 서버 자체에는 인증/접근 제어가 없다. 외부에 노출하지 말 것.
  (`HOST=0.0.0.0` 사용 시 같은 네트워크 사용자 누구나 조회 실행 가능.)
- `.env` / cookies 파일 / 캐시 세션은 `.gitignore` 처리되어 있지만 PC
  공유 시 파일 권한도 확인.
- 조회 결과에는 본인 명의 자료가 포함되므로, 서버 로그 / 브라우저 캐시
  / 화면 캡처 처리에 유의.
