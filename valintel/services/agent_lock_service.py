"""Agent selection/locking service, independent of the GUI."""
from __future__ import annotations
import re
import requests
from ..config import ENDPOINTS
from .riot_api import RiotAPI

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
