# COTR Yahoo Fantasy Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public, analysis-ready Yahoo Fantasy Football sync for Communication on the Rocks that updates every six hours while keeping Yahoo/GitHub credentials private and preserving keeper-history inputs.

**Architecture:** A Python sync process authenticates to Yahoo with a refresh token, discovers the current COTR league from the authorized account, fetches Yahoo Fantasy resources in memory, normalizes and sanitizes them into deterministic JSON, and writes only public football data. GitHub Actions runs the sync every six hours, rotates a changed Yahoo refresh token into the repository secret before continuing, runs tests, and commits only when `data/` changes.

**Tech Stack:** Python 3.12, `requests`, `PyNaCl`, `pytest`, standard-library `xml.etree.ElementTree`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-cotr-yahoo-fantasy-design.md`

## Global Constraints

- Public repository contains sanitized fantasy-football data only.
- Never persist raw Yahoo API payloads.
- Never print OAuth tokens, Yahoo account GUIDs/emails, authorization codes, or the GitHub secret-management token.
- Current league is Communication on the Rocks, Yahoo league ID `34393`, season `2026`.
- Historical league matching must skip and warn on ambiguity rather than guess.
- Sync schedule is manual plus every six hours.
- A no-op sync must produce no git diff.
- If Yahoo rotates the refresh token and GitHub secret replacement fails, fail immediately.
- JSON output must be deterministic: sorted keys, stable ordering, terminal newline.
- Network calls must be mocked in unit tests.

---

## File Structure

- `.github/workflows/yahoo-sync.yml` — scheduled/manual CI sync, test, and commit workflow.
- `config/keeper_rules.json` — COTR keeper policy in machine-readable form.
- `config.json` — league identity, season, available-player limit, sync behavior.
- `sync/yahoo_auth.py` — OAuth refresh parsing, refresh-token rotation, GitHub secret update, bootstrap CLI helpers.
- `sync/yahoo_client.py` — authenticated Yahoo Fantasy HTTP client and XML parsing helpers.
- `sync/normalize.py` — Yahoo XML resource normalizers into public domain dictionaries/lists.
- `sync/sanitize.py` — public-field validation, sensitive-key rejection, deterministic JSON writer.
- `sync/keeper_history.py` — keeper-cost history calculations and original-draft-round transformations.
- `sync/sync_yahoo.py` — orchestration for current season and historical season sync.
- `tests/fixtures/*.xml` — synthetic Yahoo-like XML only; no real account data.
- `tests/test_auth.py` — token parsing/rotation and secret-update unit tests.
- `tests/test_normalize.py` — XML normalization, current league selection, deterministic sort tests.
- `tests/test_sanitize.py` — sensitive-field detection and deterministic writer tests.
- `tests/test_keeper_history.py` — keeper round progression and undrafted handling tests.
- `README.md` — public repo purpose/data contract.
- `SETUP.md` — Yahoo developer app, OAuth bootstrap, GitHub secrets, first-run instructions.
- `requirements.txt` — pinned minimum runtime/test dependencies.
- `.gitignore` — excludes local secrets, auth scratch files, caches, virtualenvs.

---

### Task 1: Repository Configuration and Keeper Rules

**Files:**
- Create: `config.json`
- Create: `config/keeper_rules.json`
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `sync/__init__.py`
- Create: `tests/test_keeper_history.py`
- Create: `sync/keeper_history.py`

**Interfaces:**
- Consumes: COTR rules from approved spec.
- Produces: `next_keeper_round(prior_round: int, final_round: int) -> int`; `first_year_keeper_round(original_round: int | None, final_round: int) -> int`; `keeper_eligible(prior_keeper_round: int | None) -> bool`.

- [ ] **Step 1: Write failing keeper-rule tests**

```python
from sync.keeper_history import first_year_keeper_round, keeper_eligible, next_keeper_round


def test_undrafted_player_costs_final_round():
    assert first_year_keeper_round(None, final_round=14) == 14


def test_first_year_keeper_uses_original_round():
    assert first_year_keeper_round(10, final_round=14) == 10


def test_repeat_keeper_cost_halves_toward_front():
    assert next_keeper_round(6, final_round=14) == 3
    assert next_keeper_round(3, final_round=14) == 1


def test_first_round_keeper_is_not_eligible_next_year():
    assert keeper_eligible(1) is False
    assert keeper_eligible(3) is True
```

- [ ] **Step 2: Run the keeper tests and verify failure**

Run: `pytest tests/test_keeper_history.py -v`
Expected: FAIL because `sync.keeper_history` does not exist.

- [ ] **Step 3: Implement minimal keeper helpers and configuration files**

```python
# sync/keeper_history.py
from __future__ import annotations


def first_year_keeper_round(original_round: int | None, final_round: int) -> int:
    return final_round if original_round is None else original_round


def next_keeper_round(prior_round: int, final_round: int) -> int:
    if prior_round <= 1:
        raise ValueError("a first-round keeper cannot be kept again")
    return max(1, prior_round // 2)


def keeper_eligible(prior_keeper_round: int | None) -> bool:
    return prior_keeper_round != 1
```

`config.json` must contain `league_name`, `league_id`, `season`, `available_player_limit`, and `historical_start_season`. `config/keeper_rules.json` must encode max keepers `2`, distinct positions `true`, undrafted cost `14`, and repeat cost method `floor_half`.

- [ ] **Step 4: Run keeper tests**

Run: `pytest tests/test_keeper_history.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.json config/keeper_rules.json .gitignore requirements.txt sync/__init__.py sync/keeper_history.py tests/test_keeper_history.py
git commit -m "feat: add COTR keeper configuration"
```

---

### Task 2: OAuth Refresh and Safe Token Rotation

**Files:**
- Create: `tests/test_auth.py`
- Create: `sync/yahoo_auth.py`

**Interfaces:**
- Consumes: `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REFRESH_TOKEN`; optionally `GH_SECRET_TOKEN`, `GITHUB_REPOSITORY`.
- Produces: `TokenResult(access_token: str, refresh_token: str, rotated: bool, expires_in: int)`; `refresh_yahoo_token(...) -> TokenResult`; `update_github_actions_secret(...) -> None`.

- [ ] **Step 1: Write failing OAuth parsing and rotation tests**

```python
from sync.yahoo_auth import parse_token_response


def test_parse_token_response_keeps_old_refresh_token_when_absent():
    result = parse_token_response(
        {"access_token": "ACCESS", "expires_in": 3600},
        current_refresh_token="OLD_REFRESH",
    )
    assert result.access_token == "ACCESS"
    assert result.refresh_token == "OLD_REFRESH"
    assert result.rotated is False


def test_parse_token_response_detects_rotated_refresh_token():
    result = parse_token_response(
        {"access_token": "ACCESS", "refresh_token": "NEW_REFRESH", "expires_in": 3600},
        current_refresh_token="OLD_REFRESH",
    )
    assert result.refresh_token == "NEW_REFRESH"
    assert result.rotated is True
```

- [ ] **Step 2: Run auth tests and verify failure**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL because `sync.yahoo_auth` does not exist.

- [ ] **Step 3: Implement token parsing and HTTP refresh**

Use `POST https://api.login.yahoo.com/oauth2/get_token` with HTTP Basic auth `(client_id, client_secret)` and form fields `grant_type=refresh_token`, `refresh_token=<value>`. Call `raise_for_status()`. Never log request/response bodies.

- [ ] **Step 4: Add mocked refresh HTTP test**

Mock `requests.Session.post`, assert the token endpoint, Basic auth, and form data are correct, and assert no token strings are emitted to captured stdout/stderr.

- [ ] **Step 5: Implement GitHub repository-secret update**

Fetch `GET /repos/{owner}/{repo}/actions/secrets/public-key`, encrypt the newest refresh token with `nacl.public.SealedBox`, then `PUT /repos/{owner}/{repo}/actions/secrets/YAHOO_REFRESH_TOKEN` with `encrypted_value` and `key_id`. Require HTTP 201 or 204.

- [ ] **Step 6: Add mocked GitHub secret-update test**

Assert the public-key GET occurs before PUT and that the plaintext refresh token is absent from the PUT JSON and captured logs.

- [ ] **Step 7: Run auth tests**

Run: `pytest tests/test_auth.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add sync/yahoo_auth.py tests/test_auth.py
git commit -m "feat: add Yahoo OAuth refresh rotation"
```

---

### Task 3: Yahoo Fantasy HTTP Client and XML Helpers

**Files:**
- Create: `sync/yahoo_client.py`
- Create: `tests/fixtures/leagues.xml`
- Modify: `tests/test_normalize.py`

**Interfaces:**
- Consumes: Yahoo OAuth access token.
- Produces: `YahooFantasyClient.get_xml(path: str, params: dict[str, str] | None = None) -> Element`; helpers `local_name(tag: str) -> str`, `children_named(node, name)`, `first_text(node, name)`.

- [ ] **Step 1: Write failing client tests**

Create a synthetic XML fixture with `fantasy_content`, `users`, `games`, and two `league` nodes. Test namespace-agnostic tag lookup and mocked authenticated GET behavior.

- [ ] **Step 2: Run targeted test**

Run: `pytest tests/test_normalize.py -k yahoo_client -v`
Expected: FAIL because client/helpers do not exist.

- [ ] **Step 3: Implement minimal Yahoo client**

Base URL: `https://fantasysports.yahooapis.com/fantasy/v2`. Send `Authorization: Bearer <access token>` and `Accept: application/xml`. Parse with `ElementTree.fromstring` in memory and return the root; do not write raw XML.

- [ ] **Step 4: Run targeted test**

Run: `pytest tests/test_normalize.py -k yahoo_client -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sync/yahoo_client.py tests/test_normalize.py tests/fixtures/leagues.xml
git commit -m "feat: add Yahoo fantasy API client"
```

---

### Task 4: League Discovery and Public Normalizers

**Files:**
- Create: `sync/normalize.py`
- Modify: `tests/test_normalize.py`
- Create: `tests/fixtures/league_settings.xml`
- Create: `tests/fixtures/teams.xml`
- Create: `tests/fixtures/draft.xml`

**Interfaces:**
- Consumes: XML roots returned by `YahooFantasyClient`.
- Produces: `discover_leagues(root) -> list[dict]`; `select_current_league(leagues, league_id, season, league_name) -> dict`; `select_historical_league(...) -> tuple[dict | None, str | None]`; `normalize_settings`, `normalize_teams`, `normalize_draft`, `normalize_roster`, `normalize_standings`, `normalize_transactions`, `normalize_scoreboard`, `normalize_players`.

- [ ] **Step 1: Write failing discovery tests**

Test exact current-season selection by league ID + season and historical behavior where two same-name leagues in one season returns `(None, warning)` rather than selecting either.

- [ ] **Step 2: Run discovery tests**

Run: `pytest tests/test_normalize.py -k league -v`
Expected: FAIL.

- [ ] **Step 3: Implement league discovery and selection**

Extract only public fields: `league_key`, `league_id`, `name`, `season`, `url`, `num_teams`, `draft_status`, `current_week`, `start_week`, `end_week` when present. Historical selection must return a warning string containing the season and candidate count on ambiguity.

- [ ] **Step 4: Write failing resource-normalization tests**

Use synthetic fixtures to assert team objects contain only `team_key`, `team_id`, `name`; draft rows contain `pick`, `round`, `team_key`, `player_key`; settings/scoring output preserves roster/scoring values without owner metadata.

- [ ] **Step 5: Implement resource normalizers**

Use namespace-agnostic XML traversal. Unknown source tags are ignored unless explicitly mapped. Stable-sort teams by numeric `team_id`, draft by numeric `pick`, players by rank then name, transactions by timestamp/id, standings by rank/team ID.

- [ ] **Step 6: Run normalizer tests**

Run: `pytest tests/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sync/normalize.py tests/test_normalize.py tests/fixtures
git commit -m "feat: normalize Yahoo fantasy resources"
```

---

### Task 5: Sanitizer and Deterministic JSON Writer

**Files:**
- Create: `sync/sanitize.py`
- Create: `tests/test_sanitize.py`

**Interfaces:**
- Consumes: normalized Python dictionaries/lists.
- Produces: `assert_public_data(value: object) -> None`; `write_json(path: Path, value: object) -> bool` returning whether file contents changed.

- [ ] **Step 1: Write failing sanitizer tests**

```python
import pytest
from sync.sanitize import SensitiveDataError, assert_public_data


def test_rejects_sensitive_keys_recursively():
    with pytest.raises(SensitiveDataError):
        assert_public_data({"team": {"owner_guid": "private"}})


def test_allows_public_fantasy_fields():
    assert_public_data({"team_id": "6", "name": "oddly satisfying", "players": [{"player_key": "x"}]})
```

- [ ] **Step 2: Run sanitizer tests and verify failure**

Run: `pytest tests/test_sanitize.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement sensitive-key matching and deterministic writer**

Reject keys matching case-insensitive fragments: `guid`, `email`, `oauth`, `access_token`, `refresh_token`, `authorization`, `client_secret`, `client_id`, `github_token`, `gh_secret_token`. `write_json` validates first, serializes with `indent=2`, `sort_keys=True`, `ensure_ascii=False`, and a final newline; it only replaces the file when bytes differ.

- [ ] **Step 4: Add deterministic/no-op write tests**

Write the same object with different dictionary insertion order twice and assert the second call returns `False` and file bytes are identical.

- [ ] **Step 5: Run sanitizer tests**

Run: `pytest tests/test_sanitize.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sync/sanitize.py tests/test_sanitize.py
git commit -m "feat: enforce public deterministic data"
```

---

### Task 6: Current-Season and History Sync Orchestrator

**Files:**
- Create: `sync/sync_yahoo.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_keeper_history.py`

**Interfaces:**
- Consumes: `YahooFantasyClient`, normalizers, config JSON, sanitizer writer.
- Produces: CLI `python -m sync.sync_yahoo`; functions `sync_current_season(client, config, data_root) -> list[Path]`, `sync_history(client, config, data_root) -> list[str]`.

- [ ] **Step 1: Write failing orchestration test with fake client**

Provide a fake client that returns fixture XML per requested path. Assert expected paths are written under `data/2026/` and no raw-response file is created.

- [ ] **Step 2: Run orchestration test and verify failure**

Run: `pytest tests/test_normalize.py -k orchestrator -v`
Expected: FAIL.

- [ ] **Step 3: Implement current-season orchestration**

Sequence: discover authorized NFL leagues → select `league_id=34393`, `season=2026` → fetch settings, teams, standings, draft results (tolerate not-yet-drafted 404/empty), each team roster, transactions, weeks `1..current_week`, and available players in 25-player pages until limit `300` or exhaustion → normalize → sanitize/write.

- [ ] **Step 4: Implement history orchestration**

Group discovered leagues by season from `historical_start_season` through `season - 1`; unambiguous name/ID lineage match writes `league.json`, `draft.json`, and final roster snapshot; ambiguity appends warning and writes nothing for that season.

- [ ] **Step 5: Add keeper-history source transformation test**

Given a draft list and final roster list, build an index keyed by `player_key` containing `original_draft_round` or `null` for undrafted players. Assert traded/dropped status does not alter original draft round.

- [ ] **Step 6: Run full unit suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sync/sync_yahoo.py sync/keeper_history.py tests
git commit -m "feat: sync COTR current and historical data"
```

---

### Task 7: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/yahoo-sync.yml`

**Interfaces:**
- Consumes repository secrets: `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REFRESH_TOKEN`, `GH_SECRET_TOKEN`; GitHub context `github.repository`.
- Produces: six-hour/manual data refresh commits.

- [ ] **Step 1: Create workflow with constrained permissions**

Workflow triggers:

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "17 */6 * * *"
```

Set `permissions: contents: write`. Use Python 3.12, install `requirements.txt`, run `pytest -q`, then `python -m sync.sync_yahoo`. Pass secrets only as environment variables to the sync step.

- [ ] **Step 2: Add no-op commit guard**

Use `git diff --quiet -- data/` to skip commit when unchanged; otherwise configure a bot identity, `git add data/`, commit `chore: sync Yahoo fantasy data`, and push.

- [ ] **Step 3: Validate workflow syntax locally**

Parse YAML with Python/PyYAML if installed; otherwise use Ruby's built-in YAML parser. Assert triggers and expected secret names are present by text inspection.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/yahoo-sync.yml
git commit -m "ci: schedule Yahoo fantasy sync"
```

