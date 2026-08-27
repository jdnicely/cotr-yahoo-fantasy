# COTR Yahoo Fantasy Sync

Automated Yahoo Fantasy Football data sync for **Communication on the Rocks (COTR)**.

This repo is designed to give COTR a clean, analysis-ready data layer similar to the Cloud Dynasty Sleeper workflow: Yahoo remains the source system, the sync normalizes only the football data we care about, and GitHub Actions keeps the dataset current without exposing Yahoo credentials.

> **League:** Communication on the Rocks  
> **Yahoo League ID:** `34393`  
> **Format:** 12-team H2H keeper league  
> **Keeper limit:** 2 players, different positions

---

## What this project does

The sync can retrieve and normalize:

- league identity and settings
- scoring and roster settings
- teams and team names
- current rosters
- standings
- draft results
- adds, drops, trades, and other transactions
- weekly matchups and scores
- up to 300 available / waiver players
- prior COTR seasons Yahoo exposes unambiguously
- historical draft round + final-roster information for keeper analysis

The goal is to make questions like these easy to answer from synchronized league state:

- Who are the best waiver targets available **in COTR**?
- Which managers are weak at RB/WR and might be trade partners?
- What changed in the league since the last sync?
- What did a player originally cost in the draft?
- What is a player's next keeper-round cost?
- Which keepers create the most surplus value?

---

## Security model

Yahoo private-league access requires OAuth. Credentials and tokens must **never** be committed to this repository.

### Stored only as GitHub Actions secrets

- `YAHOO_CLIENT_ID`
- `YAHOO_CLIENT_SECRET`
- `YAHOO_REFRESH_TOKEN`
- `GH_SECRET_TOKEN`

The refresh-token workflow supports Yahoo token rotation. If Yahoo returns a replacement refresh token, the workflow can update `YAHOO_REFRESH_TOKEN` in GitHub Secrets rather than writing the token anywhere in the repository.

Raw Yahoo API responses are **never saved to disk**. The intended flow is:

```text
Yahoo API
   ↓
normalize in memory
   ↓
exclude private account / manager fields
   ↓
validate output for sensitive keys
   ↓
write deterministic JSON
```

Manager email addresses, Yahoo GUIDs, authorization codes, access tokens, refresh tokens, and account identifiers are not part of the public data model.

---

## Important Yahoo API note

Yahoo's current Fantasy Sports developer program requires an application submission/review before Fantasy API access is provisioned. OAuth credentials alone do not guarantee access to Fantasy endpoints.

Yahoo's developer policies may also restrict storage or redistribution of Fantasy API data. Because of that, **Yahoo-derived league data is not committed by default**.

Data persistence is gated behind this GitHub repository variable:

```text
ALLOW_YAHOO_DATA_COMMITS=I_HAVE_CONFIRMED_YAHOO_TERMS
```

Do **not** set that variable until the terms applicable to your approved Yahoo application permit the intended persistence/publication model.

The repo code and COTR's manually supplied keeper configuration can remain public without enabling Yahoo-data commits.

---

## COTR keeper rules

The league-specific rules are stored in:

```text
config/keeper_rules.json
```

Current COTR rules encoded by the project:

1. Owners may keep up to **2 players**.
2. The two keepers must be **different positions**.
3. A first-time keeper costs the round in which the player was originally drafted the prior season.
4. Trading for a drafted player does **not** reset that original draft-round cost.
5. A drafted player later dropped and claimed from waivers retains the original draft-round cost.
6. An undrafted player costs the **final draft round (Round 14)**.
7. A repeat keeper's cost is reduced by half using COTR's convention: for example `6 → 3 → 1`.
8. Once a player has counted against a **1st-round pick**, that player cannot be kept the following season.

This logic is deliberately stored separately from Yahoo's generic keeper settings because COTR's keeper economics are league-specific.

---

## Repository layout

```text
cotr-yahoo-fantasy/
├── .github/
│   └── workflows/
│       └── yahoo-sync.yml       # Scheduled + manual synchronization
├── config/
│   └── keeper_rules.json        # COTR keeper rules
├── docs/
│   └── superpowers/
│       ├── plans/               # Implementation plan
│       └── specs/               # Architecture/design spec
├── sync/
│   ├── keeper_history.py        # Original-round / keeper-history helpers
│   ├── normalize.py             # Yahoo XML → public football model
│   ├── sanitize.py              # Sensitive-key validation
│   ├── sync_yahoo.py            # Sync orchestration
│   ├── yahoo_auth.py            # OAuth/bootstrap/token refresh
│   └── yahoo_client.py          # Yahoo API transport
├── tests/
│   ├── fixtures/                # Synthetic Yahoo-like XML fixtures
│   └── test_*.py                # Unit tests
├── config.json                  # League identity + sync limits
├── requirements.txt
├── SETUP.md                     # Detailed authorization/setup guide
└── README.md
```

When persistence is explicitly enabled, normalized outputs are written under `data/`.

---

## Expected data layout

A synchronized season is structured for direct analysis rather than as a raw Yahoo dump.

Example:

