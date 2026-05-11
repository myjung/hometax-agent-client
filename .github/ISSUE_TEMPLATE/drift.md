---
name: 응답 드리프트 / 홈택스 변경 감지
about: 라이브러리가 기대한 응답 shape 과 다름. `ResponseSchemaDriftError` raise 또는 라이브 회귀.
labels: drift
---

<!-- ⚠️ 응답 본문 첨부 시 PII 마스킹 필수: RRN / TIN / 사번 / 사무실 정보 등. -->

## 어떤 드리프트인가

- [ ] 새 필드 출현 (`raw` 로 자동 surface — 보고만)
- [ ] 핵심 필드 누락 (`ResponseSchemaDriftError`)
- [ ] action_id / screen_id 가 더 이상 동작 안 함
- [ ] `NTS_KEYS` 회전 의심 (`tests/test_keys_live.py` 실패)
- [ ] 알고리즘 자체 변경 의심 (`tests/test_crypto.py` 실패)

## 영향 범위

- 라이브러리 메서드:
- 액션 ID / 화면 ID:
- 호스트 (hometax / teht / tewe / ...):

## 응답 변화 (PII 마스킹)

```json
{ ... }
```

## 라이브러리 버전 / 검증일

- 본 버전 (`pip show hometax-agent-client`):
- 마지막 정상 동작 (대략):
- 감지 시점:
