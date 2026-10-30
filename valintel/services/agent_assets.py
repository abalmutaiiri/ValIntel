"""Retrieval of agent portrait images."""
from __future__ import annotations
import requests

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
