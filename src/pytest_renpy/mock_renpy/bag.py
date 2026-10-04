"""Permissive attribute bags for Ren'Py namespaces like gui, build, style."""


class PermissiveBag:
    """An attribute bag that accepts any write and stubs any unknown read.

    Written values are kept in ``_values``, separately from the stubs
    returned for unknown reads, so callers can tell "written" from "stub"
    without ``hasattr`` (which is always true here). Calling a stub, e.g.
    ``gui.init(1920, 1080)`` or ``build.classify("**~", None)``, records
    the call and returns None.
    """

    def __init__(self, name):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_values", {})
        object.__setattr__(self, "_stubs", {})

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._values:
            return self._values[name]
        if name not in self._stubs:
            from pytest_renpy.mock_renpy import _NoOpStub

            self._stubs[name] = _NoOpStub(f"{self._name}.{name}", prefix="")
        return self._stubs[name]

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._values[name] = value

    def __delattr__(self, name):
        try:
            del self._values[name]
        except KeyError:
            raise AttributeError(name) from None

    def __repr__(self):
        return f"<PermissiveBag: {self._name}>"
