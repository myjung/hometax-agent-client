# 다중 세션 관리 — `SessionStore`

세무사 사무실처럼 **여러 고객 세션을 동시에 보유** 해야 할 때 사용한다.
`HometaxClient.from_cookies(path)` / `save_session(path)` 가 단일 파일을
다루는 반면, `SessionStore` 는 **디렉토리 하나** 를 다중 세션 보관소로
취급해 list / open / save / health 를 일관 API 로 제공한다.

## 설계 원칙

`architecture.md` 의 라이브러리/워크플로 경계를 그대로 따른다:

- **파일 IO 만**. 세션 lock / 자동 refresh / 진행 상태 / UI 모두 호출자
  책임.
- **`client_id` 는 호출자 책임**. 동명이인 처리 / slug 규칙은 워크플로 layer.
  허용 문자 `[A-Za-z0-9_-]` 1~64 자 (filesystem 안전).
- **drift-tolerant**. 알지 못하는 필드는 `SessionEntry.raw` 에 보존.
- **마지막-쓰기 우선**. 동시성 제어 없음. 필요 시 OS 레벨 lock 으로 호출자가
  처리.

## 디렉토리 / 파일 형식

기본 위치 `captures/sessions/` (프로젝트 상대, `.gitignore` 됨). 그 외
경로는 호출자가 명시.

```
captures/sessions/
├── kim_chulsoo.json
├── lee_younghee.json
└── park_corp.json
```

각 파일:

```json
{
  "client_id": "kim_chulsoo",
  "label": "김철수",
  "user_id": "kim123",
  "tin": "000000999999999999",
  "auth_method": "idpw",
  "saved_at": 1748000000,
  "last_used_at": 1748100000,
  "cookies": [
    {"name": "TXPPsessionID", "value": "...", "domain": ".hometax.go.kr", "path": "/"},
    ...
  ]
}
```

기존 단일 `.session.json` (`save_session()` 산출) 도 같은 디렉토리에 두면
list 에 잡힌다 — `client_id` 는 파일 stem 으로 fallback. `label` /
`auth_method` 는 `None`. 모든 파일 `0o600`.

## 기본 사용

```python
from hometax_client import SessionStore, HometaxClient
from hometax_client.auth import IdPwAuth

store = SessionStore()  # captures/sessions/

# 1) 새 고객 세션 발급해서 저장
auth = IdPwAuth(user_id="kim123", password="...", rrn="900101-1")
client = HometaxClient.login(auth=auth, cache_path="/tmp/__throwaway.json")
store.save(client, client_id="kim_chulsoo", label="김철수", auth_method="idpw")

# 2) 어떤 세션이 있는지 둘러보기
for entry in store.list():
    print(entry.client_id, entry.label, entry.tin, entry.auth_method)

# 3) 세션 재사용
client = store.open("kim_chulsoo")  # last_used_at 자동 갱신
info = client.session_info()
statements = client.inquiries.income_statements(attr_year=2024)

# 4) 세션 신선도 검사
health = store.health("kim_chulsoo")          # cheap meta — 네트워크 0회
if health.fresh:
    print("recent")
else:
    print(f"stale → {health.reason}")
```

## API

### Discovery

| 메서드 | 반환 |
|---|---|
| `store.list()` | `list[SessionEntry]` — 정렬 (client_id) |
| `store.get(client_id)` | `SessionEntry | None` |
| `store.find_by_tin(tin)` | `SessionEntry | None` |
| `store.find_by_user_id(user_id)` | `SessionEntry | None` |
| `client_id in store` | `bool` (잘못된 형식이면 False, raise X) |
| `len(store)` | int |
| `for entry in store: ...` | iterator |

### Read / Write

