"""Translation and text helpers: _, __, _p."""

import textwrap


def underscore(s):
    """Stand-in for Ren'Py's `_()`: marks a string translatable, returns it."""
    return s


def double_underscore(s):
    """Stand-in for Ren'Py's `__()`: translates immediately, returns it."""
    return s


def paragraph(s):
    """Stand-in for Ren'Py's `_p()`.

    Dedents, joins the lines of each paragraph with spaces, and separates
    paragraphs with a blank line.
    """
    paragraphs = []
    for block in textwrap.dedent(s).strip().split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if lines:
            paragraphs.append(" ".join(lines))
    return "\n\n".join(paragraphs)
