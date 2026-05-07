"""Mock renpy.random — wraps stdlib random.Random with deterministic seed."""

import random as _stdlib_random


class MockRandom(_stdlib_random.Random):
    """A seeded Random instance mimicking renpy.random.

    Defaults to seed=0 for deterministic test behavior.
    Exposes the same interface as Python's random.Random.
    """

    def __init__(self, seed=0):
        super().__init__(seed)
