# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`hometax-agent-client` is an **HTTP-only capture-and-replay client** for HomeTax (`hometax.go.kr`). The library wraps `wqAction.do` (HomeTax's main RPC: JSON body + HMAC suffix produced by `nts_encrypt`) so AI agents and scripts can call HomeTax services without driving a browser. Python 3.12+, packaged with `hatchling`, managed with `uv`.

Status is alpha — public API is stabilizing, breaking changes possible until 0.2.

## Commands

```bash
# install dev environment (creates .venv via uv)
uv sync --all-extras

# run tests
.venv/bin/pytest
.venv/bin/pytest tests/test_crypto.py::test_specific  # single test

# lint (PR gate)
.venv/bin/pycodestyle --max-line-length=120 hometax_client/

# run an example end-to-end (requires .env populated, see .env.example)
.venv/bin/python examples/basic_inquiry.py
.venv/bin/python examples/auth_kakao.py
```

The `[bootstrap]` extra (`uv sync --extra bootstrap`) pulls in Playwright; only used to seed cookies once when the 2026-05 `pubcLogin` protection script blocks direct ID/PW POST. The library core never imports Playwright.

## Architecture

Read [`docs/architecture.md`](docs/architecture.md), [`docs/conventions.md`](docs/conventions.md), [`docs/extending.md`](docs/extending.md), and [`docs/compatibility.md`](docs/compatibility.md) before non-trivial changes — they encode the design contract.

### Two-layer API (do not collapse)

```
client.<service>.<method>(...)   typed convenience  → dataclasses with `raw`
client.wq_action(action_id=..., screen_id=..., host=..., body=...)   raw escape hatch
```

Both layers are public. The raw `wq_action()` exists so callers can route around HomeTax response drift without waiting on a release. Do not delete it, do not make it private.

### Where things live

- `hometax_client/client.py` — `HometaxClient`. Owns `wq_action` (signing, JSON parse, block/error classification), `refresh_session` (`/token.do`), `activate_subsystem_session` (`/permission.do`), `session_info` (auto-fills `tin`), and lazy `inquiries` / `income_tax` service properties. Constructors: `from_cookies(...)` (Playwright json or `save_session` cache, both auto-detected) and `login(auth=..., cache_path=...)` (cache-first then OACX).
- `hometax_client/crypto.py` — `nts_encrypt`, `nts_report_signature`, plus the NTS_KEYS source layer. `active_keys()` resolves keys in order: `HOMETAX_NTS_KEYS_FILE` env > default user cache (`~/.cache/hometax-agent-client/nts_keys.json`) > `NTS_KEYS_BASELINE` (hardcoded 2026-04 snapshot, extracted from `common_te-min.js` `testVal` array — public client-side mixing constants, not a server secret). Rotation does **not** break `tests/test_crypto.py` (algorithm-only); the live drift canary is `tests/test_keys_live.py` (gated by `HOMETAX_LIVE=1`) and the manual CLI is `python -m hometax_client.health [--refresh]`.
- `hometax_client/auth/` — `OACXAuth` base, `KakaoAuth` / `NaverAuth` thin overrides, `IdPwAuth`. Each `auth.authenticate()` then `auth.to_client()` produces a `HometaxClient`.
- `hometax_client/services/` — `InquiryService` (지급명세서/세금신고), `IncomeTaxService` (종합소득세 신고도움). All inherit `ServiceBase` (provides `_ensure_tin()` and `_cookie_value()` via `self._c`).
- `hometax_client/sessions.py` — `SessionStore` for multi-client session management (`docs/sessions.md`). Directory of `<client_id>.json` files; primitives: `list / get / open / save / touch / remove / health / find_by_tin / find_by_user_id`. Atomic writes (tempfile + os.replace). No locking — caller's job. `HometaxClient.save_session` shares the same write path via `_session_payload`.
- `hometax_client/health.py` — `python -m hometax_client.health [--refresh]` CLI for NTS_KEYS drift detection. Compares live `common_te-min.js` to `active_keys()` (env file > user cache > baseline). `tests/test_keys_live.py` (gated by `HOMETAX_LIVE=1`) is the automatic canary.
- `hometax_client/bootstrap/` — **optional** Playwright recon (only loaded when `[bootstrap]` extra is installed). `CaptureSession` / `capture_login` save `cookies.json` (drop-in for `from_cookies`), HAR (req/resp bodies, for protection-script analysis), and `storage_state.json`. Core never imports this. CLI: `examples/recon_login.py`. Docs: `docs/recon.md`.
- `hometax_client/facts/current.toml` — action IDs, screen IDs, hosts, referers, response-list keys. Loaded once via `facts.lookup("services", ...)`. Patch-release HomeTax identifier changes by editing this file alone — **do not hard-code IDs in service modules**.
- `hometax_client/models.py` — frozen dataclasses; every one keeps `raw: dict` so unknown fields survive.
- `hometax_client/exceptions.py` — full hierarchy under `HometaxError`. `classify_failure()` maps wire `resultMsg` to the right subclass. Callers branch on type, never on Korean message strings.
- `docs/hometax-facts.md` — single source of truth for HomeTax behavior verified by capture (subdomains, host pools, cookie shape, action IDs, etc.). When you add a new service, append a §section here with verification date and capture path.