---

### Task 8: Bootstrap CLI and Documentation

**Files:**
- Modify: `sync/yahoo_auth.py`
- Create: `README.md`
- Create: `SETUP.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: local Yahoo client ID/secret and user-entered authorization code only during bootstrap.
- Produces: authorization URL and token JSON printed only to the interactive terminal with explicit warning; no tracked token file.

- [ ] **Step 1: Add bootstrap URL/token helper tests**

Assert authorization URL includes Yahoo OAuth request endpoint, client ID, redirect URI `oob`, response type `code`, and language `en-us`; mock the code exchange and verify endpoint/form fields.

- [ ] **Step 2: Implement `python -m sync.yahoo_auth bootstrap`**

Print the authorization URL, prompt for the returned code, exchange it for tokens, and display only the initial refresh token with an explicit instruction to place it directly into GitHub Secrets and clear terminal history if desired. Do not write credentials to disk.

- [ ] **Step 3: Write README data contract**

Document repository purpose, public-data boundary, folder structure, six-hour schedule, and example analysis questions supported by the data.

- [ ] **Step 4: Write exact SETUP steps**

Include Yahoo developer app creation, callback/OOB configuration supported by the app, local bootstrap command, GitHub repo creation, exact secret names, fine-grained GitHub PAT restricted to this repository with repository `Secrets: write`, first manual workflow run, and post-run secret/git-history checks.

- [ ] **Step 5: Run full tests**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Run static secret scan**

Run:

```bash
grep -RniE '(refresh_token|access_token|client_secret|authorization: bearer|yahoo.*@)' . \
  --exclude-dir=.git --exclude='*.md' --exclude='test_*.py'
