<!--
이 PR template 은 [`AGENTS.md`](../AGENTS.md) §"PR 기여 (외부 / 에이전트)" 의
요약본입니다. 자세한 가이드는 거기를 보세요.
-->

## 변경 종류 (해당하는 곳에 X)

- [ ] 새 service / 조회 (`services/<area>.py` + `facts/current.toml`)
- [ ] 새 인증 방식 (`auth/<provider>.py`)
- [ ] `facts/current.toml` 갱신 (홈택스 action / screen 변경 대응)
- [ ] 에러 분류 개선 (`HometaxError` 하위)
- [ ] bug fix / regression test 픽스처
- [ ] docs 만 / refactor 만
- [ ] **`examples/` demo 추가/수정** (`examples/README.md` 가드레일 따름)

## 요약 / 동기

<!-- 왜 (why) 가 핵심. 무엇 (what) 은 diff 에서 읽힌다. -->

## 작업 종류 매트릭스 — AGENTS.md 의 어느 행?

<!-- 사용자 자연어 요청 처리 / 새 조회 추가 / 응답 드리프트 / 새 인증 / 다중 세션 / 새 메뉴 발견 / NTS_KEYS 회전 -->

행:

읽은 docs (순서):

## 검증 명령

```bash
.venv/bin/pytest -q
.venv/bin/ruff check hometax_client/ examples/ tests/
```

결과:

## 라이브러리 vs 워크플로 경계

이 PR 이 `hometax_client/` (라이브러리 코어) 와 `examples/` (demo) 중 어느
쪽인지 명시. 코어 거절 영역 (파일 IO / UI / PDF·Excel·CSV / 한국어
stemming / 배치 / 윈도우 `.bat`) 은 `examples/` 로만 환영.

## 체크리스트

- [ ] `pytest -q` 통과
- [ ] `ruff check hometax_client/ examples/ tests/` 통과
- [ ] 새 public API 에 type hint + docstring (한국어 우선)
- [ ] 새 dataclass 는 `frozen=True` + `raw: dict` 필드
- [ ] 새 wqAction 호출 시 `facts/current.toml` 에 식별자 분리
- [ ] `docs/` 의 영향 받는 파일 갱신 (특히 `docs/hometax-facts.md`)
- [ ] **캡처 / 응답 본문에 실제 PII (RRN / TIN / 사번 / 사무실 정보) 없음**
- [ ] `examples/` 추가 시 `examples/README.md` 인덱스 갱신
