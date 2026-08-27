from pathlib import Path

from sync.yahoo_client import YahooFantasyClient, first_text, local_name


FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_yahoo_client_parses_xml_and_sends_bearer_header():
    xml = (FIXTURES / "leagues.xml").read_text()
    session = FakeSession(FakeResponse(xml))
    client = YahooFantasyClient("ACCESS_TOKEN", session=session)

    root = client.get_xml("users;use_login=1/games;game_codes=nfl/leagues")

    assert local_name(root.tag) == "fantasy_content"
    assert first_text(root, "league_id") == "34393"
    url, kwargs = session.calls[0]
    assert url == "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_codes=nfl/leagues"
    assert kwargs["headers"]["Authorization"] == "Bearer ACCESS_TOKEN"
    assert kwargs["headers"]["Accept"] == "application/xml"

from xml.etree import ElementTree as ET

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


def fixture_root(name):
    return ET.fromstring((FIXTURES / name).read_text())


def test_discovers_and_selects_current_cotr_league():
    leagues = discover_leagues(fixture_root("leagues.xml"))
    selected = select_current_league(leagues, league_id="34393", season=2026, league_name="Communication on the Rocks")
    assert selected["league_key"] == "500.l.34393"
    assert selected["season"] == 2026


def test_historical_ambiguity_is_reported_instead_of_guessed():
    leagues = [
        {"league_key": "1.l.1", "league_id": "1", "name": "Communication on the Rocks", "season": 2024},
        {"league_key": "1.l.2", "league_id": "2", "name": "Communication on the Rocks", "season": 2024},
    ]
    selected, warning = select_historical_league(leagues, season=2024, league_name="Communication on the Rocks")
    assert selected is None
    assert "2024" in warning
    assert "2" in warning


def test_normalize_teams_excludes_private_manager_metadata_and_sorts_by_team_id():
    teams = normalize_teams(fixture_root("teams.xml"))
    assert [team["team_id"] for team in teams] == ["2", "6"]
    assert teams[1] == {"team_key": "500.l.34393.t.6", "team_id": "6", "name": "oddly satisfying"}
    assert "guid" not in str(teams).lower()
    assert "email" not in str(teams).lower()


def test_normalize_draft_sorts_by_pick():
    draft = normalize_draft(fixture_root("draft.xml"))
    assert [row["pick"] for row in draft] == [1, 2]
    assert draft[0]["player_key"] == "500.p.1001"


def test_normalize_settings_maps_roster_and_scoring_values():
    settings = normalize_settings(fixture_root("league_settings.xml"))
    assert settings["draft_type"] == "live_standard"
    assert settings["roster_positions"][0] == {"position": "QB", "count": 1}
    assert {"stat_id": "10", "value": 0.25} in settings["stat_modifiers"]


def test_normalize_roster_maps_public_player_fields():
    roster = normalize_roster(fixture_root("roster.xml"))
    assert roster["team_key"] == "500.l.34393.t.6"
    assert roster["players"][0]["name"] == "Jahmyr Gibbs"
    assert roster["players"][0]["selected_position"] == "RB"


def test_normalize_standings_maps_record_and_points():
    standings = normalize_standings(fixture_root("standings.xml"))
    assert standings[0]["rank"] == 1
    assert standings[0]["wins"] == 10
    assert standings[0]["points_for"] == 1550.5


def test_normalize_transactions_maps_player_moves():
    txs = normalize_transactions(fixture_root("transactions.xml"))
    assert txs[0]["transaction_id"] == "1"
    assert txs[0]["players"][0]["move_type"] == "add"
    assert txs[0]["players"][0]["destination_team_key"] == "500.l.34393.t.6"


def test_normalize_scoreboard_maps_matchup_teams_and_scores():
    scoreboard = normalize_scoreboard(fixture_root("scoreboard.xml"))
    assert scoreboard["week"] == 1
    assert scoreboard["matchups"][0]["teams"][0]["points"] == 101.25


def test_normalize_available_players_preserves_api_order_with_source_rank():
    players = normalize_players(fixture_root("players.xml"))
    assert players[0]["source_rank"] == 1
    assert players[0]["name"] == "Michael Wilson"
    assert players[1]["source_rank"] == 2

from sync.sync_yahoo import sync_current_season


class FakeYahooClient:
    def __init__(self):
        self.calls = []

    def get_xml(self, path, params=None):
        self.calls.append(path)
        if path == "users;use_login=1/games;game_codes=nfl/leagues":
            return fixture_root("leagues.xml")
        if path.endswith("/settings"):
            return fixture_root("league_settings.xml")
        if path.endswith("/teams"):
            return fixture_root("teams.xml")
        if path.endswith("/standings"):
            return fixture_root("standings.xml")
        if path.endswith("/draftresults"):
            return fixture_root("draft.xml")
        if "/roster" in path:
            return fixture_root("roster.xml")
        if "/transactions" in path:
            return fixture_root("transactions.xml")
        if "/scoreboard;week=" in path:
            return fixture_root("scoreboard.xml")
        if "/players;status=A" in path:
            return fixture_root("players.xml")
        raise AssertionError(f"unexpected path {path}")


def test_current_sync_writes_analysis_ready_public_files(tmp_path):
    client = FakeYahooClient()
    config = {
        "league_id": "34393",
        "league_name": "Communication on the Rocks",
        "season": 2026,
        "available_player_limit": 300,
        "historical_start_season": 2024,
    }

    changed = sync_current_season(client, config, tmp_path)

    expected = {
        tmp_path / "2026/league.json",
        tmp_path / "2026/settings.json",
        tmp_path / "2026/teams.json",
        tmp_path / "2026/rosters.json",
        tmp_path / "2026/standings.json",
        tmp_path / "2026/draft.json",
        tmp_path / "2026/transactions/all.json",
        tmp_path / "2026/matchups/by_week/week_01.json",
        tmp_path / "2026/available_players.json",
    }
    assert expected.issubset(set(changed))
    assert all(path.exists() for path in expected)
    assert not list(tmp_path.rglob("*.xml"))
    public_text = "\n".join(path.read_text() for path in expected)
    assert "PRIVATE-GUID" not in public_text
    assert "private@example.invalid" not in public_text

from sync.sync_yahoo import sync_history


def test_history_sync_writes_unambiguous_season_and_warns_on_missing_season(tmp_path):
    client = FakeYahooClient()
    config = {
        "league_id": "34393",
        "league_name": "Communication on the Rocks",
        "season": 2026,
        "available_player_limit": 300,
        "historical_start_season": 2024,
    }

    warnings = sync_history(client, config, tmp_path)

    assert any("2024" in warning for warning in warnings)
    history = tmp_path / "history/2025"
    assert (history / "league.json").exists()
    assert (history / "draft.json").exists()
    assert (history / "final_rosters.json").exists()
    final_rosters = __import__("json").loads((history / "final_rosters.json").read_text())
    assert "original_draft_round" in final_rosters[0]["players"][0]
