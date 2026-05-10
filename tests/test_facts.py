"""facts 카탈로그 로딩과 lookup 테스트."""

from __future__ import annotations

import pytest

from hometax_client import facts


def test_default_catalog_loads() -> None:
    catalog = facts.catalog()
    assert isinstance(catalog, dict)
    assert "meta" in catalog
    assert catalog["meta"].get("catalog_version")


def test_lookup_returns_inquiries_action_id() -> None:
    action_id = facts.lookup(
        "services", "inquiries", "income_statements", "action_id",
    )
    assert action_id == "ATXPPBAA001R16"


def test_lookup_raises_keyerror_on_missing_path() -> None:
    with pytest.raises(KeyError):
        facts.lookup("services", "nonexistent", "key")


def test_material_kinds_present() -> None:
    rows = facts.lookup("services", "income_tax", "material_kinds")
    codes = {row["code"] for row in rows}
    # 캡처에서 확인된 5개 자료구분
    assert {"F0025", "A0162", "A0165", "A0161", "F0026"} <= codes
