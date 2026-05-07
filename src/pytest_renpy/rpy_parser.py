"""Parse .rpy files to extract Python logic for testing.

Implements a line-by-line state machine that extracts:
- init python: blocks (with priority and store name)
- define statements
- default statements
- label metadata
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


@dataclass
class InitBlock:
    """An extracted init python: block."""

    priority: int
    store_name: str | None
    code: str
    source_file: str
    source_line: int


@dataclass
class Define:
    """A define statement."""

    name: str
    expression: str
    priority: int = 0


@dataclass
class Default:
    """A default statement."""

    name: str
    expression: str


@dataclass
class Label:
    """A label declaration."""

    name: str
    source_line: int


@dataclass
class ParsedFile:
    """Result of parsing a single .rpy file."""

    source_file: str
    init_blocks: list[InitBlock] = field(default_factory=list)
    defines: list[Define] = field(default_factory=list)
    defaults: list[Default] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)


class _State(Enum):
    TOPLEVEL = auto()
    IN_INIT_PYTHON = auto()
    IN_LABEL = auto()
    IN_SCREEN = auto()
    IN_RENPY_BLOCK = auto()


# Regex patterns for top-level statements
_RE_INIT_PYTHON = re.compile(
    r"^init\s+(?:(-?\d+)\s+)?python(?:\s+in\s+(\w+))?\s*:\s*$"
)
_RE_PYTHON_EARLY = re.compile(r"^(?:init\s+(?:-?\d+\s+)?)?python\s+early\s*:\s*$")
_RE_DEFINE = re.compile(r"^define\s+(?:(-?\d+)\s+)?(\S+)\s*=\s*(.+)$")
_RE_DEFAULT = re.compile(r"^default\s+(\S+)\s*=\s*(.+)$")
_RE_LABEL = re.compile(r"^label\s+(\w+)(?:\s*\([^)]*\))?\s*:\s*$")
_RE_SCREEN = re.compile(r"^screen\s+\w+")


def _get_indent_level(line: str) -> int | None:
    """Return the number of leading whitespace characters, or None if blank."""
    stripped = line.lstrip()
    if not stripped:
        return None
    return len(line) - len(stripped)


class ParseError(Exception):
    """Error during .rpy file parsing."""

    def __init__(self, message: str, source_file: str, source_line: int):
        self.source_file = source_file
        self.source_line = source_line
        super().__init__(f"{source_file}:{source_line}: {message}")


def parse_file(path: str | Path) -> ParsedFile:
    """Parse a .rpy file and extract Python logic.

    Args:
        path: Path to the .rpy file.

    Returns:
        ParsedFile with extracted init blocks, defines, defaults, and labels.
    """
    path = Path(path)
    source_file = str(path)

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise ParseError(str(e), source_file, 0) from e

    result = ParsedFile(source_file=source_file)
    state = _State.TOPLEVEL

    # State for collecting init python block
    block_lines: list[str] = []
    block_start_line = 0
    block_priority = 0
    block_store_name: str | None = None
    block_indent: int | None = None

    # State for tracking indented blocks to skip
    skip_indent: int | None = None

    def _finish_init_block():
        """Finalize the current init python block."""
        nonlocal block_lines, block_indent
        if not block_lines:
            return
        code_lines = []
        for bl in block_lines:
            stripped = bl.lstrip()
            if not stripped:
                code_lines.append("")
            else:
                indent = len(bl) - len(stripped)
                if block_indent is not None and indent >= block_indent:
                    code_lines.append(bl[block_indent:])
                else:
                    code_lines.append(bl)

        while code_lines and not code_lines[-1].strip():
            code_lines.pop()

        code = "\n".join(code_lines)
        if code.strip():
            result.init_blocks.append(
                InitBlock(
                    priority=block_priority,
                    store_name=block_store_name,
                    code=code,
                    source_file=source_file,
                    source_line=block_start_line,
                )
            )
        block_lines = []
        block_indent = None

    def _dispatch_toplevel(stripped: str, line_num: int) -> _State:
        """Try to match a top-level statement. Returns the new state."""
        nonlocal block_priority, block_store_name, block_start_line
        nonlocal block_lines, block_indent, skip_indent

        if _RE_PYTHON_EARLY.match(stripped):
            skip_indent = None
            return _State.IN_RENPY_BLOCK

        m = _RE_INIT_PYTHON.match(stripped)
        if m:
            block_priority = int(m.group(1)) if m.group(1) else 0
            block_store_name = m.group(2)
            block_start_line = line_num
            block_lines = []
            block_indent = None
            return _State.IN_INIT_PYTHON

        m = _RE_DEFINE.match(stripped)
        if m:
            priority = int(m.group(1)) if m.group(1) else 0
            result.defines.append(
                Define(name=m.group(2), expression=m.group(3).strip(), priority=priority)
            )
            return _State.TOPLEVEL

        m = _RE_DEFAULT.match(stripped)
        if m:
            result.defaults.append(
                Default(name=m.group(1), expression=m.group(2).strip())
            )
            return _State.TOPLEVEL

        m = _RE_LABEL.match(stripped)
        if m:
            result.labels.append(Label(name=m.group(1), source_line=line_num))
            skip_indent = None
            return _State.IN_LABEL

        if _RE_SCREEN.match(stripped):
            skip_indent = None
            return _State.IN_SCREEN

        return _State.TOPLEVEL

    def _try_return_to_toplevel(raw_line: str, line_num: int) -> _State:
        """When leaving a block, re-dispatch the current line at top level."""
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#"):
            return _dispatch_toplevel(stripped, line_num)
        return _State.TOPLEVEL

    for line_num_0, raw_line in enumerate(lines):
        line_num = line_num_0 + 1

        if state == _State.TOPLEVEL:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            state = _dispatch_toplevel(stripped, line_num)

        elif state == _State.IN_INIT_PYTHON:
            indent_level = _get_indent_level(raw_line)

            if indent_level is None:
                # Blank line -- preserve within block
                if block_lines or block_indent is not None:
                    block_lines.append("")
                continue

            if block_indent is None:
                if indent_level == 0:
                    _finish_init_block()
                    state = _try_return_to_toplevel(raw_line, line_num)
                    continue
                block_indent = indent_level

            if indent_level < block_indent:
                _finish_init_block()
                state = _try_return_to_toplevel(raw_line, line_num)
                continue

            block_lines.append(raw_line)

        elif state in (_State.IN_LABEL, _State.IN_SCREEN, _State.IN_RENPY_BLOCK):
            indent_level = _get_indent_level(raw_line)
            if indent_level is None:
                continue

            if skip_indent is None:
                if indent_level == 0:
                    state = _try_return_to_toplevel(raw_line, line_num)
                    continue
                skip_indent = indent_level
            elif indent_level < skip_indent:
                state = _try_return_to_toplevel(raw_line, line_num)
                continue

    # End of file -- finalize any open block
    if state == _State.IN_INIT_PYTHON:
        _finish_init_block()

    return result
