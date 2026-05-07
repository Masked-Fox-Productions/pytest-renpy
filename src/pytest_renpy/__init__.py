"""pytest-renpy: Test Ren'Py game logic without the engine."""


class JumpException(Exception):
    """Raised when renpy.jump() is called."""

    def __init__(self, target):
        self.target = target
        super().__init__(f"jump to '{target}'")


class CallException(Exception):
    """Raised when renpy.call() is called."""

    def __init__(self, target):
        self.target = target
        super().__init__(f"call to '{target}'")


class ReturnException(Exception):
    """Raised when renpy.return_statement() is called."""

    def __init__(self):
        super().__init__("return")


class QuitException(Exception):
    """Raised when renpy.quit() is called."""

    def __init__(self):
        super().__init__("quit")
