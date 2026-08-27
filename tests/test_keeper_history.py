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

from sync.keeper_history import build_original_draft_round_index


def test_original_draft_round_index_preserves_draft_cost_for_final_roster_players():
    draft = [
        {"player_key": "p.gibbs", "round": 1},
        {"player_key": "p.smith", "round": 6},
    ]
    final_rosters = [
        {"team_key": "team.6", "players": [{"player_key": "p.smith"}, {"player_key": "p.wilson"}]}
    ]

    index = build_original_draft_round_index(draft, final_rosters)

    assert index == {"p.smith": 6, "p.wilson": None}
