# Extending — 새 세목 / 메뉴 추가

법인세, 원천세, 양도소득세, 부가가치세 등 새 세목을 추가할 때 따르는 패턴.

## 0. 사전: 캡처

홈택스에서 해당 메뉴를 실제로 한 번 사용해 네트워크 요청을 캡처한다.
캡처 데이터는 `captures/` (gitignore) 에 둔다. 라이브러리 추가에 필요한
정보:

- 화면 ID (예: `UTERNAxxx`)
- 액션 ID 와 사용 위치 (예: 목록 조회 `ATERNAxxxR01`, 상세 조회 `R02`)
- 서브시스템 호스트 (`hometax`, `teht`, `tewe`, ...)
- 요청 본문 형태 (자료구분, 페이지네이션, 필수 필드)
- 응답 본문 핵심 키 (목록 dataset, 상세 dataset)
- 인증 등급 (ID/PW 로 호출되는지, 카카오 이상 필요한지)

## 1. 사실 카탈로그 갱신

`docs/hometax-facts.md` 에 §추가:

```markdown
## §15. 양도소득세 신고

검증일: 2026-12-01 / 출처: captures/2026-12-01_capital_gains/

| 화면/action | 역할 |
|---|---|
| `UTERNAxxx` | 양도소득세 거래내역 조회 화면 |
| `ATERNAxxxR01` | 거래내역 목록 조회 |
| `ATERNAxxxR02` | 거래 상세 조회 |

서브시스템: teht.hometax.go.kr
인증 등급: 카카오 이상 필요 (ID/PW 거부 검증)
```

## 2. `facts/current.toml` 갱신

```toml
[services.capital_gains]
host = "teht"
screen_id = "UTERNAxxx"
list_action = "ATERNAxxxR01"
detail_action = "ATERNAxxxR02"
list_items_key = "transactionList"
referer = "https://teht.hometax.go.kr/.../UTERNAxxx.xml"
```

## 3. dataclass 추가 (선택)

`hometax_client/models.py` 에 응답 행을 위한 dataclass:

```python
@dataclass(frozen=True)
class CapitalGainsTransaction:
    transaction_date: str | None
    asset_type: str | None
    transferred_amount: int | None
    acquisition_amount: int | None
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CapitalGainsTransaction:
        return cls(
            transaction_date=d.get("trsfDt"),
            asset_type=d.get("astTycd"),
            transferred_amount=d.get("trsfAmt"),
            acquisition_amount=d.get("acqsAmt"),
            raw=dict(d),
        )
```

`raw` 필드는 반드시 포함. 와이어 키는 무변형 보존.

## 4. 서비스 모듈 작성

`hometax_client/services/capital_gains.py`:

```python
"""양도소득세 (capital gains tax) 조회 서비스.

화면: UTERNAxxx
인증 등급: 카카오 이상 필요. ID/PW 세션은 SessionExpiredError 로 거부됨.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import facts
from ..models import CapitalGainsTransaction
from ._base import ServiceBase

if TYPE_CHECKING:
    from ..client import HometaxClient


class CapitalGainsService(ServiceBase):
    """양도소득세 조회."""

    def transaction_history(
        self,
        attr_year: int | str,
    ) -> list[CapitalGainsTransaction]:
        """양도소득세 신고 대상 거래내역 조회."""
        spec = facts.lookup("services", "capital_gains")
        tin = self._ensure_tin()
        self._c.activate_subsystem_session(
            host=spec["host"],
            screen_id=spec["screen_id"],
            referer=spec["referer"],
        )
        data = self._c.wq_action(
            action_id=spec["list_action"],
            screen_id=spec["screen_id"],
            host=spec["host"],
            body={
                "attrYr": str(attr_year),
                "tin": tin,
            },
        )
        items = data.get(spec["list_items_key"]) or []
        return [
            CapitalGainsTransaction.from_dict(row) for row in items
        ]

    def raw_transaction_history(
        self,
        attr_year: int | str,
    ) -> dict[str, Any]:
        """저수준 직접 호출 — typed 뷰 대신 응답 dict 통째로 반환."""
        spec = facts.lookup("services", "capital_gains")
        tin = self._ensure_tin()
        self._c.activate_subsystem_session(
            host=spec["host"],
            screen_id=spec["screen_id"],
            referer=spec["referer"],
        )
        return self._c.wq_action(
            action_id=spec["list_action"],
            screen_id=spec["screen_id"],
            host=spec["host"],
            body={"attrYr": str(attr_year), "tin": tin},
        )
```

## 5. `client.py` 에 lazy property 추가

```python
@property
def capital_gains(self) -> CapitalGainsService:
    """양도소득세 조회."""
    if self._capital_gains is None:
        from .services.capital_gains import CapitalGainsService
        self._capital_gains = CapitalGainsService(self)
    return self._capital_gains
```

`__init__` 에서 `self._capital_gains: CapitalGainsService | None = None`
초기화. `TYPE_CHECKING` 블록에 forward import 추가.

## 6. 테스트 추가

`tests/fixtures/capital_gains_R01.json` 에 캡처된 응답을 저장(개인정보
마스킹 처리 후). `tests/test_capital_gains.py`:

```python
def test_parses_capital_gains_R01_response():
    raw = json.loads(FIXTURE.read_text())
    rows = raw.get("transactionList") or []
    parsed = [CapitalGainsTransaction.from_dict(r) for r in rows]
    assert all(t.raw for t in parsed)
    assert parsed[0].transaction_date is not None
```

회귀 안전망의 핵심. 홈택스가 새 분기에 응답을 바꾸면 새 fixture 추가 후
parser 보강.

## 7. `services/__init__.py` 와 `__init__.py` 노출

```python
# services/__init__.py
from .capital_gains import CapitalGainsService
__all__ = ["..., CapitalGainsService"]
```

dataclass 가 추가되었으면 `hometax_client/__init__.py` 에도 re-export.

## 8. 인증 등급 명시

서비스 클래스 docstring 에 등급 명시. 가능하면 사전 검사:

```python
def transaction_history(self, ...):
    # 등급 검사 (선택)
    if self._c.user_cl_cd == "02":  # ID/PW 등급
        raise AuthGradeInsufficientError(
            "양도소득세 조회는 카카오 이상 인증 등급이 필요합니다.",
        )
    ...
```

## 9. README / docs 업데이트

`README.md` 와 `docs/architecture.md` 의 예제/매트릭스에 새 서비스 한 줄
추가.

## 체크리스트

- [ ] 캡처 데이터 확보 (gitignore 위치)
- [ ] `docs/hometax-facts.md` §추가
- [ ] `facts/current.toml` 항목 추가
- [ ] `models.py` dataclass 추가 (필요 시)
- [ ] `services/<tax_area>.py` 작성
- [ ] `HometaxClient.<tax_area>` lazy property 추가
- [ ] `services/__init__.py` 노출
- [ ] fixture + 테스트 추가
- [ ] 인증 등급 docstring 명시
- [ ] PEP 8 lint 통과 (`pycodestyle --max-line-length=120`)
- [ ] 테스트 통과 (`pytest`)
- [ ] CHANGELOG / README 업데이트
