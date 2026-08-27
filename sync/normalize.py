from __future__ import annotations

from xml.etree import ElementTree as ET

from sync.yahoo_client import children_named, descendants_named, first_text


def _direct_text(node: ET.Element, name: str, default: str | None = None) -> str | None:
    matches = children_named(node, name)
    if not matches or matches[0].text is None:
        return default
    value = matches[0].text.strip()
    return value if value else default


def _int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    return int(value)


def _float(value: str | None, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    return float(value)


def _compact(mapping: dict) -> dict:
    return {key: value for key, value in mapping.items() if value is not None}


def discover_leagues(root: ET.Element) -> list[dict]:
    leagues: list[dict] = []
    for node in descendants_named(root, "league"):
        league_key = _direct_text(node, "league_key")
        league_id = _direct_text(node, "league_id")
        name = _direct_text(node, "name")
        season = _int(_direct_text(node, "season"))
        if not league_key or not league_id or not name or season is None:
            continue
        leagues.append(
            _compact(
                {
                    "league_key": league_key,
                    "league_id": league_id,
                    "name": name,
                    "season": season,
                    "url": _direct_text(node, "url"),
                    "num_teams": _int(_direct_text(node, "num_teams")),
                    "draft_status": _direct_text(node, "draft_status"),
                    "current_week": _int(_direct_text(node, "current_week")),
                    "start_week": _int(_direct_text(node, "start_week")),
                    "end_week": _int(_direct_text(node, "end_week")),
                }
            )
        )
    return sorted(leagues, key=lambda league: (league["season"], league["league_key"]))


def select_current_league(
    leagues: list[dict],
    league_id: str,
    season: int,
    league_name: str,
) -> dict:
    exact = [
        league
        for league in leagues
        if str(league.get("league_id")) == str(league_id)
        and int(league.get("season", -1)) == int(season)
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"multiple Yahoo leagues matched league ID {league_id} for {season}")

    fallback = [
        league
        for league in leagues
        if league.get("name") == league_name and int(league.get("season", -1)) == int(season)
    ]
    if len(fallback) == 1:
        return fallback[0]
    raise ValueError(
        f"could not uniquely identify {league_name!r} for {season}; "
        f"ID matches={len(exact)}, name matches={len(fallback)}"
    )


def select_historical_league(
    leagues: list[dict],
    season: int,
    league_name: str,
) -> tuple[dict | None, str | None]:
    candidates = [
        league
        for league in leagues
        if league.get("name") == league_name and int(league.get("season", -1)) == int(season)
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) == 0:
        return None, f"No {league_name} league found for {season}."
    return None, f"Ambiguous {league_name} history for {season}: {len(candidates)} matching leagues."


def normalize_teams(root: ET.Element) -> list[dict]:
    teams: list[dict] = []
    for node in descendants_named(root, "team"):
        team_key = _direct_text(node, "team_key")
        team_id = _direct_text(node, "team_id")
        name = _direct_text(node, "name")
        if not team_key or not team_id or not name:
            continue
        teams.append({"team_key": team_key, "team_id": team_id, "name": name})
    return sorted(teams, key=lambda team: int(team["team_id"]))


def normalize_draft(root: ET.Element) -> list[dict]:
    rows: list[dict] = []
    for node in descendants_named(root, "draft_result"):
        pick = _int(_direct_text(node, "pick"))
        round_number = _int(_direct_text(node, "round"))
        team_key = _direct_text(node, "team_key")
        player_key = _direct_text(node, "player_key")
        if None in (pick, round_number) or not team_key or not player_key:
            continue
        rows.append(
            {
                "pick": pick,
                "round": round_number,
                "team_key": team_key,
                "player_key": player_key,
            }
        )
    return sorted(rows, key=lambda row: row["pick"])


def normalize_settings(root: ET.Element) -> dict:
    settings_nodes = descendants_named(root, "settings")
    if not settings_nodes:
        raise ValueError("Yahoo settings response did not include settings")
    settings = settings_nodes[0]
    roster_positions = []
    for node in descendants_named(settings, "roster_position"):
        position = _direct_text(node, "position")
        count = _int(_direct_text(node, "count"))
        if position and count is not None:
            roster_positions.append({"position": position, "count": count})

    modifiers = []
    modifier_parents = descendants_named(settings, "stat_modifiers")
    if modifier_parents:
        for node in descendants_named(modifier_parents[0], "stat"):
            stat_id = _direct_text(node, "stat_id")
            value = _float(_direct_text(node, "value"))
            if stat_id and value is not None:
                modifiers.append({"stat_id": stat_id, "value": value})

    return _compact(
        {
            "draft_type": _direct_text(settings, "draft_type"),
            "scoring_type": _direct_text(settings, "scoring_type"),
            "num_playoff_teams": _int(_direct_text(settings, "num_playoff_teams")),
            "roster_positions": roster_positions,
            "stat_modifiers": modifiers,
        }
    )


def _normalize_player(node: ET.Element, source_rank: int | None = None) -> dict:
    player = _compact(
        {
            "player_key": _direct_text(node, "player_key"),
            "player_id": _direct_text(node, "player_id"),
            "name": first_text(node, "full"),
            "position": _direct_text(node, "display_position"),
            "nfl_team": _direct_text(node, "editorial_team_abbr"),
            "status": _direct_text(node, "status"),
            "selected_position": first_text(
                descendants_named(node, "selected_position")[0], "position"
            )
            if descendants_named(node, "selected_position")
            else None,
            "source_rank": source_rank,
        }
    )
    return player


def normalize_roster(root: ET.Element) -> dict:
    team_nodes = descendants_named(root, "team")
    if not team_nodes:
        raise ValueError("Yahoo roster response did not include a team")
    team = team_nodes[0]
    players = [_normalize_player(node) for node in descendants_named(team, "player")]
    players = [player for player in players if player.get("player_key")]
    return _compact(
        {
            "team_key": _direct_text(team, "team_key"),
            "team_id": _direct_text(team, "team_id"),
            "name": _direct_text(team, "name"),
            "players": players,
        }
    )


def normalize_standings(root: ET.Element) -> list[dict]:
    rows: list[dict] = []
    for team in descendants_named(root, "team"):
        standings_nodes = descendants_named(team, "team_standings")
        if not standings_nodes:
            continue
        standings = standings_nodes[0]
        rows.append(
            _compact(
                {
                    "team_key": _direct_text(team, "team_key"),
                    "team_id": _direct_text(team, "team_id"),
                    "name": _direct_text(team, "name"),
                    "rank": _int(_direct_text(standings, "rank")),
                    "wins": _int(first_text(standings, "wins")),
                    "losses": _int(first_text(standings, "losses")),
                    "ties": _int(first_text(standings, "ties")),
                    "percentage": _float(first_text(standings, "percentage")),
                    "points_for": _float(_direct_text(standings, "points_for")),
                    "points_against": _float(_direct_text(standings, "points_against")),
                }
            )
        )
    return sorted(rows, key=lambda row: (row.get("rank", 999), int(row.get("team_id", 999))))


def normalize_transactions(root: ET.Element) -> list[dict]:
    rows: list[dict] = []
    for tx in descendants_named(root, "transaction"):
        transaction_key = _direct_text(tx, "transaction_key")
        transaction_id = _direct_text(tx, "transaction_id")
        if not transaction_key and not transaction_id:
            continue
        players = []
        for player_node in descendants_named(tx, "player"):
            data_nodes = descendants_named(player_node, "transaction_data")
            data = data_nodes[0] if data_nodes else None
            players.append(
                _compact(
                    {
                        "player_key": _direct_text(player_node, "player_key"),
                        "name": first_text(player_node, "full"),
                        "move_type": _direct_text(data, "type") if data is not None else None,
                        "source_team_key": _direct_text(data, "source_team_key") if data is not None else None,
                        "destination_team_key": _direct_text(data, "destination_team_key") if data is not None else None,
                    }
                )
            )
        rows.append(
            _compact(
                {
                    "transaction_key": transaction_key,
                    "transaction_id": transaction_id,
                    "type": _direct_text(tx, "type"),
                    "status": _direct_text(tx, "status"),
                    "timestamp": _int(_direct_text(tx, "timestamp")),
                    "players": players,
                }
            )
        )
    return sorted(rows, key=lambda row: (row.get("timestamp", 0), row.get("transaction_id", "")))


def normalize_scoreboard(root: ET.Element) -> dict:
    scoreboard_nodes = descendants_named(root, "scoreboard")
    if not scoreboard_nodes:
        raise ValueError("Yahoo scoreboard response did not include a scoreboard")
    scoreboard = scoreboard_nodes[0]
    week = _int(_direct_text(scoreboard, "week"))
    matchups = []
    for matchup in descendants_named(scoreboard, "matchup"):
        teams = []
        for team in descendants_named(matchup, "team"):
            points_nodes = descendants_named(team, "team_points")
            teams.append(
                _compact(
                    {
                        "team_key": _direct_text(team, "team_key"),
                        "name": _direct_text(team, "name"),
                        "points": _float(first_text(points_nodes[0], "total")) if points_nodes else None,
                    }
                )
            )
        matchups.append(
            _compact(
                {
                    "week": _int(_direct_text(matchup, "week"), week),
                    "status": _direct_text(matchup, "status"),
                    "teams": teams,
                }
            )
        )
    return {"week": week, "matchups": matchups}


def normalize_players(root: ET.Element) -> list[dict]:
    players = []
    for rank, node in enumerate(descendants_named(root, "player"), start=1):
        player = _normalize_player(node, source_rank=rank)
        if player.get("player_key"):
            players.append(player)
    return players
