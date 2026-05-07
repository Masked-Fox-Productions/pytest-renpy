"""pytest-renpy plugin registration and configuration."""

pytest_plugins = ["pytest_renpy.fixtures"]


def pytest_addoption(parser):
    group = parser.getgroup("renpy", "Ren'Py testing")
    group.addoption(
        "--renpy-project",
        action="store",
        default=".",
        help="Path to the Ren'Py project directory (default: current directory)",
    )
    group.addoption(
        "--renpy-sdk",
        action="store",
        default=None,
        help="Path to the Ren'Py SDK directory (required for Layer 2 integration tests)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "renpy: mark test as a Ren'Py game test",
    )
    config.addinivalue_line(
        "markers",
        "renpy_flow: mark test as a Layer 2 integration test (requires --renpy-sdk)",
    )
