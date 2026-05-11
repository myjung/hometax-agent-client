# AGENTS.md

여러 AI 에이전트 (Claude Code / Codex / Cursor / Aider 등) 가 이 레포에서 공통으로 사용하는 운영 규칙. `CLAUDE.md` 도 이 파일을 import 한다.

## 한 줄 요약

`hometax-agent-client` 는 홈택스(`hometax.go.kr`) `wqAction.do` 의 **HTTP 캡처-리플레이 라이브러리**다. 브라우저를 띄우지 않고 (단, 부트스트랩용 Playwright 는 `[bootstrap]` extras 에 옵션) 세션 쿠키 + HMAC 서명만으로 호출한다. AI 에이전트가 다중 고객의 세무 자료를 안전하게 읽고/처리할 수 있게 한다.

## 작업 전 반드시 확인

| 문서 | 목적 |
| --- | --- |
| `docs/architecture.md` | 두 층 API (`client.<service>.<method>` vs `wq_action`) / 라이브러리 vs 워크플로 경계 |
| `docs/conventions.md` | 와이어 키 무변형 / 영문 snake_case 한 곳 / 명명 (`*Service`/`*Result`/`*Error`) |
| `docs/extending.md` | 새 조회/서비스 추가 체크리스트 |
| `docs/compatibility.md` | 안정성 컨트랙트 — 깨면 major bump |
| `docs/hometax-facts.md` | 캡처로 검증된 홈택스 식별자 단일 출처 |
| `docs/sessions.md` | `SessionStore` 다중 세션 관리 |
| `docs/recon.md` | `[bootstrap]` Playwright 리콘 도구 |

읽지 않고 만지면 디자인 컨트랙트가 깨진다.

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
