"""StoreNamespace: a dict subclass that supports attribute access.

This must be a dict subclass because exec(code, namespace) requires a real dict,
and globals() inside exec'd code returns that dict. Attribute access (store.x)
is wired to dict operations (store['x']).
"""


class StoreNamespace(dict):
    """A dict subclass providing attribute-style access to its items.

    Used as the globals dict for exec(). Supports both store['x'] and store.x
    syntax. Built-in dict methods (items, keys, values, get, pop, update, etc.)
    are preserved and take precedence over dict key lookups via attribute access.
    """

    def __getattr__(self, name):
        """Look up name as a dict key, but only for non-dict-method names."""
        # __getattr__ is only called when normal attribute lookup fails,
        # so dict methods (items, keys, values, etc.) are already handled
        # by dict.__getattribute__ before we get here.
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                f"'StoreNamespace' object has no attribute '{name}'"
            ) from None

    def __setattr__(self, name, value):
        """Set name as a dict key."""
        self[name] = value

    def __delattr__(self, name):
        """Delete name from dict keys."""
        try:
            del self[name]
        except KeyError:
            raise AttributeError(
                f"'StoreNamespace' object has no attribute '{name}'"
            ) from None