### What this library deliberately does NOT do

Per `docs/architecture.md` §"라이브러리 vs 워크플로 경계":

- No file IO except library self-state: single session cache (`save_session` / `from_cookies`), multi-session store (`SessionStore`), NTS_KEYS cache (`save_keys`), and bootstrap recon artifacts (`bootstrap.CaptureSession`). User outputs (PDF/Excel/CSV) are caller's responsibility.
- No PDF/Excel/CSV rendering, no filename generation, no Korean stemming.
- No batch progress, no session locking (single or multi), no UI.
- No automatic session refresh / re-auth on expiry — `SessionStore.health()` reports the state, branching is the caller's job.
- No error messages that force callers to string-match Korean text — branch by exception type.

These belong in a downstream workflow package, not here.

## Conventions worth knowing before editing

- **Wire field names are preserved unmodified** in returned `dict`s and in `dataclass.raw` (`attrYr`, `txprDscmNo`, `mateKndCd`, `agitxRtnInqrDVOList`, …). Only the typed extracted fields use English snake_case (`attr_year`, `material_kind_name`, `payer_tin`). This is an intentional capture-replay contract.
- **User-facing argument names are normal**: `user_id`, `password`, `rrn`, `attr_year` — translate to wire names internally.
- **HomeTax-internal prefixes (e.g. `agitx`) never leak into module names.** Translate semantically: `agitx` → `income_tax`. Wire keys keep the prefix.
- **Naming**: `*Client` / `*Service` / `*Auth` / `*Result` / `*Error`. No `*Help` / `*Util` / `*Manager`. Getters are noun-form and side-effect-light; mutators are verb-form. Raw passthrough is always `wq_action`.
- **Type hints required on all public methods.** Use `from __future__ import annotations`. `Any` only for external wire responses.
- **Docstrings on public methods (Korean primary, English secondary).** Include the wire `action_id` / `screen_id` so capture traceability is preserved.
- **Stability contract** is in `docs/compatibility.md` — don't change `wq_action` signature, `HometaxError` hierarchy, or existing dataclass fields without a major-version bump. New fields can be added in minor releases (callers tolerate them via `raw`).

## Adding a new tax service (high-level)

Follow [`docs/extending.md`](docs/extending.md) — full checklist there. The pattern: capture → `docs/hometax-facts.md` §section → `facts/current.toml` entry → dataclass in `models.py` (with `raw`) → `services/<area>.py` (typed method + `raw_*` escape hatch, both calling `activate_subsystem_session` then `wq_action`) → lazy property on `HometaxClient` → fixture-based parser test.

## Response drift handling

When HomeTax returns a shape the library wasn't expecting:

- **New field** → silently surfaces via `dataclass.raw`. No code change needed.
- **Missing core field** → `ResponseSchemaDriftError(action_id, missing, raw)`. Callers can read `exc.raw` to keep working.
- **Action ID changed** → edit `facts/current.toml`, ship a patch release. Service code stays untouched.
- **NTS_KEYS rotated** → `tests/test_keys_live.py` (HOMETAX_LIVE=1) or `python -m hometax_client.health` reports drift. `python -m hometax_client.health --refresh` writes new keys to user cache → `active_keys()` immediately picks them up. Optional follow-up: bump `NTS_KEYS_BASELINE` + fixture in a patch release for new installs / offline use.
- **Algorithm itself changed (HMAC scheme)** → `tests/test_crypto.py` fails; reverse-engineer new algorithm in `crypto.py`.

## Security

`captures/`, `out/`, `*.session.json`, `.env` are in `.gitignore` — never commit captured cookies, RRNs, or credentials. `save_session` writes the cache with `0o600`. The library is intended for the holder's own data only.
