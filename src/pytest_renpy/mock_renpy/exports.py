"""Mock implementations of renpy.* export functions.

Each function records its call on the mock instance and implements
the expected behavior (raising exceptions for control flow, no-ops
for display operations, etc.).
"""

from pytest_renpy import JumpException, CallException, ReturnException, QuitException


class RenpyExports:
    """Container for renpy.* exported functions, bound to a mock instance."""

    def __init__(self, mock):
        self._mock = mock

    def jump(self, target):
        """Record target and raise JumpException."""
        self._mock.jumps.append(target)
        raise JumpException(target)

    def call(self, target):
        """Record target and raise CallException."""
        self._mock.calls.append(target)
        raise CallException(target)

    def return_statement(self):
        """Raise ReturnException."""
        raise ReturnException()

    def quit(self):
        """Record quit and raise QuitException."""
        self._mock.quit_called = True
        raise QuitException()

    def pause(self, duration=0):
        """Record duration, no-op."""
        self._mock.pauses.append(duration)

    def notify(self, msg):
        """Record notification message."""
        self._mock.notifications.append(msg)

    def display_menu(self, options):
        """Record menu options and return the first option's value."""
        self._mock.menus.append(options)
        # options is a list of (label, value) tuples
        for _label, value in options:
            if value is not None:
                return value
        return None

    def scene(self, *args, **kwargs):
        """Record scene clear."""
        self._mock.scenes.append({"args": args, "kwargs": kwargs})

    def show(self, name, at_list=None, **kwargs):
        """Record show command."""
        self._mock.shown.append({
            "name": name,
            "at_list": at_list or [],
            **kwargs,
        })

    def hide(self, name, **kwargs):
        """Record hide command."""
        self._mock.hidden.append({"name": name, **kwargs})

    def with_statement(self, transition):
        """Record transition, no-op."""
        self._mock.transitions.append(transition)

    def version(self):
        """Return a static version string."""
        return "pytest-renpy mock (Ren'Py 8.0.0 compatible)"