```

Expected: only variable/key names in source/workflow; no credential-looking literal values.

- [ ] **Step 7: Commit**

```bash
git add sync/yahoo_auth.py README.md SETUP.md .gitignore tests
git commit -m "docs: add Yahoo OAuth bootstrap guide"
```

---

### Task 9: Verification and Release Package

**Files:**
- Review all repository files.
- Create no additional tracked runtime artifacts.

**Interfaces:**
- Consumes: completed repository.
- Produces: verified repository bundle ready to push to a public GitHub repository.

- [ ] **Step 1: Run all tests from a clean environment**

Run: `python -m pip install -r requirements.txt && pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Compile Python source**

Run: `python -m compileall -q sync tests`
Expected: exit code 0.

- [ ] **Step 3: Inspect git status and history**

Run: `git status --short && git log --oneline --decorate -10`
Expected: clean working tree with feature commits present.

- [ ] **Step 4: Verify no private data is tracked**

Run `git grep` for sensitive key patterns and inspect every hit; only code/docs/test placeholders are acceptable. Run `git ls-files` and confirm no `.env`, token, credential, raw XML, or local auth file is tracked.

- [ ] **Step 5: Package repository**

Create `/mnt/data/cotr-yahoo-fantasy.zip` excluding `.git`, `__pycache__`, `.pytest_cache`, and virtual environments.

- [ ] **Step 6: Report exact remaining user-side actions**

The only manual actions should be: create the public GitHub repo, create Yahoo developer app, complete one-time Yahoo OAuth authorization, add four GitHub secrets, upload/push the verified repository, and manually run the workflow once.


## Implementation Note — Yahoo 2026 Access/Policy Change

During implementation on 2026-08-27, current Yahoo developer documentation was re-verified. Yahoo now requires Fantasy Sports API application review/provisioning, provides read access by default, and publishes policy language restricting separation/redistribution of API data. The implementation therefore keeps the source repository public-capable but disables Yahoo-derived data commits by default. Persistence/publication requires the explicit repository variable `ALLOW_YAHOO_DATA_COMMITS=I_HAVE_CONFIRMED_YAHOO_TERMS` after the approved application's terms have been confirmed. Refresh-token secret rotation was also simplified to use `gh secret set` over stdin rather than a PyNaCl dependency.
