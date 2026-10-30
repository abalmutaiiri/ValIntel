"""Representation of a single player shown in ValIntel."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Player:
    puuid: str
    team: str
    agent_id: str = ""
    agent: str = "Selecting…"
    icon: str = ""
    name: str = "Resolving…"
    kd: float | None = None
    winrate: float | None = None
    games: int = 0
    is_self: bool = False
