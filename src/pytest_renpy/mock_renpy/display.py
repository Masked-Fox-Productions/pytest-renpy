"""Display stubs for Transform, TintMatrix, Character, transitions, and position constants."""


class Transform:
    """Stub for renpy.Transform.

    Records kwargs for inspection in tests.
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        args = ", ".join(f"{k}={v!r}" for k, v in self.kwargs.items())
        return f"Transform({args})"


class TintMatrix:
    """Stub for TintMatrix (used in matrixcolor transforms)."""

    def __init__(self, color):
        self.color = color

    def __repr__(self):
        return f"TintMatrix({self.color!r})"


class Character:
    """Stub for Character declarations.

    Character("Name", ...) returns an instance that is itself callable
    (Characters are called to display dialogue in Ren'Py).
    """

    def __init__(self, name=None, **kwargs):
        self.name = name
        self.kwargs = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __call__(self, what="", **kwargs):
        """Simulate saying dialogue — no-op in mock."""
        return None

    def __repr__(self):
        return f"Character({self.name!r})"


class Dissolve:
    """Stub for Dissolve transition."""

    def __init__(self, duration=0.5):
        self.duration = duration

    def __repr__(self):
        return f"Dissolve({self.duration})"


class _TransitionConstant:
    """A named transition constant (dissolve, fade, etc.)."""

    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return self._name


class _PositionConstant:
    """A named position constant (right, left, center, etc.)."""

    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return self._name


# Transition constants
dissolve = _TransitionConstant("dissolve")
fade = _TransitionConstant("fade")

# Position constants
right = _PositionConstant("right")
left = _PositionConstant("left")
center = _PositionConstant("center")
truecenter = _PositionConstant("truecenter")


class RecordingStub:
    """Base for display/action stand-ins that only record their arguments.

    Instances are callable no-ops so they also work where Ren'Py expects a
    transition or action to be invoked.
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        return None

    def __repr__(self):
        parts = [repr(a) for a in self.args]
        parts += [f"{k}={v!r}" for k, v in self.kwargs.items()]
        return f"{type(self).__name__}({', '.join(parts)})"


def _recording(name):
    return type(name, (RecordingStub,), {"__module__": __name__})


# Display, transition, and value stand-ins referenced by stock boilerplate
# (gui.rpy, screens.rpy, options.rpy) and game code at init time.
DISPLAY_STUBS = {
    name: _recording(name)
    for name in (
        "Borders",
        "Pause",
        "MoveTransition",
        "BarValue",
        "Quit",
    )
}


class ATLTransform(RecordingStub):
    """Placeholder bound to the name of an ATL ``transform name:`` statement."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name

    def __repr__(self):
        return f"<ATL transform {self.name}>"
