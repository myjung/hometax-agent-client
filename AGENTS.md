# AGENTS.md

여러 AI 에이전트 (Claude Code / Codex / Cursor / Aider 등) 가 이 레포에서 공통으로 사용하는 운영 규칙. `CLAUDE.md` 도 이 파일을 import 한다.

## 한 줄 요약

`hometax-agent-client` 는 홈택스(`hometax.go.kr`) `wqAction.do` 의 **HTTP 캡처-리플레이 라이브러리**다. 브라우저를 띄우지 않고 (단, 부트스트랩용 Playwright 는 `[bootstrap]` extras 에 옵션) 세션 쿠키 + HMAC 서명만으로 호출한다. AI 에이전트가 다중 고객의 세무 자료를 안전하게 읽고/처리할 수 있게 한다.

## 작업 전 반드시 확인 — 시작점 매트릭스

어떤 작업이든 시작하기 전에 자기 작업이 어디에 해당하는지 먼저 확인. 잘못된
문서부터 읽기 시작하면 컨텍스트만 낭비된다. 막힐 때는 "막힐 때 fallback" 의 docs.

| 작업 종류 | 진입점 (코드) | 봐야 할 docs (순서) | 막힐 때 fallback |
| --- | --- | --- | --- |
| 사용자 자연어 요청 처리 (조회 / 인증 / 만료 안내) | `client.<service>.<method>` 또는 `client.wq_action(...)` | `README.md` §주요 특징 → `docs/architecture.md` (두 층 API) → 해당 service docstring | `hometax_client/exceptions.py` (에러 분기) + `docs/sessions.md` |
| 새 조회 / service 추가 | `services/<area>.py` + `facts/current.toml` | `docs/extending.md` → `docs/hometax-facts.md` → `docs/conventions.md` | `docs/recon.md` (캡처로 wire 검증) |
| 응답 드리프트 / 새 필드 출현 | `models.raw`, `ResponseSchemaDriftError` | `docs/compatibility.md` → `docs/conventions.md` | `docs/hometax-facts.md` (검증 사실 단일 출처) |
| 새 인증 방식 추가 (NPKI 등) | `auth/<provider>.py` | `docs/extending.md` → `docs/recon.md` → `docs/hometax-facts.md` §pubcLogin | `bootstrap` 으로 직접 캡처 후 재검증 |
| 다중 세션 운영 (세무사 다중 고객) | `SessionStore` | `docs/sessions.md` | `hometax_client/exceptions.py` (만료/권한 분기) |
| 새 메뉴 발견 / 분석 | `bootstrap.CaptureSession` + `iter_wq_actions` | `docs/recon.md` | `docs/hometax-facts.md` §주의사항 |
| `NTS_KEYS` 회전 / 서명 알고리즘 변경 | `python -m hometax_client.health` | `hometax_client/crypto.py` docstring | `tests/test_crypto.py` (알고리즘 회귀) |

읽지 않고 시작하면 잘못된 문서에서 헤매기 쉽다. 작업 종류가 위에 없으면
사용자에게 한번 더 명확히 묻고 시작.

## PR 기여 (외부 / 에이전트)

라이브러리 코어와 `examples/` 의 책임 경계를 다르게 적용한다.

**라이브러리 코어 (`hometax_client/`) — 흡수**

- 새 service / 새 조회 (`services/<area>.py` + `facts/current.toml`)
- 새 인증 방식 (`auth/<provider>.py`)
- `facts/current.toml` 갱신 (action ID / 화면 ID 변경 대응)
- 에러 분류 개선 (`HometaxError` 하위 계층)
- bug fix / regression test 픽스처 (PII 마스킹된 것만)

**라이브러리 코어 — 거절. `examples/` 로는 환영**

- 파일 IO (PDF/Excel/CSV 저장, 파일명 생성, 디스크 폴더 규칙)
- 로컬 UI / 웹서버
- 한국어 stemming / 자연어 매핑
- 배치 / 진행률 / 다중 고객 자동화
- 윈도우 `.bat` / `.ps1` (코어는 cross-platform Linux 우선, `examples/` 는 OS 별 환영)

**`examples/` 가드레일** ([`examples/README.md`](examples/README.md))

1. demo 1개 = 한 파일. 부풀려진 모놀리식 거절 (3,000줄 짜리 웹 앱 클라이언트 같은 것).
2. 외부 의존성은 최대한 축소하며 반드시 필요하면 `pyproject.toml` `[examples]` extra 로 격리. 코어 `dependencies` 에 추가 금지.
3. PII 출력 위치 / 마스킹 / 권한 (`0o600` 권장) 명시.
4. `examples/README.md` 인덱스 갱신 (외부 contributor 진입점).
5. 라이브러리 API 변경에 깨지지 않는지 import 가능성만은 검증.

**PR 공통 체크리스트**

- 시작점 매트릭스의 해당 작업 행 docs 모두 통과.
- `ruff check hometax_client/ examples/ tests/` 통과.
- 새 로직은 픽스처 기반 테스트 (실제 PII 없음).
- 캡처 / 응답 본문에 실제 PII (RRN / TIN / 사번 / 사무실 정보) 없음 재확인.

정식 `CONTRIBUTING.md` + PR / Issue template 은 public 전환 직전에 별도 작업.

## 실행 명령

