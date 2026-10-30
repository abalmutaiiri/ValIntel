"""Offline demonstration data for UI previews and tests."""
from __future__ import annotations
from .config import KNOWN_AGENTS
from .models.player import Player
from .models.snapshot import Snapshot

def demo_snapshot():
    """Return sample data without any network or VALORANT connection."""
    mapping = {uuid: (name, f"https://media.valorant-api.com/agents/{uuid}/displayicon.png")
               for uuid, name in KNOWN_AGENTS.items()}
    allies_info = [("DemoJett#NA1", "Jett", True), ("PlayerTwo#1234", "Sage", False),
                   ("PlayerThree#NA1", "Omen", False), ("PlayerFour#NA1", "Sova", False),
                   ("PlayerFive#NA1", "Raze", False)]
    enemies_info = [("OpponentOne#EU", "Reyna"), ("OpponentTwo#EU", "Cypher"),
                    ("OpponentThree#EU", "Clove"), ("OpponentFour#EU", "Breach"),
                    ("OpponentFive#EU", "Killjoy")]

    def make(name, agent, side, i, is_self=False):
        uuid, icon = next(((k, v[1]) for k, v in mapping.items() if v[0] == agent), ("", ""))
        return Player(puuid=f"demo-{side}-{i}", name=name, team=side,
                      agent=agent, agent_id=uuid, icon=icon, is_self=is_self,
                      kd=[1.31, 0.97, 1.11, 0.88, 1.2][i],
                      winrate=[.6, .4, .6, .4, .6][i], games=5)

    return Snapshot(mode="DEMO", match_id="demo", map_name="Ascent · Demo data",
                    allies=[make(n, a, "ally", i, s) for i, (n, a, s) in enumerate(allies_info)],
                    enemies=[make(n, a, "enemy", i) for i, (n, a) in enumerate(enemies_info)],
                    status="Demo data only — not connected to a VALORANT match")
