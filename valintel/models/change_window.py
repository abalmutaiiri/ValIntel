"""Bounds on a name change inferred from observations."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ChangeWindow:
    prior_id: str
    next_id: str
    last_seen_prior: str
    first_seen_next: str
    prior_act: str
    next_act: str