```bash
# 개발 환경 설치 (.venv 생성, uv 사용)
uv sync --all-extras

# 테스트
.venv/bin/pytest
.venv/bin/pytest tests/test_crypto.py::test_specific   # 단일 테스트

# lint (PR 게이트) — ruff (E + W + F, line-length 120 은 pyproject 설정)
.venv/bin/ruff check hometax_client/ examples/ tests/
.venv/bin/ruff check --fix hometax_client/ examples/ tests/   # 자동 수정

# 예제 실행 (`.env` 필요, `.env.example` 참고)
.venv/bin/python examples/basic_inquiry.py
.venv/bin/python examples/auth_kakao.py
```

`[bootstrap]` extra (`uv sync --extra bootstrap`) 는 Playwright 를 가져온다.
2026-05 `pubcLogin` 보호 스크립트가 직접 ID/PW POST 를 막을 때 쿠키 부트스트랩
용도로만 사용. 라이브러리 코어는 Playwright 를 import 하지 않는다.

## 작업 원칙

- **사용자/문서/주석은 한국어 일차**. 영어 보조 허용.
- **HTTP-only 정책**. 라이브러리 코어는 `playwright` / `selenium` / `httpx-browser` 등을 import 하지 않는다. 부트스트랩 도구는 `hometax_client.bootstrap` 서브패키지에 격리.
- **PDF / Excel / CSV / Korean stemming / 파일명 생성 / 배치 / UI** 는 라이브러리 범위 밖. 워크플로 계층에서 처리.
- **와이어 키 (예: `attrYr`, `txprDscmNo`, `agitxRtnInqrDVOList`) 는 반환 dict 와 `dataclass.raw` 에 무변형으로 보존**. 영문 snake_case 는 typed 필드 (`attr_year`, `payer_tin`) 에만 적용.
- **에러는 타입으로 분기**. `HometaxError` 하위 계층 사용. 한국어 메시지 문자열 매칭으로 callers 가 분기하게 만들지 않는다.
- **action_id / screen_id 는 `hometax_client/facts/current.toml` 한 곳**. 서비스 모듈에 하드코딩 금지.
- **모든 모델에 `raw: dict` 필드**. 응답 드리프트에 견디기 위함.

## 보안 / PII

- `captures/`, `out/`, `*.session.json`, `.env`, `tests/fixtures/` 내부 실제 PII 는 `.gitignore` 로 차단된다. 커밋 전에 항상 확인.
- 테스트 픽스처는 마스킹된 데이터 전용. PII 매핑은 `tests/fixtures/<날짜>/README` 또는 위 문서에 명시. 실제 RRN/TIN/사번/사무실 정보는 절대 커밋하지 않는다.
- `save_session` 은 `0o600` 으로 디스크에 쓴다. 다른 세션 저장 경로도 같은 정책.

## 라이브러리 capability 표현 가이드

- 현재 구현 안 된 기능은 "현재 미구현" / "현재 미지원" 으로 표기. **"read-only 만 지원" / "의도적으로 read-only" 같은 미래 scope 자기제한 표현 금지**.
- 법적 / 책임 disclaimer (이용약관 / 법규 / 사용자 책임) 는 강하게 유지. 기능 scope 단정과 다른 차원.
- 동명이인 / 위임 관계 같은 도메인 검증은 호출자 책임. 라이브러리는 검증하지 않는다.

## 작업 흐름

1. 큰 변경은 **설계안 (API surface, tradeoff, 결정 포인트)** 먼저 사용자에게 제시 → OK 받고 구현. 사용자 협업 스타일 "검토 후 진행".
2. 새 조회/서비스 추가는 `docs/extending.md` 체크리스트를 따른다.
   - 캡처 → `docs/hometax-facts.md` §section → `facts/current.toml` 엔트리 → `models.py` dataclass (with `raw`) → `services/<area>.py` (typed + `raw_*` 둘 다) → `HometaxClient` lazy property → 픽스처 기반 파서 테스트.
3. `ruff check hometax_client/ examples/ tests/` 통과 필수 (PR 게이트). 룰 셋 `E + W + F`, line-length 120 은 `pyproject.toml [tool.ruff]` 설정.
4. 커밋은 사용자가 내용 검토 후 직접 진행. 에이전트가 무단으로 push / PR / public 전환 / PyPI 배포하지 않는다.

## 외부 surface 정책

- GitHub repo 현재 **private** (검토 후 public 전환 예정).
- PyPI: `0.1.0a1` 게시됨 (이름 선점). 정식 릴리스는 `git tag v0.1.0 && git push origin v0.1.0` 가 자동 publish — 사용자 단독 결정.
- public 전환 / 릴리스 / PR 머지 / 외부 시스템 게시는 사용자 명시 승인 후에만.

## 응답 드리프트 대응

| 상황 | 대응 |
| --- | --- |
| 새 필드 출현 | `dataclass.raw` 로 자동 surface — 코드 변경 불요 |
| 핵심 필드 누락 | `ResponseSchemaDriftError(action_id, missing, raw)` |
| action ID 변경 | `facts/current.toml` 한 줄 수정 후 patch 릴리스 |
| `NTS_KEYS` 회전 | `python -m hometax_client.health --refresh` 로 캐시 갱신. 알고리즘 자체가 바뀌면 `tests/test_crypto.py` 가 실패 |

## 막혔을 때

- `git log --oneline -20` 으로 최근 컨텍스트 복원.
- `docs/hometax-facts.md` 에 캡처 기반 검증 사실 확인.
