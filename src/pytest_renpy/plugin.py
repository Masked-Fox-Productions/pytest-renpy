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
    group.addoption(
        "--renpy-on-error",
        action="store",
        choices=("raise", "skip"),
        default=None,
        help="Layer 1 load errors: 'raise' (default) fails the test; 'skip' "
        "skips the failing item and records it in renpy_load_errors",
    )
    parser.addini(
        "renpy_on_error",
        help="Layer 1 load error mode: raise (default) or skip",
        type="string",
        default="raise",
    )
    parser.addini(
        "renpy_sdk",
        help="Path to the Ren'Py SDK directory (alternative to --renpy-sdk flag)",
        type="string",
        default="",
    )
    parser.addini(
        "renpy_project",
        help="Path to the Ren'Py project directory (alternative to --renpy-project flag)",
        type="string",
        default="",
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
