"""Mock renpy.config — permissive attribute bag with sensible defaults."""


class MockConfig:
    """Attribute bag for renpy.config.

    Any attribute access returns a sensible default rather than raising
    AttributeError. Known attributes have specific defaults.
    """

    _defaults = {
        "gamedir": "/game",
        "savedir": "/saves",
        "rollback_enabled": True,
        "developer": True,
        "screen_width": 1920,
        "screen_height": 1080,
        "window_title": "pytest-renpy mock",
    }

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._defaults.get(name, None)
