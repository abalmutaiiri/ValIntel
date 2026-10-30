"""Historical name observations, validation, and CSV/JSON import/export."""
from __future__ import annotations
import csv
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from ..models.name_observation import NameObservation
from ..models.change_window import ChangeWindow

def _iso_date(value: Any) -> str:
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        timestamp = float(value)
        # APIs may return Unix timestamps in milliseconds.
        if timestamp > 10**11:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Match date is required (YYYY-MM-DD).")
    s = value.strip()
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError as exc:
        raise ValueError("Match date must be YYYY-MM-DD.") from exc

def normalize_observation(raw: dict[str, Any], target_puuid: str) -> NameObservation:
    """Require the same non-empty PUUID in every observation."""
    target = target_puuid.strip().lower()
    if not target:
        raise ValueError("Set your own account PUUID before adding history.")
    record_puuid = str(raw.get("puuid") or "").strip().lower()
    if not record_puuid:
        raise ValueError("Each match record must contain a PUUID.")
    if record_puuid != target:
        raise ValueError("A record belongs to a different PUUID. Nothing was imported.")

    riot_id = str(raw.get("riot_id") or "").strip()
    if "#" not in riot_id or riot_id.startswith("#") or riot_id.endswith("#"):
        raise ValueError("Riot ID must include a player name and tag (Name#TAG).")
    episode_act = str(raw.get("episode_act") or "").strip()
    if not episode_act or len(episode_act) > 70:
        raise ValueError("Episode/Act label is required (e.g., Episode 8 Act 3).")
    match_id = str(raw.get("match_id") or "").strip()
    if not match_id or len(match_id) > 160:
        raise ValueError("A unique match ID is required for each observation.")
    match_date = _iso_date(raw.get("match_date"))
    source_url = str(raw.get("source_url") or "").strip()
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Source link must be an HTTPS URL without credentials.")
    return NameObservation(target, riot_id, episode_act, match_date, match_id, source_url)

def consolidate(records: Iterable[NameObservation]) -> list[NameObservation]:
    """One observation per PUUID/match ID; conflicting values must be corrected."""
    by_match: dict[tuple[str, str], NameObservation] = {}
    for item in records:
        key = (item.puuid.lower(), item.match_id.casefold())
        old = by_match.get(key)
        if old is not None and old != item:
            raise ValueError(f"Conflicting entries for match '{item.match_id}'.")
        by_match[key] = item
    return sorted(by_match.values(), key=lambda v: (v.match_date, v.match_id))

def changes(records: Iterable[NameObservation]) -> list[ChangeWindow]:
    ordered = consolidate(records)
    result: list[ChangeWindow] = []
    for before, after in zip(ordered, ordered[1:]):
        if before.riot_id.casefold() != after.riot_id.casefold():
            result.append(ChangeWindow(
                prior_id=before.riot_id, next_id=after.riot_id,
                last_seen_prior=before.match_date, first_seen_next=after.match_date,
                prior_act=before.episode_act, next_act=after.episode_act,
            ))
    return result

def by_act(records: Iterable[NameObservation]) -> list[tuple[str, list[NameObservation]]]:
    groups: dict[str, list[NameObservation]] = {}
    for item in consolidate(records):
        groups.setdefault(item.episode_act, []).append(item)
    return sorted(groups.items(), key=lambda pair: (pair[1][0].match_date, pair[0].lower()), reverse=True)

def _list_from_json(obj: Any) -> list[dict]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("observations", "records"):
            if isinstance(obj.get(k), list):
                return obj[k]
    raise ValueError("Expected a JSON array, or an object with an 'observations' array.")

def read_observations(path: str | Path, target_puuid: str) -> list[NameObservation]:
    """Load a local user-supplied CSV or JSON snapshot manifest.

    The input is intentionally explicit: it needs the historic Riot ID saved
    at match time. Raw VTL pages and API payloads are not supported because
    there is no verified public schema for how VTL stores historical names.
    """
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError("History file is too large (maximum 2 MB).")
    if path.suffix.lower() == ".json":
        rows = _list_from_json(json.loads(path.read_text(encoding="utf-8-sig")))
    elif path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        raise ValueError("Choose a .json or .csv history manifest.")
    if len(rows) > 2000:
        raise ValueError("A history file may contain at most 2,000 observations.")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Each history observation must be a JSON object / CSV row.")
    return consolidate(normalize_observation(row, target_puuid) for row in rows)

def write_observations(path: str | Path, records: Iterable[NameObservation]) -> None:
    output = Path(path)
    observations = [r.to_dict() for r in consolidate(records)]
    if output.suffix.lower() == ".csv":
        with output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "puuid", "riot_id", "episode_act", "match_date", "match_id", "source_url"])
            writer.writeheader()
            writer.writerows(observations)
    elif output.suffix.lower() == ".json":
        output.write_text(json.dumps({"observations": observations}, indent=2), encoding="utf-8")
    else:
        raise ValueError("Export file must end in .csv or .json.")

def example_observations() -> list[NameObservation]:
    """Illustrative dummy PUUID values; no live player information."""
    puuid = "demo-self-account"
    raw = [
        ("2024-04-11", "Episode 8 Act 2", "OldHandle#NA1", "demo-match-001"),
        ("2024-06-02", "Episode 8 Act 3", "OldHandle#NA1", "demo-match-002"),
        ("2024-08-14", "Episode 9 Act 1", "NextHandle#111", "demo-match-003"),
        ("2024-10-03", "Episode 9 Act 2", "NextHandle#111", "demo-match-004"),
        ("2024-11-15", "Episode 9 Act 3", "FinalHandle#222", "demo-match-005"),
    ]
    return [NameObservation(puuid, name, act, dt, matchid) for dt, act, name, matchid in raw]
