"""Offline evaluation (isolated from operational detection; D-12, D-13).

This package is the only application code allowed to join detector outputs with simulator
reference labels. The operational modules (``app.domain``, ``app.services``, ``app.api``)
never import it; ``tests/test_ground_truth_boundary.py`` enforces both rules.
"""
