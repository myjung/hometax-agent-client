# examples

`hometax-agent-client` 라이브러리를 어떻게 호출하는지 보여주는 작은 demo
모음. **본격 사무실 운영용 워크플로는 별도 패키지로 만들 영역** — 본
디렉토리의 데모는 학습 / 참조 / e2e 검증용이다.

라이브러리 코어 정책 (HTTP-only / 워크플로 외부화) 과 충돌하지 않으면서,
일반 사용 시나리오 (파일 저장 / 다중 고객 배치 / 로컬 UI 등) 의 demo 는
환영. 자세한 PR scope 는 [`../AGENTS.md`](../AGENTS.md) §"PR 기여" 참조.

## 인덱스

| 파일 | 무엇을 보여주는가 |
| --- | --- |
| `auth_idpw.py` | ID/PW 직접 로그인 흐름. 2026-05 `pubcLogin` 보호 스크립트 주의사항 포함 |
| `auth_kakao.py` | 카카오 OACX 간편인증 → 세션 캐시 (1차 인증 표준 흐름) |
| `auth_naver.py` | 네이버 OACX (카카오와 갈리는 부분 stage 별 verbose 로깅) |
| `basic_inquiry.py` | 기존 쿠키 (`from_cookies`) 로 기본 조회 |
| `income_tax_inquiry.py` | 종합소득세 신고도움 — 자료구분별 소득내역 / 신고안내문 / 보험료 |
| `recon_login.py` | Playwright 로 로그인 캡처 (`--resume` 으로 세션 재사용 둘러보기 가능) |
| `recon_e2e_naver.py` | Naver 인증 → `export_storage_state` → CaptureSession resume → HAR 분석 한 흐름 (에이전트 주도) |
| `web-sample/` | 옛 `hometax-tools` 의 3,000줄 웹 UI 를 한 화면 / 한 폼 / 한 호출로 압축한 demo |

## 가드레일 (새 demo 추가 시)

[`../AGENTS.md`](../AGENTS.md) §"`examples/` 가드레일" 의 5개 규칙. 요약:

1. **demo 1개 = 한 파일** (또는 web-sample 처럼 한 작은 디렉토리). 부풀려진
   모놀리식 거절.
2. **외부 의존성은 최대한 축소.** 반드시 필요하면 `pyproject.toml`
   `[examples]` extra 로 격리. 코어 `dependencies` 에 추가 금지.
3. PII 출력 위치 / 마스킹 / 권한 (`0o600`) 명시. 디스크 출력은
   `captures/` 나 `out/` 같이 `.gitignore` 된 경로 또는 사용자 명시 경로만.
4. 본 인덱스 표에 한 줄 추가.
5. 라이브러리 API 변경에 깨지지 않는지 import 가능성만은 확인.

## 새 demo 추가 패턴

```bash
# 1. demo 작성 — 한 파일, docstring 으로 사전 조건 / 실행법 / 산출물 명시
vim examples/my_demo.py

# 2. 본 README 인덱스 표에 한 줄 추가

# 3. (의존성 있다면) pyproject.toml 의 [project.optional-dependencies] 에
#    [examples] extra 추가 — 코어 dependencies 는 건드리지 않는다
vim pyproject.toml

# 4. import 가능성 확인 + ruff
.venv/bin/python -c "import ast; ast.parse(open('examples/my_demo.py').read())"
.venv/bin/ruff check examples/my_demo.py
```

본격 워크플로 (자동 배치 / 사무실 운영 / 사용자 자료 일괄 다운로드 등) 가
demo 의 경계를 넘는다고 느껴지면, 별도 패키지로 분리하고 본 라이브러리를
의존성으로 가져가는 게 맞다.
