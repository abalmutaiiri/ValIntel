"""A repeated opponent encounter in authorized match history."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RepeatedOpponent:
    # Deliberately omit opponent Riot IDs from UI; an integer label is enough
    # to distinguish repeat patterns inside an analyzed history.
    label: str
    encounters: int
    match_ids: tuple[str, ...]
    player_wins: int
    player_losses: int
