"""deckAI harness: measure MTG decklists by simulated play on a pinned Forge engine.

Module boundaries follow the capabilities in
openspec/changes/forge-gauntlet-measurement-rig/specs/:

    harness.engine      -> forge-engine-control
    harness.validation  -> deck-validation
    harness.stats       -> experiment-statistics
    harness.pilot       -> pilot-policy
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