| 메서드 | 동작 |
|---|---|
| `store.open(client_id)` | `HometaxClient` 반환 + `last_used_at` 자동 갱신. 없으면 `KeyError` |
| `store.save(client, client_id=..., label=..., auth_method=...)` | 저장된 `Path` 반환. 잘못된 `client_id` 형식 → `ValueError` |
| `store.touch(client_id)` | 쿠키 변경 없이 `last_used_at` 만 갱신 |
| `store.remove(client_id)` | 삭제. 존재했으면 `True`, 없었으면 `False` |

### Health

```python
store.health(client_id, *, live=False) -> SessionHealth
store.health_all(*, live=False) -> list[SessionHealth]
```

`SessionHealth` 의 `reason` 분기:

| `reason` | 의미 | `fresh` |
|---|---|---|
| `recent` | `last_active` 가 `fresh_within_sec` (기본 1800초) 이내 | True |
| `stale` | 그보다 오래됨 | False |
| `missing` | client_id 가 store 에 없음 | False |
| `verified` | `live=True` 에서 `session_info()` 정상 반환 | True |
| `session_expired` | `live=True` 에서 `SessionExpiredError` | False |
| `error:<ExcClass>` | `live=True` 에서 다른 `HometaxError` / 예외 | False |

`live=False` (기본) 는 메타데이터만 본다 — 네트워크 0회, 빠름. `live=True`
는 실제 `session_info()` 호출 — 권위 있지만 비용. 일괄 sweep 에선 보통
`live=False` 로 후보 좁히고 의심스러운 것만 `live=True`.

## 재인증 흐름 분기 패턴 (`auth_method` 활용)

만료 시 라이브러리는 자동 재인증 안 한다. 호출자가 `auth_method` 메타로
분기:

```python
import os
from hometax_client import SessionStore, HometaxClient
from hometax_client.auth import IdPwAuth, KakaoAuth, NaverAuth

store = SessionStore()

def get_client(client_id: str) -> HometaxClient:
    health = store.health(client_id, live=True)
    if health.fresh:
        return store.open(client_id)

    entry = store.get(client_id)
    if entry is None:
        raise KeyError(f"unknown client: {client_id}")

    # 만료 — auth_method 별 재인증
    if entry.auth_method == "idpw":
        auth = IdPwAuth(
            user_id=os.environ[f"HOMETAX_{client_id.upper()}_ID"],
            password=os.environ[f"HOMETAX_{client_id.upper()}_PW"],
            rrn=os.environ[f"HOMETAX_{client_id.upper()}_RRN"],
        )
    elif entry.auth_method == "kakao":
        auth = KakaoAuth(...)
    elif entry.auth_method == "naver":
        auth = NaverAuth(...)
    else:
        raise RuntimeError(f"{client_id}: 자동 재인증 불가 (auth_method={entry.auth_method})")

    auth.authenticate()
    client = auth.to_client()
    client.session_info()
    store.save(
        client, client_id=client_id,
        label=entry.label, auth_method=entry.auth_method,
    )
    return client
```

이 함수가 워크플로 레이어. 라이브러리는 정보 (`auth_method`, `health.reason`)
만 제공.

## 동시성

**lock 없음**. 동일 `client_id` 에 두 프로세스가 동시에 `save()` 하면
last-write-wins (write 자체는 atomic — `tempfile + os.replace` — 이므로
partial file 은 안 생긴다). 동시 발급/갱신을 막아야 하면 워크플로에서
OS lock (`fcntl.flock`, `portalocker` 등) 으로 처리.

`open()` 은 read-only 라 안전. `touch()` 는 read-modify-write 라 race
가능 — 손해는 last_used_at 약간 어긋남 정도.

## 테스트 / 회귀

`tests/test_sessions.py` 22 테스트 — list/get/save/open/touch/remove/health
모든 분기 + drift 보존 + atomic write 회귀 안전망.

## 관련

- `tests/test_sessions.py` — 22 테스트
- `hometax_client/sessions.py` — 구현
- `architecture.md` §라이브러리 vs 워크플로 경계 — 본 모듈이 그 경계 안에
  머무르는 이유
