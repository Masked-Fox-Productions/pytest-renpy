"""Layer 2 integration tests for minimum-viable-rpg.

Demonstrates: label python: block functions, defaults inside labels.
MVP-RPG defines 18 utility functions inside label init_utils: python:
blocks — invisible to Layer 1's init-block extraction.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pytest_renpy.engine.runner import RenpyEngine

SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))
PROJECT_PATH = Path("/projects/masked_fox/minimum-viable-rpg-renpy")

requires_sdk = pytest.mark.skipif(not SDK_PATH.exists(), reason="SDK not found")
requires_project = pytest.mark.skipif(
    not PROJECT_PATH.exists(), reason="minimum-viable-rpg not found"
)


@requires_sdk
@requires_project
class TestMinimumViableRpgFlow:
    def test_start_label_sets_defaults(self):
        """Jump to start and verify defaults that Layer 1 can't reach."""
        with RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=30) as engine:
            result = engine.jump("start")
            store = engine.get_store("LOCATIONS", "hero_stats")
            # These are set inside label start:, not at top level
            locations = store.get("LOCATIONS")
            hero = store.get("hero_stats")
            assert locations is not None or hero is not None, (
                "Expected at least one of LOCATIONS or hero_stats to be set"
            )

    def test_init_courtyard_sets_location(self):
        """Jump to a location init label and verify store mutation."""
        with RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=30) as engine:
            result = engine.jump("init_courtyard")
            store = engine.get_store("LOCATIONS")
            locations = store.get("LOCATIONS")
            assert locations is not None
