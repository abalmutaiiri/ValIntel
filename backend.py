"""VALORANT Match Intel — backend only (no GUI dependencies).

Contains live Riot client access, agent metadata, name resolution,
match-history caching, and exploratory match comparison.
"""
from __future__ import annotations

import base64
import copy
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Endpoint settings: edit here when APIs change ---
ENDPOINTS = {
    "entitlements": "/entitlements/v1/token",
    "pregame_player": "/pregame/v1/players/{puuid}",
    "pregame_match": "/pregame/v1/matches/{match_id}",
    "pregame_select": "/pregame/v1/matches/{match_id}/select/{agent_id}",
    "pregame_lock": "/pregame/v1/matches/{match_id}/lock/{agent_id}",
    "coregame_player": "/core-game/v1/players/{puuid}",
    "coregame_match": "/core-game/v1/matches/{match_id}",
    "name_service": "/name-service/v2/players",
    "henrik_account": "https://api.henrikdev.xyz/valorant/v1/by-puuid/account/{puuid}",
    "henrik_matches": "https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{region}/{puuid}",
    "agents": "https://valorant-api.com/v1/agents?isPlayableCharacter=true",
}

# Optional hostname override for debugging. Normally read from ShooterGame.log.
GLZ_OVERRIDE = ""
REFRESH_SECONDS = 18
NAME_CACHE_SECONDS = 3600
STATS_CACHE_SECONDS = 600
STATS_FAILURE_COOLDOWN_SECONDS = 90  # Avoid hammering HenrikDEV during a slowdown.
HENRIK_CONNECT_TIMEOUT = 6
HENRIK_READ_TIMEOUT = 25
# Complete playable roster as of October 24, 2026 (29 agents).
# Verified UUIDs from Valorant-API; do not add upcoming unreleased agents.
# Agent metadata is also refreshed from the public API at startup so that
# future playable agents appear automatically without editing this list.
KNOWN_AGENTS = {
    "41fb69c1-4189-7b37-f117-bcaf1e96f1bf": "Astra",
    "5f8d3a7f-467b-97f3-062c-13acf203c006": "Breach",
    "9f0d8ba9-4140-b941-57d3-a7ad57c6b417": "Brimstone",
    "22697a3d-45bf-8dd7-4fec-84a9e28c69d7": "Chamber",
    "1dbf2edd-4729-0984-3115-daa5eed44993": "Clove",
    "117ed9e3-49f3-6512-3ccf-0cada7e3823b": "Cypher",
    "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235": "Deadlock",
    "dade69b4-4f5a-8528-247b-219e5a1facd6": "Fade",
    "e370fa57-4757-3604-3648-499e1f642d3f": "Gekko",
    "95b78ed7-4637-86d9-7e41-71ba8c293152": "Harbor",
    "0e38b510-41a8-5780-5e8f-568b2a4f2d6c": "Iso",
    "add6443a-41bd-e414-f6ad-e58d267f4e95": "Jett",
    "601dbbe7-43ce-be57-2a40-4abd24953621": "KAY/O",
    "1e58de9c-4950-5125-93e9-a0aee9f98746": "Killjoy",
    "7c8a4701-4de6-9355-b254-e09bc2a34b72": "Miks",
    "bb2a4828-46eb-8cd1-e765-15848195d751": "Neon",
    "8e253930-4c05-31dd-1b6c-968525494517": "Omen",
    "eb93336a-449b-9c1b-0a54-a891f7921d69": "Phoenix",
    "f94c3b30-42be-e959-889c-5aa313dba261": "Raze",
    "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc": "Reyna",
    "569fdd95-4d10-43ab-ca70-79becc718b46": "Sage",
    "6f2a04ca-43e0-be17-7f36-b3908627744d": "Skye",
    "320b2a48-4d9b-a075-30f1-1f93a9b638fa": "Sova",
    "b444168c-4e35-8076-db47-ef9bf368f384": "Tejo",
    "92eeef5d-43b5-1d4a-8d03-b3927a09034b": "Veto",
    "707eab51-4836-f488-046a-cda6bf494859": "Viper",
    "efba5359-4016-a1e5-7626-b1ae76895940": "Vyse",
    "df1cb487-4902-002e-5c17-d28e83e78588": "Waylay",
    "7f94d92c-4234-0a36-9646-3a87eb8b5c89": "Yoru",
}


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


