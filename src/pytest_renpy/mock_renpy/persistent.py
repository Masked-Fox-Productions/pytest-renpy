"""Mock persistent storage — attribute-access object backed by a dict."""


class MockPersistent:
    """Persistent storage mock.

    Supports arbitrary attribute assignment and access. Starts empty.
    Backed by an internal dict.
    """

    def __init__(self):
        object.__setattr__(self, "_data", {})

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data.get(name, None)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def __delattr__(self, name):
        try:
            del self._data[name]
        except KeyError:
            raise AttributeError(name) from None
