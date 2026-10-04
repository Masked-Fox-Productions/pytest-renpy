"""Mock renpy.config — permissive attribute bag with sensible defaults."""


class MockConfig:
    """Attribute bag for renpy.config.

    Any attribute access returns a sensible default rather than raising
    AttributeError. Known attributes have specific defaults; unknown ones
    read as None. Config lists that stock boilerplate mutates in place
    (``config.overlay_screens.append(...)``) start as fresh empty lists.
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

    _list_defaults = (
        "overlay_screens",
        "character_id_prefixes",
        "underlay",
        "context_callbacks",
        "interact_callbacks",
        "start_callbacks",
        "after_load_callbacks",
        "label_callbacks",
        "periodic_callbacks",
        "per_frame_screens",
        "detached_layers",
        "top_layers",
        "bottom_layers",
        "transient_layers",
        "overlay_layers",
        "context_clear_layers",
        "special_directory_map",
    )

    def __init__(self):
        for name in self._list_defaults:
            setattr(self, name, [])
        self.layers = ["master", "transient", "screens", "overlay"]
        self.keymap = {}
        self.font_replacement_map = {}
        self.tag_layer = {}
        self.tag_zorder = {}
        self.tag_transform = {}
        self.layer_clipping = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._defaults.get(name, None)
