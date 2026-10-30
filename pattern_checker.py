"""Compatibility exports; see valintel.analysis.pattern_checker."""
from valintel.analysis.pattern_checker import (
    MAX_MATCHES, ALERT_THRESHOLD, RepeatedOpponent, PatternReport,
    analyze_match_history, scan_players, demo_reports,
)
__all__ = ["MAX_MATCHES", "ALERT_THRESHOLD", "RepeatedOpponent", "PatternReport",
           "analyze_match_history", "scan_players", "demo_reports"]
