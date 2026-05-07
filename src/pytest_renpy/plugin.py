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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "renpy: mark test as a Ren'Py game test",
    )
