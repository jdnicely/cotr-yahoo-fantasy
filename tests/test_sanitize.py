import json

import pytest

from sync.sanitize import SensitiveDataError, assert_public_data, write_json


def test_rejects_sensitive_keys_recursively():
    with pytest.raises(SensitiveDataError):
        assert_public_data({"team": {"owner_guid": "private"}})


def test_rejects_oauth_fields_recursively():
    with pytest.raises(SensitiveDataError):
        assert_public_data({"meta": {"refresh_token": "private"}})


def test_allows_public_fantasy_fields():
    assert_public_data(
        {
            "league_id": "34393",
            "team": {
                "team_id": "6",
                "name": "oddly satisfying",
                "players": [{"player_key": "500.p.1", "player_id": "1"}],
            },
        }
    )


def test_write_json_is_deterministic_and_noop_when_content_is_same(tmp_path):
    path = tmp_path / "data.json"
    first = {"z": 1, "a": {"y": 2, "x": 3}}
    second = {"a": {"x": 3, "y": 2}, "z": 1}

    assert write_json(path, first) is True
    original = path.read_bytes()
    assert write_json(path, second) is False
    assert path.read_bytes() == original
    assert json.loads(path.read_text()) == second
    assert path.read_text().endswith("\n")
