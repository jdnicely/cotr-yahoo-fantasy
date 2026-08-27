# COTR Yahoo Fantasy Sync — Design

Date: 2026-08-27
Status: Approved design draft

## Goal

Create a separate public GitHub repository for the Communication on the Rocks (COTR) Yahoo Fantasy Football league that exposes sanitized, analysis-ready fantasy data while keeping all Yahoo and GitHub authentication material private in repository secrets.

The repository should become the durable read layer for COTR analysis, similar in spirit to the existing Sleeper sync used for Cloud Dynasty.

## Security Boundary

### Public repository contents

The public repository may contain only sanitized fantasy-football data and code/configuration needed to reproduce the sync. Public data may include:

- League name and league identifier
- League scoring and roster settings
- Team names
- Player names, player IDs, positions, and NFL teams
- Rosters
- Draft results
- Keeper selections/cost metadata that is safe to publish
- Standings
- Matchups and scores
- Transactions, trades, adds, and drops
- Available/waiver player pool
- COTR keeper rules stored as league configuration

### Private repository secrets

The following must never be committed:

- Yahoo client secret
- Yahoo OAuth access token
- Yahoo OAuth refresh token
- Yahoo authorization codes
- Yahoo account email or account GUID
- Raw API payloads containing private owner/account metadata
- GitHub token used to update repository secrets

The Yahoo client ID may also be stored as a secret for simplicity, even if not inherently sensitive.

## Repository Layout

```text
cotr-yahoo-fantasy/
├── .github/
│   └── workflows/
│       └── yahoo-sync.yml
├── config/
│   └── keeper_rules.json
├── data/
│   ├── 2026/
│   │   ├── league.json
│   │   ├── settings.json
│   │   ├── teams.json
│   │   ├── rosters.json
│   │   ├── standings.json
│   │   ├── draft.json
│   │   ├── transactions/
│   │   │   ├── all.json
│   │   │   └── by_week/
│   │   ├── matchups/
│   │   │   └── by_week/
│   │   └── available_players.json
│   └── history/
│       └── <season>/
│           ├── league.json
│           ├── draft.json
│           └── final_rosters.json
├── sync/
│   ├── yahoo_auth.py
│   ├── yahoo_client.py
│   ├── normalize.py
│   ├── sanitize.py
│   ├── keeper_history.py
│   └── sync_yahoo.py
├── tests/
│   ├── test_auth.py
│   ├── test_normalize.py
│   ├── test_sanitize.py
│   └── test_keeper_history.py
├── config.json
├── README.md
├── SETUP.md
└── requirements.txt
```

## v1 Data Scope

### Current season

The 2026 sync should collect and normalize:

1. League identity and settings
2. Scoring and roster settings
3. All teams
4. All current rosters
5. Standings
6. Draft results after the draft occurs
7. All league transactions
8. Weekly matchups and scores
9. Approximately the top 300 available or waiver-eligible players, plus metadata for all rostered players
10. Keeper rules defined in repository configuration

### Historical seasons

The sync should attempt to discover previous COTR seasons accessible under the authorized Yahoo account.

For each season:

- If exactly one unambiguous matching COTR league is found, normalize its draft results and final rosters into `data/history/<season>/`.
- If the match is ambiguous, skip that season and report the ambiguity rather than guessing.
- Historical data is intended to support keeper-cost reconstruction and multi-year keeper eligibility analysis.

## Keeper Rules

The repository must encode COTR-specific keeper logic rather than relying on Yahoo keeper flags alone.

Current COTR rules:

1. Up to two keepers per owner.
2. The two keepers must be different positions.
3. First-year keeper cost equals the player's prior-year original draft round, regardless of later trade or waiver acquisition.
4. Undrafted players cost the final draft round.
5. A repeated keeper's cost increases by half each year, following league convention.
6. Once a keeper counts against a first-round pick, that player cannot be kept the following year.

The sync should preserve raw draft-round history needed to calculate keeper costs, but keeper recommendations remain an analysis-layer concern rather than a workflow side effect.

