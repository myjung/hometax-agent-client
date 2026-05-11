# Contributing

기여 환영합니다. 아래 절차와 컨벤션을 따라주시면 리뷰가 빠릅니다.

## 보안 이슈

자격증명 / 세션 / PII 노출 관련 취약점은 **공개 issue 대신** [`SECURITY.md`](SECURITY.md)
의 비공개 보고 절차를 따라주세요.

## 개발 환경

```bash
git clone <repo>
cd hometax-agent-client

# 모든 extras 설치 (bootstrap, test 포함)
uv sync --all-extras

# 라이브 부트스트랩이 필요하면 한 번 더:
.venv/bin/playwright install chromium    # 또는 --channel chrome 사용
```

Python 3.12 이상.

## 테스트

```bash
# 오프라인 회귀 (기본 — 항상 실행)
.venv/bin/pytest -q

# 라이브 drift 검사 (네트워크 + 홈택스 접근 가능 시)
HOMETAX_LIVE=1 .venv/bin/pytest tests/test_keys_live.py

# 단일 테스트
.venv/bin/pytest tests/test_crypto.py::test_extract_keys_from_js_with_real_excerpt
```

PR 은 오프라인 회귀가 통과해야 머지됩니다. 라이브 테스트는 게이트 (`HOMETAX_LIVE=1`)
이므로 CI 에서는 skip — 개발자 로컬 / cron 으로 검증.

## Lint / 포맷

```bash
.venv/bin/ruff check hometax_client/ examples/ tests/
.venv/bin/ruff check --fix hometax_client/ examples/ tests/    # 자동 수정
```

PR 통과 조건. 룰 셋 `E + W + F`, line-length 120 은 `pyproject.toml`
`[tool.ruff]` 설정. 새 모듈도 동일 룰 적용.

## 컨벤션

- **네이밍 / 모듈 / 클래스 / 메서드 규약**: [`docs/conventions.md`](docs/conventions.md)
- **새 세목 / 서비스 추가 패턴**: [`docs/extending.md`](docs/extending.md)
- **안정성 계약 (호환성)**: [`docs/compatibility.md`](docs/compatibility.md)
- **검증된 사실 SSOT**: [`docs/hometax-facts.md`](docs/hometax-facts.md) — 새 사실
  추가 시 검증일 + 출처 (캡처 디렉토리 / 코드 위치) 필수
- **에이전트 진입점**: [`AGENTS.md`](AGENTS.md) — Claude Code / Codex /
  Cursor / Aider 등 공용 운영 규칙. 시작점 매트릭스 + PR 기여 가이드 포함.
  `CLAUDE.md` 는 `AGENTS.md` 를 import 하는 얇은 shim.

## Fixture / 캡처 데이터

`tests/fixtures/` 에 캡처된 응답을 추가할 때:

1. **반드시 PII 마스킹** — [`tests/fixtures/README.md`](tests/fixtures/README.md)
   의 마스킹 표 (`tin`, `userId`, `userNm`, `txprDscmNo`, `bmanOfbDt`,
   `pubcUserNo`, `lgnClientIp`, `charId`, R07 `pswd`/`id` 등) 를 따른다.
2. **leak sanity check 필수** — fixture 저장 후 원본 PII 가 결과에 남아있는지
   grep. 한 건이라도 남아있으면 commit 금지.
3. **출처 기록** — `docs/hometax-facts.md` 에 검증일 + 캡처 디렉토리 명시.
4. **캡처 원본은 commit 안 함** — `captures/` 는 `.gitignore` 처리됨.
   fixture 만 commit.

## PR 체크리스트

- [ ] `pytest -q` 통과
- [ ] `ruff check hometax_client/ examples/ tests/` 통과
- [ ] 새 public API 추가 시 type hint + docstring (한국어 우선)
- [ ] 새 dataclass 는 `frozen=True` + `raw: dict` 필드 보유
- [ ] 새 wqAction 호출 시 `facts/current.toml` 에 식별자 분리
- [ ] `docs/` 의 영향 받는 파일 (특히 `hometax-facts.md`) 갱신
- [ ] PII 가 commit 에 포함되지 않음을 확인

## 커밋 메시지

다음 prefix 권장:

- `feat:` 새 기능
- `fix:` 버그 수정
- `docs:` 문서만
- `test:` 테스트만
- `refactor:` 동작 변경 없는 정리
- `chore:` 의존성 / 도구 변경
- `security:` 자격증명 / 세션 / 권한 관련 변경

본문은 **왜 (why)** 를 적어주세요 — what 은 diff 에서 읽힙니다.

## 라이브러리 vs 워크플로 경계

본 라이브러리는 다음을 의도적으로 하지 않습니다 (`docs/architecture.md`
참조):

- 사용자 산출물 디스크 저장 (PDF/Excel/CSV)
- 한국어 파일명 / 폴더명 결정
- 일괄 조회 진행 상태 / 세션 lock / UI
- 자동 세션 refresh / 만료 시 자동 재인증

이런 책임은 호출자 / 워크플로 패키지 (별도 repo) 가 담당합니다. PR 이 이
경계를 넘으면 reject 되거나 별도 패키지로 분리 제안됩니다.

## 응답 시간 / 거부 사유

- 단순 PR (lint / typo / 작은 fix): 2~3 일 내 회신 목표.
- 새 기능 / 새 서비스: 1주 내 응답. 설계 토론이 길어질 수 있음.
- 거부 사유 명시: 라이브러리 경계 위반 / 커버리지 부족 / 보안 위험 / scope
  외.

## 라이선스

기여한 코드는 본 프로젝트의 [MIT 라이선스](LICENSE) 하에 배포됩니다.
