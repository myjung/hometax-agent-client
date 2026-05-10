# Security Policy

## 보고 (Reporting a vulnerability)

본 라이브러리는 사용자의 홈택스 자격증명과 세션 쿠키를 다루므로 보안 이슈는
**공개 issue 가 아닌 비공개 채널** 로 보고해 주십시오.

권장 경로:

1. **GitHub Security Advisory** — 본 repo 의 Security 탭 →
   "Report a vulnerability" (private 트랙).
2. **이메일** — `jmy1330@gmail.com` (관리자). 가능하면 GPG 암호화.

다음 정보를 함께 보내주시면 도움이 됩니다:

- 영향 받는 버전 (`pip show hometax-agent-client` 또는 git commit hash).
- 재현 절차 (가능하면 minimal repro 코드).
- 영향 범위 (자격증명 노출 / 임의 코드 실행 / 세션 탈취 등).
- 발견 환경 (OS, Python 버전, 네트워크 환경).

PoC 에 **본인 자격증명을 포함하지 마세요** — 합성 / 마스킹 값 또는 일반화
설명을 첨부해 주시면 됩니다. 부득이하게 본인 캡처를 첨부할 경우 PII 마스킹은
[`tests/fixtures/README.md`](tests/fixtures/README.md) 의 규칙을 따라 주세요.

## 우리가 보안 이슈로 다루는 범위

- 라이브러리가 사용자 자격증명을 의도하지 않은 경로 (외부 서버, 로그 파일,
  unprotected file, git tracked file 등) 로 누설하는 경우.
- 라이브러리에 대한 입력 (cookies 파일, 응답 본문 등) 으로 임의 코드 실행이
  유발되는 경우.
- 세션 캐시 파일이 의도된 권한 (`0o600`) 보다 느슨하게 저장되는 경우.
- 의존성 (`curl-cffi`, `httpx`, `lxml`, `playwright` 등) 의 알려진 CVE 가
  본 라이브러리 사용 패턴에서 직접 영향을 주는 경우.
- 부트스트랩 도구 (`hometax_client.bootstrap`) 가 사용자 cookies / HAR 을
  의도하지 않은 위치에 저장하거나 외부에 송신하는 경우.

## 우리가 보안 이슈로 다루지 않는 범위

다음은 보안 이슈가 아니라 **기능 / 호환성 이슈** 로 분류합니다 — 일반 issue 로
신고해 주세요:

- 홈택스가 라이브러리 호출을 거부 / 차단하는 경우 (`BlockedError`,
  `ProtectedLoginError`, `SessionExpiredError`, `AuthGradeInsufficientError`).
- 응답 schema 변경으로 parser 가 깨지는 경우 (`ResponseSchemaDriftError`).
- NTS_KEYS 가 회전되어 서명이 거부되는 경우 — `python -m hometax_client.health
  --refresh` 또는 PR 로 baseline 갱신.
- 새 인증 방식 (NPKI 등) 미지원.

## 자격증명 안전성 — 라이브러리 동작

본 라이브러리가 자격증명을 다루는 방식 (사용자 검증용):

| 항목 | 동작 |
|---|---|
| **외부 통신** | `hometax.go.kr` 서브도메인 + `apct.hometax.go.kr` (NetFunnel 큐) 만. 그 외 호스트로 어떤 데이터도 송신 안 함. |
| **로그 / 텔레메트리** | 없음. stdout/stderr 출력은 사용자가 명시적으로 부른 함수의 결과 / 예외만. |
| **메모리** | ID/PW/RRN 은 `IdPwAuth` 인스턴스 수명 동안 보유. `to_client()` 후엔 인증 토큰만. |
| **디스크** | `save_session` / `SessionStore.save` 가 사용자 지정 경로에 cookies + user_id + tin 저장. 권한 `0o600` (atomic write). 비밀번호 / RRN 은 디스크 저장 안 함. |
| **세션 cookies 보존 범위** | `constants.ESSENTIAL_COOKIES` 에 등록된 쿠키만 저장 — UI 부가 쿠키 제외. |
| **NTS_KEYS** | `crypto.NTS_KEYS_BASELINE` 은 `common_te-min.js` 에서 추출한 평문 mixing constants — 서버측 비밀 아님. cache 갱신 시 `~/.cache/hometax-agent-client/nts_keys.json` 권한은 OS 기본값 (현재 0o600 미적용 — TODO 항목). |
| **부트스트랩 도구 산출물** | `bootstrap.CaptureSession` 이 cookies / HAR / storage_state 를 사용자 지정 디렉토리에 저장 (기본 `captures/` — `.gitignore` 됨). HAR 에는 ID/PW 인증 시 비밀번호가 포함될 수 있음 — 분석 후 삭제 권장. |

## 의존성 보안

핵심 의존성:

- `curl-cffi` — TLS fingerprint 통과용. 알려진 CVE 모니터링.
- `httpx` — 보조 HTTP 호출.
- `lxml` / `beautifulsoup4` — HTML 파싱 (XML external entity 취약점 주의:
  본 라이브러리는 신뢰된 홈택스 응답만 파싱).
- `playwright` (`[bootstrap]` extras 만) — 브라우저 자동화.

`uv lock` 으로 정확한 버전이 `uv.lock` 에 고정되어 있습니다. 보안 업데이트는
patch release 로 반영합니다.

## 응답 시간

- **24 시간 내**: 보고 접수 확인 회신.
- **1 주일 내**: 영향 평가 및 fix 일정 / 거부 사유 회신.
- **30 일 내**: critical 취약점 fix 배포 (가능한 경우).

비-critical 이슈는 다음 minor release 일정에 따릅니다.

## 책임 공개 (Coordinated disclosure)

- 보고자 측에서 fix 배포 전 공개를 자제해 주시면 감사하겠습니다.
- 보고자가 공개를 원하면 fix release 와 동시에 GitHub Security Advisory 에
  credit 함께 게시.
- 90 일 disclosure 정책 (보고 후 90 일 경과 시 보고자 단독 공개 가능).
