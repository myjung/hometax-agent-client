# tests/fixtures — 회귀용 캡처 응답

홈택스 와이어 응답을 분기/세션 단위 디렉토리에 마스킹해 보관한다. `tests/`
의 회귀 테스트가 이 fixture 들을 읽어 parser 의 호환성을 검증한다 (`docs/
compatibility.md` 의 "회귀 테스트 안전망" 참조).

## 디렉토리 규칙

```
tests/fixtures/
└── <YYYY-MM-DD>/        ← 캡처 일자
    ├── <action>_<state>.json   (wqAction.do 같은 JSON 응답)
    └── <action>_<state>.txt    (pubcLogin.do 처럼 JSONP/text)
```

캡처 일자 + 의미 있는 상태로 구분 (e.g. `pubclogin_step1_rrn_required.txt`).

## PII 마스킹 (필수)

캡처 출처는 본인 명의 세션이지만 fixture 는 repo 에 commit 되므로 모든 PII
는 placeholder 로 치환한다. 치환 규칙은 fixture 셋 안에서 일관되게 (테스트가
검증할 수 있도록).

| 필드 | placeholder |
|---|---|
| `tin`, `cnvrTin` | `000000999999999999` |
| `userId` | `testuser` |
| `userNm` | `홍길동` |
| `txprDscmNo` (앞 6자리) | `990101` (`*******` 부분 그대로) |
| `bmanOfbDt` (생년월일 8자리) | `19990101` |
| `pubcUserNo` | `100000000099999999` |
| `lgnClientIp` | `127.0.0.1` |
| `charId` | `A000000` |
| R07 `pswd` (서버 회전 hex) | `PSWD_PLACEHOLDER_HEX_...` |
| R07 `id` (서버 회전 hex) | `ID_PLACEHOLDER_HEX_...` |

## 새 fixture 추가 절차

1. `captures/<timestamp>/trace.har` (recon 도구 산출물) 에서 응답 본문을 추출.
2. 위 표대로 PII 치환. 누락 검증을 위해 sanity check (원본 PII 가 결과에 없는지)
   필수.
3. `tests/fixtures/<일자>/` 에 의미 있는 이름으로 저장.
4. `tests/test_*.py` 에 fixture 를 읽는 회귀 테스트 추가. 테스트는 placeholder
   값을 검증해야 한다 (실제 PII 가 들어 있다면 그게 보안 사고 신호).
5. `docs/hometax-facts.md` 에 출처 (캡처 디렉토리 / entry 번호) 명시.

## 현재 보관

| 디렉토리 | 출처 | 내용 |
|---|---|---|
| `2026-05-10/` | `captures/2026-05-10T23-12-46/trace.har` ([`docs/hometax-facts.md §15`](../../docs/hometax-facts.md)) | R07 사전 검증, pubcLogin 1·2차, ATXPPAAA001R037 (session_info) |
