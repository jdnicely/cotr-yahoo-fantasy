from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import requests

from sync.normalize import (
    discover_leagues,
    normalize_draft,
    normalize_players,
    normalize_roster,
    normalize_scoreboard,
    normalize_settings,
    normalize_standings,
    normalize_teams,
    normalize_transactions,
    select_current_league,
    select_historical_league,
)
from sync.keeper_history import build_original_draft_round_index
from sync.sanitize import write_json
from sync.yahoo_auth import refresh_yahoo_token, update_github_actions_secret
from sync.yahoo_client import YahooFantasyClient

DISCOVERY_PATH = "users;use_login=1/games;game_codes=nfl/leagues"
PAGE_SIZE = 25


def _write(changed: list[Path], path: Path, value: object) -> None:
    if write_json(path, value):
        changed.append(path)


def _optional_xml(client: YahooFantasyClient, path: str):
    try:
        return client.get_xml(path)
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        if status in {400, 404}:
            return None
        raise


def _paginated(
    client: YahooFantasyClient,
    path_builder: Callable[[int, int], str],
    normalizer: Callable,
    limit: int | None = None,
) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while limit is None or len(rows) < limit:
        count = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(rows))
        if count <= 0:
            break
        root = client.get_xml(path_builder(start, count))
        batch = normalizer(root)
        if not batch:
            break
        for item in batch:
            if "source_rank" in item:
                item = dict(item)
                item["source_rank"] = start + int(item["source_rank"])
            rows.append(item)
            if limit is not None and len(rows) >= limit:
                break
        if len(batch) < count:
            break
        start += count
    return rows


def sync_current_season(
    client: YahooFantasyClient,
    config: dict,
    data_root: Path,
) -> list[Path]:
    changed: list[Path] = []
    season = int(config["season"])
    league_root = client.get_xml(DISCOVERY_PATH)
    leagues = discover_leagues(league_root)
    league = select_current_league(
        leagues,
        league_id=str(config["league_id"]),
        season=season,
        league_name=str(config["league_name"]),
    )
    league_key = league["league_key"]
    season_root = Path(data_root) / str(season)

    _write(changed, season_root / "league.json", league)

    settings = normalize_settings(client.get_xml(f"league/{league_key}/settings"))
    _write(changed, season_root / "settings.json", settings)

    teams = normalize_teams(client.get_xml(f"league/{league_key}/teams"))
    _write(changed, season_root / "teams.json", teams)

    rosters = [
        normalize_roster(client.get_xml(f"team/{team['team_key']}/roster"))
        for team in teams
    ]
    rosters = sorted(rosters, key=lambda roster: int(roster.get("team_id", 999)))
    _write(changed, season_root / "rosters.json", rosters)

    standings = normalize_standings(client.get_xml(f"league/{league_key}/standings"))
    _write(changed, season_root / "standings.json", standings)

    draft_root = _optional_xml(client, f"league/{league_key}/draftresults")
    draft = normalize_draft(draft_root) if draft_root is not None else []
    _write(changed, season_root / "draft.json", draft)

    transactions = _paginated(
        client,
        lambda start, count: f"league/{league_key}/transactions;start={start};count={count}",
        normalize_transactions,
    )
    _write(changed, season_root / "transactions" / "all.json", transactions)
    transaction_weeks: dict[int, list[dict]] = {}
    for transaction in transactions:
        week = transaction.get("week")
        if isinstance(week, int):
            transaction_weeks.setdefault(week, []).append(transaction)
    for week, rows in sorted(transaction_weeks.items()):
        _write(
            changed,
            season_root / "transactions" / "by_week" / f"week_{week:02d}.json",
            rows,
        )

    start_week = int(league.get("start_week", 1))
    current_week = int(league.get("current_week", start_week))
    for week in range(start_week, current_week + 1):
        scoreboard_root = _optional_xml(client, f"league/{league_key}/scoreboard;week={week}")
        if scoreboard_root is None:
            continue
        scoreboard = normalize_scoreboard(scoreboard_root)
        _write(
            changed,
            season_root / "matchups" / "by_week" / f"week_{week:02d}.json",
            scoreboard,
        )

    available_limit = int(config.get("available_player_limit", 300))
    available_players = _paginated(
        client,
        lambda start, count: (
            f"league/{league_key}/players;status=A;sort=AR;start={start};count={count}"
        ),
        normalize_players,
        limit=available_limit,
    )
    _write(changed, season_root / "available_players.json", available_players)

    return changed


def sync_history(client: YahooFantasyClient, config: dict, data_root: Path) -> list[str]:
    warnings: list[str] = []
    leagues = discover_leagues(client.get_xml(DISCOVERY_PATH))
    current_season = int(config["season"])
    start_season = int(config.get("historical_start_season", current_season - 1))
    history_root = Path(data_root) / "history"

    for season in range(start_season, current_season):
        league, warning = select_historical_league(
            leagues,
            season=season,
            league_name=str(config["league_name"]),
        )
        if warning:
            warnings.append(warning)
        if league is None:
            continue
        league_key = league["league_key"]
        target = history_root / str(season)
        write_json(target / "league.json", league)

        draft_root = _optional_xml(client, f"league/{league_key}/draftresults")
        draft = normalize_draft(draft_root) if draft_root is not None else []
        write_json(target / "draft.json", draft)

        teams = normalize_teams(client.get_xml(f"league/{league_key}/teams"))
        final_week = int(league.get("end_week", 17))
        final_rosters = [
            normalize_roster(
                client.get_xml(f"team/{team['team_key']}/roster;week={final_week}")
            )
            for team in teams
        ]
        draft_rounds = build_original_draft_round_index(draft, final_rosters)
        for roster in final_rosters:
            for player in roster.get("players", []):
                player["original_draft_round"] = draft_rounds.get(player.get("player_key"))
        write_json(target / "final_rosters.json", final_rosters)

    return warnings


def load_config(path: Path = Path("config.json")) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    config = load_config()
    client_id = os.environ["YAHOO_CLIENT_ID"]
    client_secret = os.environ["YAHOO_CLIENT_SECRET"]
    refresh_token = os.environ["YAHOO_REFRESH_TOKEN"]

    token = refresh_yahoo_token(client_id, client_secret, refresh_token)
    if token.rotated:
        github_token = os.environ.get("GH_SECRET_TOKEN")
        repository = os.environ.get("GITHUB_REPOSITORY")
        if not github_token or not repository:
            raise RuntimeError(
                "Yahoo rotated the refresh token but GH_SECRET_TOKEN/GITHUB_REPOSITORY is unavailable"
            )
        update_github_actions_secret(
            repository=repository,
            github_token=github_token,
            secret_name="YAHOO_REFRESH_TOKEN",
            secret_value=token.refresh_token,
        )

    client = YahooFantasyClient(token.access_token)
    data_root = Path("data")
    changed = sync_current_season(client, config, data_root)
    warnings = sync_history(client, config, data_root)
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(f"Yahoo sync complete; {len(changed)} current-season files changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
