"""Post-match repeated-opponent analysis for authorized match histories."""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable, Sequence
from ..config import MAX_MATCHES, ALERT_THRESHOLD
from ..models.pattern_report import PatternReport
from ..models.repeated_opponent import RepeatedOpponent

def _as_list(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []

def _participants(match: dict) -> list[dict]:
    """Henrik v3 uses players.all_players; v4 uses a flat players array."""
    players = match.get("players")
    if isinstance(players, dict):
        return _as_list(players.get("all_players"))
    return _as_list(players)

def _team_id(player: dict) -> str:
    for key in ("team_id", "team", "teamId"):
        team = player.get(key)
        if isinstance(team, dict):
            team = team.get("team_id") or team.get("id")
        if isinstance(team, str) and team.strip():
            return team.strip().lower()
    return ""

def _puuid(player: dict) -> str:
    value = player.get("puuid") or player.get("subject") or player.get("Subject")
    return value.strip().lower() if isinstance(value, str) else ""

def _match_id(match: dict) -> str:
    metadata = match.get("metadata") if isinstance(match.get("metadata"), dict) else {}
    for field in ("matchid", "match_id", "matchId", "id"):
        value = metadata.get(field) or match.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

def _competitive(match: dict) -> bool:
    metadata = match.get("metadata") if isinstance(match.get("metadata"), dict) else {}
    mode = metadata.get("mode") or metadata.get("queue") or metadata.get("queue_id")
    if isinstance(mode, dict):
        mode = mode.get("id") or mode.get("name")
    if isinstance(mode, str) and mode.strip():
        return mode.strip().lower() in ("competitive", "ranked")
    # The API request itself was filtered to competitive; absent metadata
    # should not disqualify an otherwise valid historical record.
    return True

def _won(match: dict, side: str) -> bool | None:
    teams = match.get("teams")
    entry = None
    if isinstance(teams, dict):
        entry = next((v for k, v in teams.items() if str(k).lower() == side), None)
    elif isinstance(teams, list):
        entry = next((v for v in teams if isinstance(v, dict) and
                      str(v.get("team_id") or v.get("team") or "").lower() == side), None)
    if isinstance(entry, dict):
        for field in ("has_won", "won", "hasWon"):
            if isinstance(entry.get(field), bool):
                return entry[field]
    return None

def analyze_match_history(player_name: str, player_puuid: str,
                          matches: Sequence[dict], *, limit: int = MAX_MATCHES,
                          threshold: int = ALERT_THRESHOLD) -> PatternReport:
    """Compute opponent encounter frequencies from historical complete match records.

    Only verified distinct matches where the analyzed player has a nonempty
    team and opponents have distinct teams contribute to the denominator.
    """
    report = PatternReport(player_name=player_name, player_puuid=player_puuid,
                           requested=limit)
    target = player_puuid.lower()
    encountered: dict[str, list[tuple[str, bool | None]]] = defaultdict(list)
    seen_matches: set[str] = set()
    malformed = 0
    for match in matches:
        if report.checked >= limit:
            break
        if not isinstance(match, dict) or not _competitive(match):
            continue
        match_id = _match_id(match)
        if not match_id or match_id in seen_matches:
            malformed += 1
            continue
        members = _participants(match)
        me = next((member for member in members if _puuid(member) == target), None)
        side = _team_id(me) if me else ""
        if not side or side in ("neutral", "none"):
            malformed += 1
            continue
        others = {_puuid(member) for member in members
                  if _puuid(member) and _puuid(member) != target and
                  _team_id(member) and _team_id(member) != side and
                  _team_id(member) not in ("neutral", "none")}
        if not others:
            malformed += 1
            continue
        seen_matches.add(match_id)
        report.checked += 1
        outcome = _won(match, side)
        for opponent in others:
            encountered[opponent].append((match_id, outcome))

    ranked = sorted(
        ((opponent, games) for opponent, games in encountered.items() if len(games) >= threshold),
        key=lambda item: (-len(item[1]), item[0])
    )
    for index, (_, games) in enumerate(ranked, 1):
        report.findings.append(RepeatedOpponent(
            label=f"Repeated opponent {index}", encounters=len(games),
            match_ids=tuple(matchid for matchid, _ in games),
            player_wins=sum(won is True for _, won in games),
            player_losses=sum(won is False for _, won in games)
        ))
    report.status = "complete" if report.checked >= limit else "partial" if report.checked else "unavailable"
    if report.status == "complete":
        report.explanation = "Ten distinct Competitive match records analyzed."
    elif report.checked:
        report.explanation = f"Only {report.checked}/{limit} usable Competitive matches were returned."
    else:
        report.explanation = "No usable Competitive match records."
    if malformed:
        report.explanation += f" {malformed} duplicate/incomplete records skipped."
    return report

def scan_players(players: Sequence[Any], henrik_key: str, region: str,
                 fetch_json: Callable[[str, str, dict], dict],
                 on_result: Callable[[PatternReport], None] | None = None) -> list[PatternReport]:
    """Fetch *only* explicitly selected and authorized histories (max five).

    fetch_json(endpoint, key, params) can be backed by RiotAPI.henrik or a
    test fixture. Requests are sequential to avoid bursts and rate limits.
    """
    if not henrik_key.strip():
        raise ValueError("HenrikDEV API key is required.")
    if len(players) > 5:
        raise ValueError("At most five authorized teammates per scan.")
    if region.lower() not in ("na", "eu", "ap", "kr", "br", "latam"):
        raise ValueError("Unknown region; refresh live match before scanning.")
    reports: list[PatternReport] = []
    for player in players:
        # The GUI is responsible for collecting explicit permission. No
        # player is selected for scanning by default.
        report = PatternReport(player_name=player.name, player_puuid=player.puuid)
        try:
            if not player.puuid or player.puuid.startswith("demo-"):
                raise ValueError("Not a real player history")
            url = ("https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/"
                   f"{region.lower()}/{player.puuid}")
            payload = fetch_json(url, henrik_key, {"mode": "competitive", "size": MAX_MATCHES})
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError("Match-history response did not contain a match list")
            report = analyze_match_history(player.name, player.puuid, payload["data"])
        except Exception as exc:
            # Don't expose sensitive PUUIDs or tokens in UI messages.
            report.explanation = str(exc).split("https://")[0][:160] or type(exc).__name__
        reports.append(report)
        if on_result:
            on_result(report)
    return reports

def demo_reports() -> list[PatternReport]:
    return [
        PatternReport("ExampleJett#NA1", "demo-ally-0", 10, 10,
                      [RepeatedOpponent("Repeated opponent 1", 5,
                                        tuple(f"sample-{n}" for n in (1, 2, 4, 6, 8)), 3, 2)],
                      "complete", "Sample data — not a cheating determination."),
        PatternReport("ExampleSage#NA1", "demo-ally-1", 10, 10, [],
                      "complete", "No opponent reached 4 encounters."),
        PatternReport("ExampleOmen#NA1", "demo-ally-2", 7, 10, [],
                      "partial", "Only 7/10 usable matches returned."),
    ]