```text
data/
├── 2026/
│   ├── league.json
│   ├── settings.json
│   ├── teams.json
│   ├── rosters.json
│   ├── standings.json
│   ├── draft.json
│   ├── available_players.json
│   ├── transactions/
│   │   └── all.json
│   └── matchups/
│       └── by_week/
└── history/
    └── 2025/
        ├── league.json
        ├── draft.json
        └── final_rosters.json
```

Historical final-roster records can include each player's `original_draft_round`. An undrafted player is represented with a null original round so COTR's Round-14 rule can be applied explicitly.

---

## One-time setup

The detailed walkthrough is in **[SETUP.md](SETUP.md)**.

At a high level:

1. Apply for / obtain Yahoo Fantasy API access.
2. Configure a Yahoo OAuth application.
3. Create a GitHub repository named `cotr-yahoo-fantasy`.
4. Add the required GitHub Actions secrets.
5. Run the local Yahoo authorization bootstrap once.
6. Save the resulting refresh token as `YAHOO_REFRESH_TOKEN`.
7. Run the GitHub Action manually to validate the connection.
8. Leave Yahoo-data persistence disabled unless/until the applicable Yahoo terms permit it.

---

## Local installation

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Run the tests

```bash
python -m pytest -q
```

The test suite uses synthetic Yahoo-style XML fixtures. It does **not** require your Yahoo credentials.

Tests cover the core behaviors including:

- OAuth token parsing and refresh behavior
- refresh-token rotation handling
- COTR keeper-history calculations
- Yahoo response normalization
- exclusion of manager/account fields
- sensitive-key validation
- current-season and historical orchestration

---

## Yahoo authorization bootstrap

After creating the Yahoo application and installing dependencies, follow the commands in **SETUP.md** to run the one-time authorization flow.

The bootstrap uses Yahoo's authorization-code flow with `oob`, which is appropriate for a command-line setup where no callback web server is running.

Never paste Yahoo client secrets or refresh tokens into an issue, commit, README, or public chat transcript.

---

## GitHub Actions

The workflow is located at:

```text
.github/workflows/yahoo-sync.yml
```

It supports:

- scheduled synchronization every six hours
- manual `workflow_dispatch` runs
- OAuth refresh before API requests
- replacement of a rotated refresh-token secret
- deterministic JSON generation
- tests before publication
- commits only when persisted football data actually changes

The initial sync correctly detects newly created/untracked `data/` files, so the first successful persistence run is not skipped as a false no-op.

---

## GitHub secrets

Add these under:

**Repository → Settings → Secrets and variables → Actions → Secrets**

| Secret | Purpose |
|---|---|
| `YAHOO_CLIENT_ID` | Yahoo OAuth application client ID |
| `YAHOO_CLIENT_SECRET` | Yahoo OAuth application secret |
| `YAHOO_REFRESH_TOKEN` | Current Yahoo refresh token |
| `GH_SECRET_TOKEN` | Fine-grained GitHub token used only to rotate the Yahoo refresh-token secret |

`GH_SECRET_TOKEN` should be scoped as narrowly as possible to this repository and only the repository-secret permissions required by the workflow.

---

## GitHub variables

Optional repository variable:

| Variable | Value | Meaning |
|---|---|---|
| `ALLOW_YAHOO_DATA_COMMITS` | `I_HAVE_CONFIRMED_YAHOO_TERMS` | Explicitly allows the workflow to persist normalized Yahoo-derived data to git |

Absence of this variable is the safe/default state.

---

## Manual sync

Once credentials are configured, use:

**GitHub → Actions → Yahoo Fantasy Sync → Run workflow**

The workflow log should show the sync stages without printing OAuth secrets or refresh tokens.

---

## Troubleshooting

### Yahoo returns 401 or 403

Check:

- the Yahoo Fantasy API application has actually been approved
- the Client ID and Client Secret belong to the same application
- `YAHOO_REFRESH_TOKEN` came from the current application
- the authorization flow used the same configured redirect value expected by the token exchange

A valid OAuth token does not necessarily mean the Yahoo Fantasy endpoints have been enabled for the application.

### The workflow suddenly stops authenticating

Yahoo may rotate refresh tokens. Confirm that:

- `GH_SECRET_TOKEN` is valid
- it is scoped to this repository
- it can update Actions secrets
- the workflow successfully replaced `YAHOO_REFRESH_TOKEN` when Yahoo issued a new one

### The workflow runs but commits nothing

That may be correct.

The workflow does not persist Yahoo-derived data unless:

```text
ALLOW_YAHOO_DATA_COMMITS=I_HAVE_CONFIRMED_YAHOO_TERMS
```

is explicitly configured.

Even with persistence enabled, no commit is created when normalized football data has not changed.

### A prior COTR season is missing

Historical discovery intentionally avoids guessing. If Yahoo returns multiple ambiguous leagues for the same season/name, the sync skips that history rather than associating the wrong league with COTR.

---

## Design principle

This project is intentionally **not** a complete Yahoo API mirror.

It is a compact football-analysis layer for COTR:

```text
Yahoo = source of truth
COTR rules = explicit local configuration
Normalized JSON = analysis interface
GitHub Actions = synchronization engine
Git history = change/audit trail when persistence is allowed
```

That keeps the repository understandable, testable, and useful for keeper, waiver, draft, matchup, and trade analysis without retaining unnecessary Yahoo account data.
