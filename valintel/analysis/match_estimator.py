"""Experimental match estimate; a heuristic, not a trained ML model."""
from __future__ import annotations
import math

def estimate_match(allies, enemies):
    """Exploratory heuristic; NOT trained ML or a calibrated win probability."""
    def eligible(team):
        return [p for p in team if p.games >= 3 and p.kd is not None and p.winrate is not None]
    a, e = eligible(allies), eligible(enemies)
    if len(a) < 3 or len(e) < 3:
        return None, (len(a), len(e))
    def strength(team):
        return sum(0.65 * math.log(max(0.2, p.kd)) +
                   0.35 * (2 * (p.winrate - 0.5)) for p in team) / len(team)
    diff = strength(a) - strength(e)
    pct = 100 / (1 + math.exp(-1.5 * diff))
    return round(min(65, max(35, pct))), (len(a), len(e))
