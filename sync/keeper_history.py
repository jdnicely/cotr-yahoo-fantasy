from __future__ import annotations


def first_year_keeper_round(original_round: int | None, final_round: int) -> int:
    """Return the first-year keeper price for a player."""
    if final_round < 1:
        raise ValueError("final_round must be positive")
    if original_round is None:
        return final_round
    if not 1 <= original_round <= final_round:
        raise ValueError("original_round must be within the draft")
    return original_round


def next_keeper_round(prior_round: int, final_round: int) -> int:
    """Advance a repeat keeper using COTR's floor-half convention."""
    if not 1 <= prior_round <= final_round:
        raise ValueError("prior_round must be within the draft")
    if prior_round == 1:
        raise ValueError("a first-round keeper cannot be kept again")
    return max(1, prior_round // 2)


def keeper_eligible(prior_keeper_round: int | None) -> bool:
    """A player becomes ineligible after counting against round one."""
    return prior_keeper_round != 1


def build_original_draft_round_index(
    draft_rows: list[dict], final_rosters: list[dict]
) -> dict[str, int | None]:
    drafted = {
        row["player_key"]: int(row["round"])
        for row in draft_rows
        if row.get("player_key") and row.get("round") is not None
    }
    result: dict[str, int | None] = {}
    for roster in final_rosters:
        for player in roster.get("players", []):
            player_key = player.get("player_key")
            if player_key:
                result[player_key] = drafted.get(player_key)
    return dict(sorted(result.items()))