## OAuth and Token Rotation

Yahoo OAuth is required for private fantasy league data.

The workflow should:

1. Read `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, and `YAHOO_REFRESH_TOKEN` from GitHub Actions secrets.
2. Exchange the refresh token for a short-lived access token.
3. Detect whether Yahoo returned a replacement refresh token.
4. If the refresh token changed, update the `YAHOO_REFRESH_TOKEN` GitHub Actions secret before continuing.
5. Use the access token only in memory.
6. Never print tokens to logs.

To permit secret rotation, the repository should use a fine-grained GitHub token restricted to the single COTR repository with only the repository-secret permission required for the update operation.

## Sync Schedule

GitHub Actions should support:

- Manual `workflow_dispatch`
- Scheduled sync every six hours

The job should only commit when normalized public data changes.

## Normalization and Sanitization

Raw Yahoo responses should not be persisted.

The pipeline should transform data in memory:

Yahoo API response → normalize → sanitize → deterministic JSON → disk

Sanitization must remove or reject:

- Yahoo account GUIDs
- Owner email/account identifiers
- OAuth fields
- Unknown fields that match sensitive-key patterns

The sanitizer should use an allowlist for public output objects where practical rather than relying solely on a denylist.

## Deterministic Output

To avoid noisy commits:

- JSON keys should be sorted.
- Lists should use stable ordering where order is not semantically meaningful.
- Timestamps should only be included when they reflect source data or are operationally useful.
- A sync run with no fantasy-data changes should produce no git diff.

## Error Handling

The workflow should fail clearly when:

- OAuth refresh fails
- Yahoo API access is unauthorized
- League discovery fails for the current season
- A sanitizer detects unexpected private fields
- Required normalized output cannot be produced

Historical ambiguity should not fail the current-season sync; it should be reported as a warning.

If refresh-token rotation succeeds with Yahoo but secret replacement fails, the workflow should fail immediately rather than risk losing the newest valid refresh token.

## Testing

Tests should cover at minimum:

- OAuth response parsing without logging secrets
- Refresh-token rotation detection
- Sanitizer removal/rejection of private Yahoo fields
- Stable deterministic JSON normalization
- Current-season league selection
- Historical league ambiguity behavior
- Keeper round-history transformation

Network calls should be mocked in unit tests.

## Initial Bootstrap

The first authorization is a one-time local/bootstrap process:

1. Create the Yahoo developer application.
2. Obtain Yahoo client credentials.
3. Complete interactive OAuth authorization for the Yahoo account that belongs to COTR.
4. Capture the initial refresh token locally.
5. Add secrets to the COTR GitHub repository.
6. Add the restricted GitHub token used only for refresh-token secret rotation.
7. Run the workflow manually.
8. Verify that only sanitized fantasy data is committed.

No bootstrap token material should be written to tracked files.

## Success Criteria

The project is successful when:

- A public `cotr-yahoo-fantasy` repository can be read without Yahoo credentials.
- The repository contains enough current data to support roster, draft, waiver, trade, standings, and matchup analysis.
- Historical draft/final-roster data supports keeper-cost reconstruction when Yahoo exposes the prior seasons unambiguously.
- Scheduled syncs run every six hours.
- No auth or account-private data appears in git history or workflow logs.
- Yahoo refresh-token rotation is handled without manual intervention.
- No-op syncs produce no commits.


## Implementation Note — Yahoo 2026 Access/Policy Change

During implementation on 2026-08-27, current Yahoo developer documentation was re-verified. Yahoo now requires Fantasy Sports API application review/provisioning, provides read access by default, and publishes policy language restricting separation/redistribution of API data. The implementation therefore keeps the source repository public-capable but disables Yahoo-derived data commits by default. Persistence/publication requires the explicit repository variable `ALLOW_YAHOO_DATA_COMMITS=I_HAVE_CONFIRMED_YAHOO_TERMS` after the approved application's terms have been confirmed. Refresh-token secret rotation was also simplified to use `gh secret set` over stdin rather than a PyNaCl dependency.