class AgentLockService(RiotAPI):
    """Agent-select-specific operations, kept separate from GUI code.

    Uses existing Riot Client credentials. It does not inject into the game.
    Mutating Riot client endpoints are unofficial and carry account-ban risk.
    """

    def _pregame_context(self):
        glz, _pd, headers, puuid = self.connect()
        url = glz + ENDPOINTS["pregame_player"].format(puuid=puuid)
        response = self.session.get(url, headers=headers, timeout=8)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        match_id = response.json().get("MatchID")
        if not match_id:
            return None
        data = self._json(
            "GET", glz + ENDPOINTS["pregame_match"].format(match_id=match_id),
            headers=headers
        )
        me = next(
            (p for p in (data.get("AllyTeam") or {}).get("Players", [])
             if p.get("Subject") == puuid),
            None,
        )
        if me is None:
            raise RuntimeError("Your account is not in the agent-select roster")
        locked_agents = {
            (p.get("CharacterID") or "").lower()
            for p in (data.get("AllyTeam") or {}).get("Players", [])
            if p.get("CharacterSelectionState") == "locked"
            and p.get("Subject") != puuid
        }
        return {
            "match_id": match_id,
            "state": data.get("PregameState", ""),
            "own_state": me.get("CharacterSelectionState", ""),
            "own_character": (me.get("CharacterID") or "").lower(),
            "locked_agents": locked_agents,
            "glz": glz,
            "headers": headers,
        }

    def probe_pregame(self):
        """Return public status fields only, without authentication headers."""
        context = self._pregame_context()
        if context is None:
            return None
        return {
            "match_id": context["match_id"],
            "state": context["state"],
            "own_state": context["own_state"],
            "locked_agents": context["locked_agents"],
        }

    @staticmethod
    def _raise_character_request_error(action, response):
        """Show the server error code without exposing tokens or private IDs."""
        error_code = ""
        try:
            data = response.json()
            if isinstance(data, dict):
                error_code = str(data.get("errorCode") or data.get("code") or "")
        except ValueError:
            pass
        suffix = f" {error_code}" if error_code else ""
        reason = ""
        if response.status_code == 409:
            reason = " — Riot reports a state conflict; the agent or lobby may have changed"
        raise RuntimeError(f"Agent {action} rejected (HTTP {response.status_code}{suffix}){reason}")

    def select_agent(self, agent_id, expected_match_id=None):
        """Hover/select an agent without locking it. One POST, never auto-retry.

        Returns a short status message. Called from a GUI worker thread.
        """
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", agent_id):
            raise ValueError("Agent ID is invalid")
        agent_id = agent_id.lower()
        context = self._pregame_context()
        if context is None:
            raise RuntimeError("No agent-selection lobby detected")
        if expected_match_id is not None and context["match_id"] != expected_match_id:
            raise RuntimeError("Agent-selection lobby changed")
        if context["state"] != "character_select_active":
            raise RuntimeError("Agent selection is not active")
        if context["own_state"] == "locked":
            raise RuntimeError("Your agent is already locked")
        if agent_id in context["locked_agents"]:
            raise RuntimeError("Another teammate already locked that agent")
        if (context["own_state"] == "selected"
                and context["own_character"] == agent_id):
            return "Agent already selected — not locked"

        path = ENDPOINTS["pregame_select"].format(
            match_id=context["match_id"], agent_id=agent_id
        )
        response = self.session.post(
            context["glz"] + path, headers=context["headers"], timeout=8,
        )
        if not response.ok:
            self._raise_character_request_error("selection", response)

        check = self._pregame_context()
        if check is None or check["match_id"] != context["match_id"]:
            raise RuntimeError("Lobby ended after the selection request")
        if (check["own_state"] != "selected"
                or check["own_character"] != agent_id):
            raise RuntimeError("Selection request accepted but agent is not confirmed")
        return "Agent selected (hovered) — not locked"

    def lock_agent(self, match_id, agent_id, cancel_event=None):
        """Select, confirm, then attempt one lock in the same agent-select lobby.

        No automatic retry of either mutating POST: a timeout can be ambiguous.
        """
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", agent_id):
            raise ValueError("Agent ID has an invalid format")
        agent_id = agent_id.lower()
        context = self._pregame_context()
        if context is None or context["match_id"] != match_id:
            raise RuntimeError("Agent selection ended or switched to another lobby")
        if context["state"] != "character_select_active":
            raise RuntimeError("Agent selection is not active")
        if context["own_state"] == "locked":
            return "Your agent is already locked"
        if agent_id in context["locked_agents"]:
            raise RuntimeError("Another teammate already locked that agent")
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Canceled before selecting the agent")

        # Original version tried to lock a character without selecting it first.
        if context["own_state"] != "selected" or context["own_character"] != agent_id:
            select_path = ENDPOINTS["pregame_select"].format(match_id=match_id, agent_id=agent_id)
            selected = self.session.post(
                context["glz"] + select_path,
                headers=context["headers"], timeout=8,
            )
            if not selected.ok:
                self._raise_character_request_error("selection", selected)

            # Confirm Riot applied the selection; it may be rejected or overridden
            # because another player selected the same character at the same time.
            refreshed = self._pregame_context()
            if refreshed is None or refreshed["match_id"] != match_id:
                raise RuntimeError("Lobby changed after selecting the agent")
            context = refreshed
            if context["state"] != "character_select_active":
                raise RuntimeError("Agent selection finished before locking")
            if context["own_state"] == "locked":
                return "Your agent is already locked"
            if context["own_state"] != "selected" or context["own_character"] != agent_id:
                raise RuntimeError("Agent selection was not confirmed by Riot; no lock sent")
            if agent_id in context["locked_agents"]:
                raise RuntimeError("Another teammate already locked that agent")

        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Canceled before sending the lock request")

        lock_path = ENDPOINTS["pregame_lock"].format(match_id=match_id, agent_id=agent_id)
        response = self.session.post(
            context["glz"] + lock_path,
            headers=context["headers"], timeout=8,
        )
        if response.status_code == 409:
            # A conflict is not proof the lock failed: always check actual state.
            # Do not retry the mutating request automatically.
            server_code = ""
            try:
                detail = response.json()
                if isinstance(detail, dict):
                    server_code = str(detail.get("errorCode") or detail.get("code") or "")
            except ValueError:
                pass
            label = f"HTTP 409 {server_code}".strip()
            try:
                after = self._pregame_context()
            except requests.RequestException:
                after = None
            if after is None or after["match_id"] != match_id:
                raise RuntimeError(
                    f"Lock rejected ({label}); the agent-select lobby ended or changed."
                )
            if (after["own_state"] == "locked"
                    and after["own_character"] == agent_id):
                return "Agent is locked (verified from lobby state)"
            if agent_id in after["locked_agents"]:
                raise RuntimeError(
                    f"Lock rejected ({label}); a teammate has locked this agent."
                )
            if after["state"] != "character_select_active":
                raise RuntimeError(
                    f"Lock rejected ({label}); agent selection is no longer active "
                    f"(state: {after['state'] or 'unknown'})."
                )
            if (after["own_state"] == "selected"
                    and after["own_character"] == agent_id):
                raise RuntimeError(
                    f"Lock rejected ({label}); {agent_id[:8]} is still selected "
                    "but Riot refused the lock operation. The API may restrict this "
                    "action; use the in-game Lock In button."
                )
            raise RuntimeError(
                f"Lock rejected ({label}); Riot now reports your selection "
                f"state as '{after['own_state'] or 'none'}'. Select again in-game."
            )
        if not response.ok:
            self._raise_character_request_error("lock", response)
        # Even successful POST can race with a server-side state change.
        try:
            after = self._pregame_context()
        except requests.RequestException:
            after = None
        if after and after["match_id"] == match_id and (after["own_state"] == "locked"
                and after["own_character"] == agent_id):
            return "Agent locked (verified from lobby state)"
        return "Lock request accepted; final state not yet verified"


def pd_from_glz(glz):
    host = glz.replace("https://", "").split(".")
    shard = host[1] if len(host) > 2 else "na"
    return f"https://pd.{shard}.a.pvp.net"


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

def demo_snapshot():
    """Return sample data without any network or VALORANT connection."""
    mapping = {uuid: (name, f"https://media.valorant-api.com/agents/{uuid}/displayicon.png")
               for uuid, name in KNOWN_AGENTS.items()}
    allies_info = [("SomeName#NA1", "Jett", True), ("PlayerTwo#1234", "Sage", False),
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


def fetch_agent_icon(url):
    """Download a trusted agent portrait, or return None on failure."""
    if not url.startswith("https://media.valorant-api.com/agents/"):
        return None
    try:
        response = requests.get(url, timeout=6)
        response.raise_for_status()
        if len(response.content) < 250_000:
            return response.content
    except requests.RequestException:
        pass
    return None
