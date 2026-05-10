"""CI test game configuration.

This minimal game is bundled in the repo for CI Layer 2 testing.
It exercises label navigation, variable access, and menu interaction.
"""

import os
from pathlib import Path


def pytest_configure(config):
    project_path = os.environ.get(
        "RENPY_PROJECT", str(Path(__file__).parent)
    )
    if not config.getoption("renpy_project", None) or config.getoption("renpy_project") == ".":
        config.option.renpy_project = project_path
