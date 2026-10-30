"""Compatibility exports; see valintel.analysis.name_history."""
from valintel.analysis.name_history import (
    NameObservation, ChangeWindow, normalize_observation, consolidate,
    changes, by_act, read_observations, write_observations, example_observations,
)
__all__ = ["NameObservation", "ChangeWindow", "normalize_observation", "consolidate",
           "changes", "by_act", "read_observations", "write_observations", "example_observations"]
