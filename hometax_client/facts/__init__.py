"""HomeTax fact catalog loader.

식별자/액션 ID 같이 홈택스가 바꿀 수 있는 값들을 ``current.toml`` 에 모아두고
모듈 import 시 한 번 로드한다. 호출자가 다른 catalog 로 override 하고 싶을
때 ``load(path)`` 로 교체할 수 있다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - fallback for older Pythons
    import tomli as tomllib  # type: ignore[no-redef]

_DEFAULT_CATALOG = Path(__file__).resolve().parent / "current.toml"

_catalog: dict[str, Any] | None = None


def load(path: str | Path | None = None) -> dict[str, Any]:
    """Load (or reload) the fact catalog from ``path``.

    호출 후 ``catalog()`` 가 새 값을 반환한다. ``path`` 가 ``None`` 이면 패키지
    내장 ``current.toml`` 을 사용한다.
    """
    global _catalog
    target = Path(path) if path else _DEFAULT_CATALOG
    with target.open("rb") as fh:
        _catalog = tomllib.load(fh)
    return _catalog


def catalog() -> dict[str, Any]:
    """Return the current fact catalog, lazy-loading the default if needed."""
    if _catalog is None:
        return load()
    return _catalog


def lookup(*keys: str) -> Any:
    """Dotted-path lookup helper.

    Example::

        lookup("services", "inquiries", "income_statements", "action_id")
    """
    node: Any = catalog()
    for key in keys:
        if not isinstance(node, dict):
            raise KeyError(f"facts lookup hit non-dict at {key!r}")
        if key not in node:
            raise KeyError(f"facts lookup missing key {key!r}")
        node = node[key]
    return node
