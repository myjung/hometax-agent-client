---
name: 버그 / 회귀
about: 라이브러리 동작이 docstring / docs 와 다름. 또는 정상 호출인데 깨짐.
labels: bug
---

<!-- ⚠️ 자격증명 / 세션 / 주민번호 / TIN / 사무실 정보 등 PII 는 절대 붙이지 마세요. -->

## 무엇이 깨졌나

<!-- 한두 문장 — 예: "income_statements(2024) 가 자료 0건일 때 빈 list 가 아니라 raise" -->

## 재현 (가능한 최소 코드)

```python
from hometax_client import HometaxClient
...
```

## 예상 vs 실제

- 예상:
- 실제:

## 환경

- `hometax-agent-client` 버전:
- Python:
- OS:
- 인증 종류 (kakao / naver / idpw / 비회원):

## 추가 컨텍스트

- 관련 액션 ID / screen ID (PII 아님):
- 라이브러리 에러 타입 (`HometaxError` 하위) 와 메시지 첫 200자:
