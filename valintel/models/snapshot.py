"""Snapshot of an agent-select lobby or active match."""
from __future__ import annotations
from dataclasses import dataclass, field
from .player import Player

@dataclass
class Snapshot:
    mode: str = "MENUS"
    match_id: str = ""
    map_name: str = "Unknown map"
    allies: list[Player] = field(default_factory=list)
    enemies: list[Player] = field(default_factory=list)
    status: str = "Waiting for VALORANT…"
    error: str = ""
    stats_note: str = ""
