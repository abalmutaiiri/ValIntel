"""Evidence of a Riot ID appearing in a historical match."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class NameObservation:
    puuid: str
    riot_id: str
    episode_act: str
    match_date: str          # ISO date (YYYY-MM-DD)
    match_id: str
    source_url: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "puuid": self.puuid, "riot_id": self.riot_id,
            "episode_act": self.episode_act, "match_date": self.match_date,
            "match_id": self.match_id, "source_url": self.source_url,
        }
