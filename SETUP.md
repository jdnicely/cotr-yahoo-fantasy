# COTR Yahoo Fantasy Sync — Setup

This guide intentionally separates **public source code** from **Yahoo credentials/private account data**.

## 1. Request Yahoo Fantasy Sports API access

Yahoo currently requires Fantasy Sports API applications to be submitted for review. Start at:

- Developer portal: https://sports.yahoo.com/developer/
- Access application: https://sports.yahoo.com/developer/access/

Describe this as a **personal/single-league, read-only fantasy-football integration** for the Yahoo league “Communication on the Rocks.” Request only the Fantasy Sports data needed for rosters, draft results, standings, transactions, matchups, league settings, and available players.

Do not assume a newly created OAuth app can call the Fantasy API until Yahoo has provisioned/approved Fantasy Sports access for that application.

## 2. Create/configure the Yahoo OAuth application

Create the Yahoo application associated with the approved Fantasy API access. For this command-line bootstrap flow:

- use OAuth 2.0 authorization-code flow
- use `oob` as the redirect URI/callback
- request Fantasy Sports **read** access (`fspt-r`)
- save the Client ID and Client Secret somewhere secure

Yahoo's OAuth documentation explicitly supports `oob` for applications that do not run a callback server.

## 3. Bootstrap the first Yahoo refresh token locally

From the repository directory:

```bash
python -m pip install -r requirements.txt
python -m sync.yahoo_auth bootstrap
```

The command will:

1. prompt for the Yahoo Client ID;
2. prompt for the Client Secret using a hidden terminal prompt;
3. print the Yahoo authorization URL;
4. ask you to paste the authorization code Yahoo displays;
5. exchange the code for OAuth tokens;
6. print **only the refresh token** you need to place in GitHub Actions secrets.

It does not write the Client Secret, access token, refresh token, or authorization code to a file.

## 4. Create the GitHub repository

Create a repository named:

`cotr-yahoo-fantasy`

The source-code repository may be public. Because Yahoo currently restricts storage/redistribution of API data, **leave Yahoo-derived data publication disabled by default**.

Push this repository's source files to that repository.

## 5. Add GitHub Actions secrets

In GitHub:

**Settings → Secrets and variables → Actions → Secrets → New repository secret**

Create these four repository secrets:

| Secret | Value |
| --- | --- |
| `YAHOO_CLIENT_ID` | Yahoo Client ID / Consumer Key |
| `YAHOO_CLIENT_SECRET` | Yahoo Client Secret / Consumer Secret |
| `YAHOO_REFRESH_TOKEN` | Refresh token from the bootstrap command |
| `GH_SECRET_TOKEN` | Fine-grained GitHub PAT described below |

Never put these values in `config.json`, `.env`, workflow YAML, issues, commits, screenshots, or chat messages.

## 6. Create the narrow GitHub token used only for Yahoo refresh-token rotation

Yahoo can return a replacement refresh token. The workflow must save the newest token before continuing, otherwise a later run may lose authorization.

Create a **fine-grained personal access token** in GitHub with:

- Repository access: **only `cotr-yahoo-fantasy`**
- Repository permission: **Secrets — Read and write**
- No broader repository/content permissions unless GitHub requires a baseline Metadata read permission automatically

Store that PAT as `GH_SECRET_TOKEN`.

The sync passes the new Yahoo refresh token to `gh secret set` over **stdin**. GitHub CLI encrypts the secret locally before sending it to GitHub; the plaintext token is not included in the command line.

## 7. Leave Yahoo data publication disabled initially

Do **not** create `ALLOW_YAHOO_DATA_COMMITS` yet.

With the variable absent, the workflow may fetch and normalize data transiently to validate the integration, but the final step deletes `data/` from the runner and does not commit it.

This is deliberate. Yahoo's current developer portal says applications must comply with its API Access and Use Agreement, including restrictions around separating/redistributing underlying API data. Confirm the terms attached to your approved Fantasy API access before enabling persistent/public Yahoo data.

If Yahoo explicitly permits the intended data storage/publication model for your approved app, create the repository variable:

**Settings → Secrets and variables → Actions → Variables**

Name:

`ALLOW_YAHOO_DATA_COMMITS`

Value:

`I_HAVE_CONFIRMED_YAHOO_TERMS`

Only then will the workflow commit generated `data/` JSON.

## 8. Run the workflow manually

Open:

**Actions → Sync Yahoo Fantasy → Run workflow**

A successful run should:

1. install dependencies;
2. run the unit test suite;
3. refresh Yahoo OAuth;
4. rotate `YAHOO_REFRESH_TOKEN` if Yahoo issues a new one;
5. discover COTR (`league_id=34393`, season `2026`);
6. fetch and normalize league data;
7. either delete transient data (default) or commit it if the explicit publication gate is enabled.

The workflow also runs automatically every six hours at minute 17.

## 9. What to verify after the first run

Check the Actions log and repository history. There should be no:

- Yahoo email address
- Yahoo GUID
- Client Secret
- OAuth access token
- OAuth refresh token
- authorization code
- GitHub PAT
- raw Yahoo XML response

The source tests include synthetic GUID/email values specifically to verify that manager/account metadata is not mapped into public team objects.

## 10. Local dry run

You can also run the sync locally after exporting credentials in your shell environment:

```bash
export YAHOO_CLIENT_ID='...'
export YAHOO_CLIENT_SECRET='...'
export YAHOO_REFRESH_TOKEN='...'
python -m sync.sync_yahoo
```

If Yahoo rotates the refresh token during a local run and `GH_SECRET_TOKEN` / `GITHUB_REPOSITORY` are not present, the program deliberately fails rather than silently lose the newest valid token.
