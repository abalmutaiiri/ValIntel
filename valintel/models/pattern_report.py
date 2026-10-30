"""Results and coverage from a historical opponent-pattern check."""
from __future__ import annotations
from dataclasses import dataclass, field
from .repeated_opponent import RepeatedOpponent
from ..config import MAX_MATCHES

@dataclass
class PatternReport:
    player_name: str
    player_puuid: str
    checked: int = 0
    requested: int = MAX_MATCHES
    findings: list[RepeatedOpponent] = field(default_factory=list)
    status: str = "unavailable"  # complete, partial, unavailable
    explanation: str = ""
