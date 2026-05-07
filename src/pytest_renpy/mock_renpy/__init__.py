"""Mock renpy module assembler.

Provides create_mock() factory that returns a fresh mock renpy namespace
with all sub-modules wired up and call tracking initialized.
"""

from pytest_renpy.mock_renpy.exports import RenpyExports
from pytest_renpy.mock_renpy.config import MockConfig
from pytest_renpy.mock_renpy.persistent import MockPersistent
from pytest_renpy.mock_renpy.random import MockRandom
from pytest_renpy.mock_renpy.display import (
    Transform,
    TintMatrix,
    Character,
    Dissolve,
    dissolve,
    fade,
    right,
    left,
    center,
    truecenter,
)


class _NoOpStub:
    """A no-op callable that records calls. Returned for unimplemented APIs.

    Also permissive for chained attribute access (e.g., renpy.music.play).
    """

    def __init__(self, name="unknown"):
        self._name = name
        self._calls = []
        self._children = {}

    def __call__(self, *args, **kwargs):
        self._calls.append({"args": args, "kwargs": kwargs})
        return None

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._children:
            self._children[name] = _NoOpStub(f"{self._name}.{name}")
        return self._children[name]

    def __repr__(self):
        return f"<NoOpStub: renpy.{self._name}>"


class MockRenpy:
    """Mock renpy module with call tracking and permissive fallback.

    Tracks: jumps, calls, pauses, notifications, quit_called, menus,
    scenes, shown, hidden, transitions.

    Unimplemented renpy.* attributes return a no-op callable stub.
    """

    def __init__(self):
        # Call tracking lists
        self.jumps = []
        self.calls = []
        self.pauses = []
        self.notifications = []
        self.quit_called = False
        self.menus = []
        self.scenes = []
        self.shown = []
        self.hidden = []
        self.transitions = []

        # Sub-modules
        self._exports = RenpyExports(self)
        self.config = MockConfig()
        self.random = MockRandom()

        # Stubs cache for permissive fallback
        self._stubs = {}

    # Wire export functions as direct attributes
    def jump(self, target):
        return self._exports.jump(target)

    def call(self, target):
        return self._exports.call(target)

    def return_statement(self):
        return self._exports.return_statement()

    def quit(self):
        return self._exports.quit()

    def pause(self, duration=0):
        return self._exports.pause(duration)

    def notify(self, msg):
        return self._exports.notify(msg)

    def display_menu(self, options):
        return self._exports.display_menu(options)

    def scene(self, *args, **kwargs):
        return self._exports.scene(*args, **kwargs)

    def show(self, name, at_list=None, **kwargs):
        return self._exports.show(name, at_list=at_list, **kwargs)

    def hide(self, name, **kwargs):
        return self._exports.hide(name, **kwargs)

    def with_statement(self, transition):
        return self._exports.with_statement(transition)

    def version(self):
        return self._exports.version()

    def __getattr__(self, name):
        """Permissive fallback: return a no-op stub for unimplemented APIs."""
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._stubs:
            self._stubs[name] = _NoOpStub(name)
        return self._stubs[name]


def create_mock():
    """Factory: create a fresh MockRenpy instance with all tracking reset."""
    return MockRenpy()
