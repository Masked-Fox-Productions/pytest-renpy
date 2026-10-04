"""Parse .rpy files to extract Python logic for testing.

Parsing happens in three passes, mirroring Ren'Py's own lexer:

1. Split the file into *logical lines* (``renpy/lexer.py``
   ``list_logical_lines``): a newline only ends a statement when no bracket is
   open, strings in any quote style may span lines, backslash-newline
   continues a line, and blank/comment-only lines are dropped.
2. Group logical lines into a block tree by indentation.
3. Walk the tree with a stack of init-context frames (``init offset`` and the
   enclosing ``init N:`` priority are block-scoped, as in ``subblock_lexer``)
   and extract:

   - ``init python`` blocks, ``define`` and ``default`` statements at any
     depth, including inside label bodies (Ren'Py runs them at init time);
   - plain ``python:`` blocks and ``$`` lines directly inside ``init N:``
     blocks (also init-time);
   - label metadata plus each label's top-level body statements, for the
     opt-in ``run_label_python`` API.

Screen bodies are skipped entirely (a screen ``default`` is screen-local).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InitBlock:
    """An extracted init-time Python block.

    ``source_line`` is the line of the statement that introduced the block
    (``init python:``, ``python:`` or ``$``); ``code_line`` is the physical
    line that the first line of ``code`` came from.
    """

    priority: int
    store_name: str | None
    code: str
    source_file: str
    source_line: int
    code_line: int = 0

    def __post_init__(self):
        if not self.code_line:
            self.code_line = self.source_line + 1


@dataclass
class Define:
    """A define statement."""

    name: str
    expression: str
    priority: int = 0
    source_file: str = ""
    source_line: int = 0
    operator: str = "="


@dataclass
class Default:
    """A default statement."""

    name: str
    expression: str
    priority: int = 0
    source_file: str = ""
    source_line: int = 0


@dataclass
class TransformDef:
    """An ATL ``transform name:`` statement; defines ``name`` at init time.

    Only the name is captured; ATL semantics are not emulated.
    """

    name: str
    priority: int = 0
    source_file: str = ""
    source_line: int = 0


@dataclass
class LabelStatement:
    """One top-level statement in a label body.

    ``kind`` is ``"python"`` for ``$`` lines and ``python:`` blocks (``code``
    holds the dedented Python); for anything else it is the statement's
    leading keyword (``"say"`` for dialogue) and the statement is skipped by
    ``run_label_python``.
    """

    kind: str
    source_line: int
    text: str = ""
    code: str | None = None
    code_line: int = 0

    @property
    def is_python(self) -> bool:
        return self.kind == "python"


@dataclass
class Label:
    """A label declaration."""

    name: str
    source_line: int
    source_file: str = ""
    body: list[LabelStatement] = field(default_factory=list)


class ParseError(Exception):
    """Error during .rpy file parsing."""

    def __init__(self, message: str, source_file: str, source_line: int):
        self.source_file = source_file
        self.source_line = source_line
        super().__init__(f"{source_file}:{source_line}: {message}")


@dataclass
class ParsedFile:
    """Result of parsing a single .rpy file."""

    source_file: str
    init_blocks: list[InitBlock] = field(default_factory=list)
    defines: list[Define] = field(default_factory=list)
    defaults: list[Default] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    transforms: list[TransformDef] = field(default_factory=list)
    parse_errors: list[ParseError] = field(default_factory=list)


# Statement patterns, matched against a logical line's comment-free text.
_RE_PYTHON_EARLY = re.compile(
    r"^(?:init\s+(?:-?\d+\s+)?)?python\s+early\b.*:$", re.S
)
_RE_INIT_PYTHON = re.compile(
    r"^init\s+(?:(-?\d+)\s+)?python(?:\s+hide)?(?:\s+in\s+([\w.]+))?\s*:$"
)
_RE_INIT_OFFSET = re.compile(r"^init\s+offset\s*=\s*(-?\d+)$")
_RE_INIT_BLOCK = re.compile(r"^init(?:\s+(-?\d+))?\s*:$")
_RE_PYTHON_BLOCK = re.compile(r"^python(?:\s+hide)?(?:\s+in\s+([\w.]+))?\s*:$")
_RE_DEFINE = re.compile(
    r"^define\s+(?:(-?\d+)\s+)?([\w.]+)\s*(\+=|\|=|=)\s*(.+)$", re.S
)
_RE_DEFAULT = re.compile(r"^default\s+(?:(-?\d+)\s+)?([\w.]+)\s*=\s*(.+)$", re.S)
_RE_LABEL = re.compile(r"^label\s+([\w.]+)\s*(?:\(.*\))?\s*(?:hide\s*)?:$", re.S)
_RE_SCREEN = re.compile(r"^screen\s+\w+")
_RE_TRANSFORM = re.compile(r"^transform\s+(?:(-?\d+)\s+)?(\w+)\s*(?:\(.*\))?\s*:$", re.S)
_RE_WORD = re.compile(r"[A-Za-z_]\w*")


# ---------------------------------------------------------------------------
# Pass 1: logical lines
# ---------------------------------------------------------------------------


@dataclass
class _LogicalLine:
    start: int  # first physical line (1-based)
    end: int  # last physical line (1-based)
    indent: int  # leading whitespace of the first physical line
    text: str  # comment-free text, stripped; may contain newlines


def _logical_lines(data: str, source_file: str):
    """Split ``data`` into logical lines following Ren'Py's lexer rules.

    Returns ``(lines, error)``. On an unterminated statement (EOF with an
    open bracket or string), ``lines`` holds everything before it and
    ``error`` is a ParseError at the statement's first line.
    """
    data = data + "\n\n"  # Ren'Py does the same "to fix lousy editors".
    n = len(data)
    pos = 0
    number = 1
    rv: list[_LogicalLine] = []

    while pos < n:
        start_number = number
        start_pos = pos
        buf: list[str] = []
        depth = 0
        open_string_line = None

        while pos < n:
            c = data[pos]

            if c == "\n" and not depth:
                text = "".join(buf).strip()
                if text:
                    raw = data[start_pos:pos]
                    indent = len(raw) - len(raw.lstrip(" \t"))
                    rv.append(_LogicalLine(start_number, number, indent, text))
                pos += 1
                number += 1
                break

            if c == "\n":
                number += 1

            if c == "\r":
                pos += 1
                continue

            if c == "\\" and data[pos + 1] == "\n":
                buf.append("\\\n")
                pos += 2
                number += 1
                continue

            if c in "([{":
                depth += 1
            elif c in ")]}" and depth:
                depth -= 1

            if c == "#":
                while data[pos] != "\n":
                    pos += 1
                continue

            if c in "\"'`":
                delim = c
                open_string_line = number
                pos += 1
                quote = delim
                if data[pos:pos + 2] == delim * 2:
                    quote = delim * 3
                    pos += 2
                chars = [quote]
                escape = False
                closed = False
                while pos < n:
                    c = data[pos]
                    if c == "\n":
                        number += 1
                    if c == "\r":
                        pos += 1
                        continue
                    if escape:
                        escape = False
                    elif data.startswith(quote, pos):
                        chars.append(quote)
                        pos += len(quote)
                        closed = True
                        break
                    elif c == "\\":
                        escape = True
                    chars.append(c)
                    pos += 1
                buf.append("".join(chars))
                if closed:
                    open_string_line = None
                continue

            buf.append(c)
            pos += 1
        else:
            if "".join(buf).strip():
                if open_string_line is not None:
                    what = f"string opened on line {open_string_line} is never closed"
                else:
                    what = "bracket is never closed"
                return rv, ParseError(
                    f"statement is not terminated ({what})",
                    source_file,
                    start_number,
                )

    return rv, None


# ---------------------------------------------------------------------------
# Pass 2: block tree
# ---------------------------------------------------------------------------


@dataclass
class _Node:
    line: _LogicalLine | None  # None marks where an unterminated statement began
    children: list[_Node] = field(default_factory=list)

    def last_line(self) -> int:
        node = self
        while node.children:
            node = node.children[-1]
        return node.line.end if node.line is not None else 0

    def contains_error(self) -> bool:
        return any(c.line is None or c.contains_error() for c in self.children)


def _build_tree(lines: list[_LogicalLine], error_indent: int | None) -> list[_Node]:
    """Group logical lines into blocks: a line owns the following deeper lines."""
    root: list[_Node] = []
    stack: list[tuple[int, list[_Node]]] = [(-1, root)]

    def add(node: _Node, indent: int):
        while indent <= stack[-1][0]:
            stack.pop()
        stack[-1][1].append(node)
        stack.append((indent, node.children))

    for ll in lines:
        add(_Node(ll), ll.indent)
    if error_indent is not None:
        add(_Node(None), error_indent)
    return root


# ---------------------------------------------------------------------------
# Pass 3: walk
# ---------------------------------------------------------------------------


@dataclass
class _Frame:
    """Init context for one block: Ren'Py's per-lexer init_offset and l.init."""

    offset: int = 0
    init_priority: int | None = None

    def child(self, init_priority: int | None = None) -> _Frame:
        return _Frame(
            self.offset,
            init_priority if init_priority is not None else self.init_priority,
        )

    def resolve(self, own_priority: str | None) -> int:
        """Priority for define/default/python inside this frame."""
        if self.init_priority is not None:
            return self.init_priority
        return int(own_priority or 0) + self.offset


class _Walker:
    def __init__(self, result: ParsedFile, physical: list[str]):
        self.result = result
        self.physical = physical
        self.source_file = result.source_file
        self.global_label: str | None = None

    def block_code(self, node: _Node) -> tuple[str, int]:
        """Dedented code for a Python block node's body.

        The code is the contiguous physical range from the first non-blank
        line after the header to the end of the last body logical line, so
        comment and blank lines are kept and line offsets stay exact. Only the
        first physical line of each logical line is dedented; continuation
        lines stay verbatim.
        """
        block_indent = node.children[0].line.indent
        last = node.last_line()
        first_line = node.line.end + 1
        while not self.physical[first_line - 1].strip():
            first_line += 1

        statement_starts = set()
        continuation = set()
        stack = list(node.children)
        while stack:
            child = stack.pop()
            if child.line is not None:
                statement_starts.add(child.line.start)
                continuation.update(range(child.line.start + 1, child.line.end + 1))
            stack.extend(child.children)

        code_lines = []
        for number in range(first_line, last + 1):
            raw = self.physical[number - 1]
            if number in continuation and number not in statement_starts:
                code_lines.append(raw)
                continue
            leading = len(raw) - len(raw.lstrip(" \t"))
            if leading == len(raw):
                code_lines.append("")
            else:
                code_lines.append(raw[min(leading, block_indent):])
        return "\n".join(code_lines), first_line

    def walk(self, nodes: list[_Node], frame: _Frame, label: Label | None, record: bool):
        """Walk sibling nodes. ``record`` is true for a label's direct body."""
        for node in nodes:
            ll = node.line
            if ll is None:
                continue
            text = ll.text

            if _RE_PYTHON_EARLY.match(text):
                self.skip(label, record, "python early", ll)
                continue

            m = _RE_INIT_PYTHON.match(text)
            if m:
                # A nested init always resolves its own priority, even inside
                # another init block (Ren'Py's init_statement ignores l.init).
                priority = int(m.group(1) or 0) + frame.offset
                self.init_block(node, priority, m.group(2))
                self.skip(label, record, "init python", ll)
                continue

            m = _RE_INIT_OFFSET.match(text)
            if m:
                frame.offset = int(m.group(1))
                continue

            m = _RE_INIT_BLOCK.match(text)
            if m:
                priority = int(m.group(1) or 0) + frame.offset
                self.walk(node.children, frame.child(priority), label, False)
                self.skip(label, record, "init", ll)
                continue

            m = _RE_DEFINE.match(text)
            if m:
                self.result.defines.append(
                    Define(
                        name=m.group(2),
                        expression=m.group(4).strip(),
                        priority=frame.resolve(m.group(1)),
                        source_file=self.source_file,
                        source_line=ll.start,
                        operator=m.group(3),
                    )
                )
                self.skip(label, record, "define", ll)
                continue

            m = _RE_DEFAULT.match(text)
            if m:
                self.result.defaults.append(
                    Default(
                        name=m.group(2),
                        expression=m.group(3).strip(),
                        priority=frame.resolve(m.group(1)),
                        source_file=self.source_file,
                        source_line=ll.start,
                    )
                )
                self.skip(label, record, "default", ll)
                continue

            m = _RE_LABEL.match(text)
            if m:
                name = m.group(1)
                if name.startswith("."):
                    # Local label: qualified by the last global label, as in Ren'Py.
                    name = f"{self.global_label}{name}"
                elif "." not in name:
                    self.global_label = name
                new_label = Label(
                    name=name, source_line=ll.start, source_file=self.source_file
                )
                self.result.labels.append(new_label)
                self.walk(node.children, frame.child(), new_label, True)
                continue

            m = _RE_TRANSFORM.match(text)
            if m:
                self.result.transforms.append(
                    TransformDef(
                        name=m.group(2),
                        priority=frame.resolve(m.group(1)),
                        source_file=self.source_file,
                        source_line=ll.start,
                    )
                )
                self.skip(label, record, "transform", ll)
                continue

            if _RE_SCREEN.match(text):
                self.skip(label, record, "screen", ll)
                continue

            m = _RE_PYTHON_BLOCK.match(text)
            if m:
                if not node.children or node.contains_error():
                    continue
                if frame.init_priority is not None:
                    self.init_block(node, frame.init_priority, m.group(1))
                elif record:
                    code, code_line = self.block_code(node)
                    label.body.append(
                        LabelStatement("python", ll.start, text, code, code_line)
                    )
                continue

            if text.startswith("$"):
                code = text[1:].lstrip()
                if frame.init_priority is not None:
                    self.result.init_blocks.append(
                        InitBlock(
                            priority=frame.init_priority,
                            store_name=None,
                            code=code,
                            source_file=self.source_file,
                            source_line=ll.start,
                            code_line=ll.start,
                        )
                    )
                elif record:
                    label.body.append(
                        LabelStatement("python", ll.start, text, code, ll.start)
                    )
                continue

            # Any other statement: skipped, but its block may hold hoistable
            # init-time statements (e.g. a define inside an `if` in a label).
            if text[0] in "\"'`":
                kind = "say"
            else:
                word = _RE_WORD.match(text)
                kind = word.group(0) if word else text.split()[0]
            self.skip(label, record, kind, ll)
            self.walk(node.children, frame.child(), label, False)

    def init_block(self, node: _Node, priority: int, store_name: str | None):
        if not node.children or node.contains_error():
            return
        code, code_line = self.block_code(node)
        self.result.init_blocks.append(
            InitBlock(
                priority=priority,
                store_name=store_name,
                code=code,
                source_file=self.source_file,
                source_line=node.line.start,
                code_line=code_line,
            )
        )

    @staticmethod
    def skip(label: Label | None, record: bool, kind: str, ll: _LogicalLine):
        if record and label is not None:
            label.body.append(
                LabelStatement(kind, ll.start, ll.text.split("\n", 1)[0])
            )


def parse_file(path: str | Path) -> ParsedFile:
    """Parse a .rpy file and extract Python logic.

    Raises ParseError only when the file cannot be read. Problems in the
    file's content are recorded on ``ParsedFile.parse_errors``; an
    unterminated statement keeps everything before it and drops the rest
    of the file.

    Args:
        path: Path to the .rpy file.

    Returns:
        ParsedFile with extracted init blocks, defines, defaults, and labels.
    """
    path = Path(path)
    source_file = str(path)

    try:
        data = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ParseError(str(e), source_file, 0) from e

    if data.startswith("﻿"):
        data = data[1:]

    result = ParsedFile(source_file=source_file)
    lines, error = _logical_lines(data, source_file)

    physical = [line.rstrip("\r") for line in data.split("\n")]
    error_indent = None
    if error is not None:
        result.parse_errors.append(error)
        raw = physical[error.source_line - 1]
        error_indent = len(raw) - len(raw.lstrip(" \t"))

    tree = _build_tree(lines, error_indent)
    _Walker(result, physical).walk(tree, _Frame(), None, False)
    return result
