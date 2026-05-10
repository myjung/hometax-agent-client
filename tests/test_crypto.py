"""nts_encrypt / nts_report_signature / NTS_KEYS source 회귀 테스트.

캡처에서 관찰된 실제 입력/출력으로 알고리즘 호환성을 고정. **키 source 변경**
(JS 구조 / cache resolution) 도 fixture 기반으로 검증한다. 라이브 drift 검사
(라이브 JS 가져와 active 키와 비교) 는 ``tests/test_keys_live.py`` 에서 별도로
``HOMETAX_LIVE=1`` 게이트로 관리.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from hometax_client.crypto import (
    ENV_KEYS_FILE,
    NTS_KEYS,
    NTS_KEYS_BASELINE,
    NTS_MARKER,
    active_keys,
    extract_keys_from_js,
    nts_digest,
    nts_encrypt,
    nts_report_signature,
    save_keys,
)

FIXTURES = Path(__file__).parent / "fixtures" / "2026-05-10"


def test_nts_keys_count_is_seven() -> None:
    assert len(NTS_KEYS) == 7
    assert all(isinstance(key, str) and key for key in NTS_KEYS)


def test_nts_digest_is_alnum_only() -> None:
    digest = nts_digest("hello", sec=15, user_id="user")
    assert digest
    assert re.fullmatch(r"[0-9a-zA-Z]+", digest)


def test_nts_digest_is_deterministic_for_fixed_sec() -> None:
    digest1 = nts_digest("payload", sec=42, user_id="rey")
    digest2 = nts_digest("payload", sec=42, user_id="rey")
    assert digest1 == digest2


def test_nts_digest_changes_with_user_id() -> None:
    digest_a = nts_digest("payload", sec=42, user_id="alice")
    digest_b = nts_digest("payload", sec=42, user_id="bob")
    assert digest_a != digest_b


def test_nts_digest_rejects_out_of_range_sec() -> None:
    import pytest

    with pytest.raises(ValueError):
        nts_digest("hello", sec=60, user_id="")
    with pytest.raises(ValueError):
        nts_digest("hello", sec=-1, user_id="")


def test_nts_encrypt_format() -> None:
    """전체 페이로드 형식: <nts<nts>nts>{sec+11}{digest}{sec:02}."""
    signed = nts_encrypt("hi", sec=30, user_id="rey")
    assert signed.startswith(NTS_MARKER)
    suffix = signed[len(NTS_MARKER):]
    # sec=30 → prefix "41" (30+11), trailing "30".
    assert suffix.startswith("41")
    assert suffix.endswith("30")


def test_nts_report_signature_pair_shape() -> None:
    b, bb = nts_report_signature("ATXPPABA001R07", sec=11)
    # bb 는 alnum-only digest, b 는 (sec+15) + alnum + (sec:02).
    assert re.fullmatch(r"[0-9a-zA-Z]+", bb)
    assert b.startswith("26")  # 11 + 15
    assert b.endswith("11")


# ----------------------------------------------------------------- #
# Key source: extract / cache / resolution                          #
# ----------------------------------------------------------------- #


def test_extract_keys_from_js_with_real_excerpt() -> None:
    """라이브 JS excerpt (2026-05-10) 에서 7개 키를 정확히 추출."""
    js_text = (FIXTURES / "common_te-min_excerpt.js").read_text(
        encoding="utf-8",
    )
    keys = extract_keys_from_js(js_text)
    assert keys == NTS_KEYS_BASELINE


def test_extract_keys_from_js_rejects_wrong_count() -> None:
    """testVal 의 키 개수가 7이 아니면 ValueError."""
    bad_js = 'var testVal=["a","b","c","d","e","f"];'  # 6개
    with pytest.raises(ValueError, match="7이 아님|7"):
        extract_keys_from_js(bad_js)


def test_extract_keys_from_js_rejects_missing_array() -> None:
    """testVal 자체가 없으면 ValueError."""
    with pytest.raises(ValueError, match="testVal"):
        extract_keys_from_js("// no testVal here")


def test_active_keys_default_to_baseline(monkeypatch, tmp_path) -> None:
    """env / cache 모두 없으면 baseline 그대로."""
    monkeypatch.delenv(ENV_KEYS_FILE, raising=False)
    # 기본 cache 경로를 비어있는 임시 경로로 가린다.
    monkeypatch.setattr(
        "hometax_client.crypto._default_cache_path",
        lambda: tmp_path / "nonexistent.json",
    )
    assert active_keys() == NTS_KEYS_BASELINE


def test_active_keys_uses_env_override(monkeypatch, tmp_path) -> None:
    """``HOMETAX_NTS_KEYS_FILE`` 가 가리키는 파일이 baseline 보다 우선."""
    fake_keys = tuple(f"FAKE{i}KEY{i}xxxxxxxxxxxxxxxxxxxx" for i in range(7))
    cache = tmp_path / "fake_keys.json"
    cache.write_text(json.dumps({"keys": list(fake_keys)}), encoding="utf-8")
    monkeypatch.setenv(ENV_KEYS_FILE, str(cache))
    assert active_keys() == fake_keys


def test_active_keys_falls_back_when_cache_invalid(
    monkeypatch, tmp_path,
) -> None:
    """깨진 cache (키 6개) 는 무시하고 baseline 으로 fallback."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"keys": ["a", "b", "c", "d", "e", "f"]}))
    monkeypatch.setenv(ENV_KEYS_FILE, str(bad))
    monkeypatch.setattr(
        "hometax_client.crypto._default_cache_path",
        lambda: tmp_path / "no.json",
    )
    assert active_keys() == NTS_KEYS_BASELINE


def test_save_keys_round_trip(monkeypatch, tmp_path) -> None:
    """save_keys 로 저장한 cache 를 active_keys 가 그대로 사용."""
    new_keys = tuple(f"ROT{i}KEY{i}yyyyyyyyyyyyyyyyyyyy" for i in range(7))
    target = tmp_path / "rotated.json"
    saved = save_keys(new_keys, path=target)
    assert saved == target
    monkeypatch.setenv(ENV_KEYS_FILE, str(target))
    assert active_keys() == new_keys


def test_save_keys_rejects_invalid_input(tmp_path) -> None:
    """7 != 길이거나 non-alnum 이면 ValueError."""
    with pytest.raises(ValueError):
        save_keys(("only", "two"), path=tmp_path / "x.json")
    with pytest.raises(ValueError):
        save_keys(
            tuple(["valid"] * 6 + ["has space"]),
            path=tmp_path / "x.json",
        )


def test_nts_digest_uses_active_keys(monkeypatch, tmp_path) -> None:
    """active_keys 가 override 되면 nts_digest 결과도 달라진다."""
    digest_baseline = nts_digest("hello", sec=14, user_id="rey")
    fake_keys = tuple(f"FAKE{i}xxxxxxxxxxxxxxxxxxxxxxxxxxxx" for i in range(7))
    cache = tmp_path / "fake.json"
    cache.write_text(json.dumps({"keys": list(fake_keys)}))
    monkeypatch.setenv(ENV_KEYS_FILE, str(cache))
    digest_override = nts_digest("hello", sec=14, user_id="rey")
    assert digest_baseline != digest_override
