"""Riot client connection, roster fetching, names and third-party statistics.

This class orchestrates reads. Network work belongs on a background worker,
never in the Qt GUI event loop.
"""
from __future__ import annotations
import base64
import copy
import json
import os
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
import urllib3

from ..config import (
    ENDPOINTS, GLZ_OVERRIDE, KNOWN_AGENTS, NAME_CACHE_SECONDS,
    STATS_CACHE_SECONDS, STATS_FAILURE_COOLDOWN_SECONDS,
    HENRIK_CONNECT_TIMEOUT, HENRIK_READ_TIMEOUT,
)
from ..models.player import Player
from ..models.snapshot import Snapshot
from ..utils import pd_from_glz

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class RiotAPI:
    def __init__(self):
        self.session = requests.Session()
        self.names: dict[str, tuple[float, str]] = {}
        self.stats: dict[str, tuple[float, tuple[float | None, float | None, int]]] = {}
        self.stats_failures: dict[str, tuple[float, str]] = {}
        self.agents: dict[str, tuple[str, str]] = {}
        self.region = "na"
        self.last_stats_key = None

    def _json(self, method, url, **kwargs):
        response = self.session.request(method, url, timeout=10, **kwargs)
        if not response.ok:
            code = ""
            try:
                body = response.json()
                if isinstance(body, dict):
                    code = body.get("errorCode", "")
            except ValueError:
                pass
            raise RuntimeError(f"HTTP {response.status_code} {code} — {url.split('?')[0].split('://')[-1].split('/')[0]}")
        return response.json()

    def _logs(self):
        path = Path(os.environ.get("LOCALAPPDATA", "")) / "VALORANT/Saved/Logs/ShooterGame.log"
        if not path.is_file():
            raise RuntimeError("ShooterGame.log missing. Start VALORANT first.")
        return path.read_text(encoding="utf-8", errors="ignore")

    def _lockfile(self):
        path = Path(os.environ.get("LOCALAPPDATA", "")) / "Riot Games/Riot Client/Config/lockfile"
        if not path.is_file():
            raise RuntimeError("Riot Client lockfile missing. Start VALORANT first.")
        parts = path.read_text(encoding="utf-8").strip().split(":")
        if len(parts) != 5:
            raise RuntimeError("Riot lockfile has an unexpected format")
        _, _, port, password, _ = parts
        token = base64.b64encode(f"riot:{password}".encode()).decode()
        return int(port), {"Authorization": f"Basic {token}"}

    def connect(self):
        log = self._logs()
        glz_match = re.findall(r"glz-[\w-]+\.[\w-]+\.a\.pvp\.net", log, re.I)
        if not glz_match and not GLZ_OVERRIDE:
            raise RuntimeError("GLZ hostname not found in ShooterGame.log")
        glz = GLZ_OVERRIDE.rstrip("/") if GLZ_OVERRIDE else f"https://{glz_match[-1]}"
        # PD shard may differ from matchmaking affinity (e.g. LATAM on NA shard).
        pd_match = re.findall(r"https://pd\.([a-z0-9-]+)\.a\.pvp\.net", log, re.I)
        shard = pd_match[-1] if pd_match else glz.split(".")[1]
        pd = f"https://pd.{shard}.a.pvp.net"
        self.region = shard if shard in ("na", "eu", "ap", "kr", "br", "latam") else "na"
        version_matches = re.findall(r"CI server version:\s*([^\s]+)", log, re.I)
        if not version_matches:
            raise RuntimeError("Client version missing from ShooterGame.log")
        version = version_matches[-1]
        port, local_headers = self._lockfile()
        # Self-signed certificate is only accepted on the localhost endpoint.
        identity = self._json("GET", f"https://127.0.0.1:{port}" + ENDPOINTS["entitlements"],
                              headers=local_headers, verify=False)
        for prop in ("subject", "accessToken", "token"):
            if not identity.get(prop):
                raise RuntimeError(f"Riot client did not return {prop}; try reopening VALORANT")
        platform = {"platformType": "PC", "platformOS": "Windows",
                    "platformOSVersion": "10.0.19042.1.256.64bit", "platformChipset": "Unknown"}
        headers = {
            "Authorization": f"Bearer {identity['accessToken']}",
            "X-Riot-Entitlements-JWT": identity["token"],
            "X-Riot-ClientPlatform": base64.b64encode(json.dumps(platform).encode()).decode(),
            "X-Riot-ClientVersion": version,
            "User-Agent": "ShooterGame/13 Windows/10.0.19043.1.256.64bit",
        }
        return glz, pd, headers, identity["subject"]

    def fetch_roster(self, glz, headers, self_puuid):
        issues = []
        for mode, prefix in (("PREGAME", "pregame"), ("IN GAME", "coregame")):
            try:
                player_endpoint = ENDPOINTS[f"{prefix}_player"].format(puuid=self_puuid)
                response = self._json("GET", glz + player_endpoint, headers=headers)
                match_id = response.get("MatchID")
                if not match_id:
                    issues.append(f"{prefix}: no MatchID")
                    continue
                match_endpoint = ENDPOINTS[f"{prefix}_match"].format(match_id=match_id)
                data = self._json("GET", glz + match_endpoint, headers=headers)
                if mode == "PREGAME":
                    raw_allies = (data.get("AllyTeam") or {}).get("Players") or []
                    raw_enemies = []  # Deliberately unavailable in agent select.
                else:
                    roster = data.get("Players") or []
                    me = next((p for p in roster if p.get("Subject") == self_puuid), None)
                    if not me:
                        raise RuntimeError("Your PUUID is missing from the CoreGame roster")
                    team = me.get("TeamID")
                    if not team or team.lower() == "neutral":
                        raise RuntimeError("Free-for-all game mode: no ally team to compare")
                    raw_allies = [p for p in roster if p.get("TeamID") == team]
                    raw_enemies = [p for p in roster if p.get("TeamID") != team]
                def parse(records, side):
                    return [Player(puuid=p.get("Subject", ""), team=side,
                                   agent_id=(p.get("CharacterID") or "").lower(),
                                   is_self=p.get("Subject") == self_puuid)
                            for p in records if p.get("Subject")]
                map_id = data.get("MapID") or ""
                map_name = map_id.split("/")[-1].replace("_", " ").title() if map_id else "Map not available"
                return Snapshot(mode=mode, match_id=match_id, map_name=map_name,
                                allies=parse(raw_allies, "ally"), enemies=parse(raw_enemies, "enemy"),
                                status=f"{mode} · {len(raw_allies)} allies"), pd_from_glz(glz)
            except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
                issues.append(f"{prefix}: {exc}")
        return Snapshot(error=" | ".join(issues), status="No active match found"), pd_from_glz(glz)

    def agent_catalog(self):
        """Full playable catalog, including an offline fallback of known agents.

        A network failure must not collapse the agent picker to just a few
        agents. An API success may add newly released agents automatically.
        """
        if self.agents:
            return self.agents

        known = {
            agent_id: (
                name,
                f"https://media.valorant-api.com/agents/{agent_id}/displayicon.png"
            )
            for agent_id, name in KNOWN_AGENTS.items()
        }
        try:
            data = self._json("GET", ENDPOINTS["agents"])
            if isinstance(data, dict):
                for item in data.get("data", []):
                    if not item.get("isPlayableCharacter", True):
                        continue
                    agent_id = (item.get("uuid") or "").lower()
                    agent_name = item.get("displayName") or ""
                    if not re.fullmatch(r"[0-9a-f-]{36}", agent_id) or not agent_name:
                        continue
                    known[agent_id] = (
                        agent_name,
                        item.get("displayIcon") or
                        f"https://media.valorant-api.com/agents/{agent_id}/displayicon.png"
                    )
        except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError):
            pass
        self.agents = known
        return self.agents

    def fill_agents(self, snap):
        mapping = self.agent_catalog()
        for player in snap.allies + snap.enemies:
            if not player.agent_id:
                player.agent = "Selecting…" if snap.mode == "PREGAME" else "Unknown"
            else:
                player.agent, player.icon = mapping.get(player.agent_id,
                    (KNOWN_AGENTS.get(player.agent_id, "Unknown"),
                     f"https://media.valorant-api.com/agents/{player.agent_id}/displayicon.png"))

    def get_riot_names(self, pd, headers, players):
        puuids = [p.puuid for p in players]
        if not puuids:
            return {}
        try:
            data = self._json("PUT", pd + ENDPOINTS["name_service"], json=puuids, headers=headers)
        except Exception:
            return {}
        result = {}
        if isinstance(data, list):
            for p in data:
                if p.get("Subject") and p.get("GameName") and p.get("TagLine"):
                    result[p["Subject"]] = f"{p['GameName']}#{p['TagLine']}"
        return result

    def henrik(self, endpoint, key, params=None):
        """Henrik history may be slower than Riot's local endpoints.

        Use separate sessions for concurrent requests. Retry transient errors once,
        without printing API keys or player IDs in error messages.
        """
        for attempt in range(2):
            try:
                response = requests.get(
                    endpoint,
                    headers={"Authorization": key},
                    params=params,
                    timeout=(HENRIK_CONNECT_TIMEOUT, HENRIK_READ_TIMEOUT),
                )
                if response.status_code == 429:
                    # Obey rate-limit failures; retry on a future refresh.
                    raise RuntimeError("HenrikDEV rate limit (HTTP 429); retry later")
                if response.status_code in (500, 502, 503, 504):
                    if attempt == 0:
                        time.sleep(2)
                        continue
                    raise RuntimeError(f"HenrikDEV server error (HTTP {response.status_code})")
                if response.status_code in (401, 403):
                    raise RuntimeError(f"HenrikDEV authorization failed (HTTP {response.status_code})")
                if not response.ok:
                    raise RuntimeError(f"HenrikDEV returned HTTP {response.status_code}")
                return response.json()
            except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout):
                # Do not retry slow history lookups immediately; the cooldown
                # prevents a burst of expensive requests on subsequent refreshes.
                raise RuntimeError("HenrikDEV timed out; will retry after cooldown")
            except requests.exceptions.ConnectionError:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise RuntimeError("Cannot connect to HenrikDEV; check your connection or service status")
        raise RuntimeError("HenrikDEV request unsuccessful")

    def fill_names(self, snap, pd, headers, henrik_key):
        players = snap.allies + snap.enemies
        public_names = self.get_riot_names(pd, headers, players)
        now = time.time()
        for p in players:
            cached = self.names.get(p.puuid)
            if cached and now - cached[0] < NAME_CACHE_SECONDS:
                p.name = cached[1]
            else:
                p.name = public_names.get(p.puuid, "Hidden / unavailable")
        missing = [p for p in players if p.name == "Hidden / unavailable"]
        if henrik_key and missing:
            def lookup(p):
                url = ENDPOINTS["henrik_account"].format(puuid=p.puuid)
                try:
                    result = self.henrik(url, henrik_key).get("data") or {}
                    if result.get("name") and result.get("tag"):
                        return p.puuid, f"{result['name']}#{result['tag']}"
                except Exception:
                    pass
                return p.puuid, None
            with ThreadPoolExecutor(max_workers=3) as pool:
                for puuid, result in pool.map(lookup, missing):
                    if result:
                        self.names[puuid] = (now, result)
                        next(p for p in missing if p.puuid == puuid).name = result
        for p in players:
            if p.name != "Hidden / unavailable":
                self.names[p.puuid] = (now, p.name)

    def fill_stats(self, snap, henrik_key):
        # A corrected API key must not inherit the previous key's failure cooldown.
        if henrik_key != self.last_stats_key:
            self.stats_failures.clear()
            self.last_stats_key = henrik_key
        if not henrik_key:
            snap.stats_note = "Enter a HenrikDEV API key to retrieve match history."
            return
        players = snap.allies + snap.enemies
        if not snap.enemies:
            snap.stats_note = "Enemy roster is unavailable during agent selection. Try after entering a match."
            return
        now = time.time()
        uncached = []
        failures = []
        cooling_down = 0
        for p in players:
            cached = self.stats.get(p.puuid)
            if cached and now - cached[0] < STATS_CACHE_SECONDS:
                p.kd, p.winrate, p.games = cached[1]
                continue
            failed = self.stats_failures.get(p.puuid)
            if failed and now - failed[0] < STATS_FAILURE_COOLDOWN_SECONDS:
                cooling_down += 1
                continue
            uncached.append(p)
        def fetch(p):
            url = ENDPOINTS["henrik_matches"].format(region=self.region, puuid=p.puuid)
            try:
                payload = self.henrik(url, henrik_key, params={"mode": "competitive", "size": 5})
                games = payload.get("data") or []
                total_k, total_d, outcomes, count = 0, 0, [], 0
                for match in games:
                    if not isinstance(match, dict):
                        continue
                    own = next((x for x in (match.get("players") or {}).get("all_players", [])
                                if x.get("puuid") == p.puuid), None)
                    if not own:
                        continue
                    stats = own.get("stats") or {}
                    if not isinstance(stats.get("kills"), (int, float)) or not isinstance(stats.get("deaths"), (int, float)):
                        continue
                    total_k += stats["kills"]
                    total_d += stats["deaths"]
                    count += 1
                    team = str(own.get("team", "")).lower()
                    teams = match.get("teams") or {}
                    if isinstance(teams, dict) and isinstance(teams.get(team), dict):
                        won = teams[team].get("has_won")
                        if isinstance(won, bool):
                            outcomes.append(won)
                kd = round(total_k / max(1, total_d), 2) if count else None
                wr = sum(outcomes) / len(outcomes) if outcomes else None
                return p.puuid, (kd, wr, count), None
            except Exception as exc:
                return p.puuid, (None, None, 0), str(exc)
        # Only fetch when requested; cache avoids repeated requests every refresh.
        # Limit concurrent calls to reduce load and avoid repeated timeout storms.
        with ThreadPoolExecutor(max_workers=2) as pool:
            for puuid, stats, problem in pool.map(fetch, uncached):
                if problem:
                    failures.append(problem)
                    self.stats_failures[puuid] = (time.time(), problem)
                    continue
                self.stats_failures.pop(puuid, None)
                self.stats[puuid] = (time.time(), stats)
                p = next((p for p in uncached if p.puuid == puuid), None)
                if p:
                    p.kd, p.winrate, p.games = stats
        eligible = sum(p.games >= 3 and p.kd is not None and p.winrate is not None for p in players)
        if failures:
            unique = list(dict.fromkeys(failures))
            snap.stats_note = (
                f"History requests failed: {len(failures)}/{len(uncached)} attempted. "
                f"{unique[0][:110]}. Retry cooldown: {STATS_FAILURE_COOLDOWN_SECONDS}s. "
                f"Eligible: {eligible} players."
            )
        elif eligible < 6:
            snap.stats_note = (
                f"Only {eligible} players have enough recent match data. "
                f"{cooling_down} history lookups cooling down. "
                "Prediction needs 3 players per team with 3+ games and a recorded win rate."
            )
        else:
            snap.stats_note = "Recent Competitive statistics loaded."


    def snapshot_updates(self, henrik_key="", load_stats=False):
        """Yield independent snapshots as live data becomes available.

        Intended to be called in a background thread by the GUI.
        """
        glz, pd, headers, my_id = self.connect()
        snap, _ = self.fetch_roster(glz, headers, my_id)
        if snap.error:
            yield snap
            return
        self.fill_agents(snap)
        yield copy.deepcopy(snap)
        self.fill_names(snap, pd, headers, henrik_key)
        yield copy.deepcopy(snap)
        if load_stats:
            self.fill_stats(snap, henrik_key)
            yield copy.deepcopy(snap)
