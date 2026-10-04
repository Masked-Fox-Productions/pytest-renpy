"""Project loader: parse all .rpy files, order the init stream, execute into a namespace.

Init blocks, defines, defaults, and ATL transform names form one stream sorted by
(priority, file, line), where the file key is the path relative to the game
directory without its ``.rpy`` suffix (Ren'Py's script order). Walking the
stream mirrors Ren'Py's init phase:

- init blocks and defines run when reached;
- defaults into the special namespaces ``persistent``, ``gui`` and
  ``preferences`` apply when reached;
- all other defaults are queued and evaluated after the walk, in stream order.
"""

from __future__ import annotations

import difflib
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

from pytest_renpy import CallException, JumpException, QuitException, ReturnException
from pytest_renpy.mock_renpy import (
    Character,
    Dissolve,
    MockPersistent,
    TintMatrix,
    Transform,
    center,
    create_mock,
    dissolve,
    fade,
    left,
    right,
    truecenter,
)
from pytest_renpy.mock_renpy.bag import PermissiveBag
from pytest_renpy.mock_renpy.display import DISPLAY_STUBS, ATLTransform
from pytest_renpy.mock_renpy.text import double_underscore, paragraph, underscore
from pytest_renpy.rpy_parser import (
    Default,
    Define,
    InitBlock,
    Label,
    LabelStatement,
    ParseError,
    TransformDef,
    parse_file,
)

# Ren'Py control-flow exceptions that run_label_python lets through unwrapped.
_CONTROL_FLOW = (JumpException, CallException, ReturnException, QuitException)


class LoadError(Exception):
    """A define/default that Ren'Py itself would reject."""


def _special_namespace(store_path: str | None) -> str | None:
    """Classify a dotted target's store path (renpy/common/000namespaces.rpy)."""
    if store_path is None:
        return None
    if store_path == "gui" or store_path.startswith("gui."):
        return "gui"
    if store_path in ("preferences", "preferences.volume"):
        return "preferences"
    if store_path in ("config", "persistent", "renpy"):
        return store_path
    return None


def _split_target(target: str) -> tuple[str | None, str]:
    if "." not in target:
        return None, target
    store_path, name = target.rsplit(".", 1)
    return store_path, name


def _stored(obj, name):
    """Return (found, value) for a value actually stored on ``obj``.

    Never uses hasattr/getattr: permissive bags answer every read.
    """
    if isinstance(obj, dict):
        return name in obj, obj.get(name)
    if isinstance(obj, PermissiveBag):
        values = obj._values
    elif isinstance(obj, MockPersistent):
        values = obj._data
    else:
        try:
            values = vars(obj)
        except TypeError:
            return False, None
    return name in values, values.get(name)


def _resolve(namespace: dict, store_path: str):
    """Resolve a store path, creating attribute holders for missing segments."""
    obj = namespace
    for segment in store_path.split("."):
        found, value = _stored(obj, segment)
        if not found:
            value = types.SimpleNamespace()
            _assign(namespace, obj, segment, value)
        obj = value
    return obj


def _assign(namespace: dict, obj, name: str, value):
    if obj is namespace:
        namespace[name] = value
    else:
        setattr(obj, name, value)


def _is_preseeded(namespace: dict, target: str) -> bool:
    """Whether the caller already provided a value for a default's target."""
    obj = namespace
    for segment in target.split("."):
        found, obj = _stored(obj, segment)
        if not found:
            return False
    return True


def _compile(source: str, filename: str, first_line: int, mode: str):
    """Compile so that line numbers in errors and tracebacks match the .rpy file."""
    return compile(
        "\n" * (first_line - 1) + source, filename, mode, dont_inherit=True
    )


def _inject_builtins(namespace: dict, mock_renpy, persistent) -> None:
    """Install the mock Ren'Py names that game code expects at init time."""
    namespace["renpy"] = mock_renpy
    namespace["config"] = mock_renpy.config
    namespace["persistent"] = persistent
    namespace["gui"] = PermissiveBag("gui")
    namespace["build"] = PermissiveBag("build")
    namespace["preferences"] = PermissiveBag("preferences")
    namespace["style"] = PermissiveBag("style")
    namespace["_"] = underscore
    namespace["__"] = double_underscore
    namespace["_p"] = paragraph
    namespace["Character"] = Character
    namespace["Transform"] = Transform
    namespace["TintMatrix"] = TintMatrix
    namespace["Dissolve"] = Dissolve
    namespace["dissolve"] = dissolve
    namespace["fade"] = fade
    namespace["right"] = right
    namespace["left"] = left
    namespace["center"] = center
    namespace["truecenter"] = truecenter
    namespace.update(DISPLAY_STUBS)


@dataclass
class LabelRunResult:
    """What run_label_python did: Python statements run, the rest skipped."""

    label: Label
    executed: list[LabelStatement] = field(default_factory=list)
    skipped: list[LabelStatement] = field(default_factory=list)


@dataclass
class ProjectData:
    """Parsed representation of a Ren'Py project."""

    init_items: list = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    game_dir: Path | None = None
    parse_errors: list[ParseError] = field(default_factory=list)
    _code_cache: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def init_blocks(self) -> list[InitBlock]:
        return [i for i in self.init_items if isinstance(i, InitBlock)]

    @property
    def defines(self) -> list[Define]:
        return [i for i in self.init_items if isinstance(i, Define)]

    @property
    def defaults(self) -> list[Default]:
        return [i for i in self.init_items if isinstance(i, Default)]

    def _code(self, item, source: str, first_line: int, mode: str):
        key = (id(item), mode)
        code = self._code_cache.get(key)
        if code is None:
            code = _compile(source, item.source_file, first_line, mode)
            self._code_cache[key] = code
        return code

    def execute_into(
        self, namespace, mock_renpy=None, on_error="raise", persistent=None
    ):
        """Run the init stream into the namespace.

        Args:
            namespace: The StoreNamespace dict to execute code into. Names
                (and stored attributes of objects) already present are
                treated as caller-provided: defaults never overwrite them.
            mock_renpy: A MockRenpy instance to inject. If None, creates a fresh one.
            on_error: "raise" (default) re-raises the first error; "skip"
                records it and continues.
            persistent: A MockPersistent to use, e.g. pre-populated with
                saved data. Defaults to ``namespace["persistent"]`` if the
                caller provided one, else a fresh MockPersistent.

        Returns:
            List of (item, exception) tuples when on_error="skip"; empty when
            on_error="raise". ``item`` is the InitBlock, Define, or Default
            that failed (or the ParseError itself for parse problems) and
            always carries ``source_file`` and ``source_line``.
        """
        if on_error not in ("raise", "skip"):
            raise ValueError(f"on_error must be 'raise' or 'skip', not {on_error!r}")

        preseeded = {
            d.name
            for d in self.defaults
            if _special_namespace(_split_target(d.name)[0]) is None
            and _is_preseeded(namespace, d.name)
        }

        if mock_renpy is None:
            mock_renpy = create_mock()
        if persistent is None:
            persistent = namespace.get("persistent")
        if persistent is None:
            persistent = MockPersistent()
        _inject_builtins(namespace, mock_renpy, persistent)

        path_added = None
        if self.game_dir is not None:
            game_dir_str = str(self.game_dir)
            if game_dir_str not in sys.path:
                sys.path.insert(0, game_dir_str)
                path_added = game_dir_str

        errors = []

        def fail(item, wrapped, cause):
            if on_error == "skip":
                errors.append((item, wrapped))
            else:
                raise wrapped from cause

        try:
            for err in self.parse_errors:
                fail(err, err, None)

            pending = []
            for item in self.init_items:
                if isinstance(item, Default) and _special_namespace(
                    _split_target(item.name)[0]
                ) is None:
                    pending.append(item)
                    continue
                try:
                    self._run_init_item(item, namespace)
                except SyntaxError as exc:
                    if not isinstance(item, InitBlock):
                        fail(item, self._item_error(item, exc), exc)
                        continue
                    wrapped = SyntaxError(
                        f"{exc.msg} (from {item.source_file}:{item.source_line})",
                        (item.source_file, exc.lineno, exc.offset, exc.text),
                    )
                    wrapped.__cause__ = exc
                    fail(item, wrapped, exc)
                except Exception as exc:
                    fail(item, self._item_error(item, exc), exc)

            for item in pending:
                if item.name in preseeded:
                    continue
                try:
                    value = eval(  # noqa: S307
                        self._code(item, item.expression, item.source_line, "eval"),
                        namespace,
                    )
                    store_path, name = _split_target(item.name)
                    obj = namespace if store_path is None else _resolve(namespace, store_path)
                    _assign(namespace, obj, name, value)
                except Exception as exc:
                    fail(item, self._item_error(item, exc), exc)
        finally:
            if path_added is not None:
                try:
                    sys.path.remove(path_added)
                except ValueError:
                    pass

        return errors

    @staticmethod
    def _item_error(item, exc) -> RuntimeError:
        if isinstance(item, InitBlock):
            what = "executing init block"
        elif isinstance(item, Define):
            what = f"evaluating define {item.name}"
        elif isinstance(item, TransformDef):
            what = f"defining transform {item.name}"
        else:
            what = f"evaluating default {item.name}"
        wrapped = RuntimeError(
            f"Error {what} from {item.source_file}:{item.source_line}: {exc}"
        )
        wrapped.__cause__ = exc
        return wrapped

    def _run_init_item(self, item, namespace) -> None:
        if isinstance(item, InitBlock):
            exec(self._code(item, item.code, item.code_line, "exec"), namespace)  # noqa: S102
            return
        if isinstance(item, TransformDef):
            namespace[item.name] = ATLTransform(item.name)
            return

        store_path, name = _split_target(item.name)
        special = _special_namespace(store_path)
        keyword = "define" if isinstance(item, Define) else "default"

        if special == "renpy" or (
            special == ("preferences" if keyword == "define" else "config")
        ):
            raise LoadError(
                f"{keyword} {item.name}: Ren'Py does not allow {keyword} "
                f"in the {store_path} namespace"
            )

        value = eval(  # noqa: S307
            self._code(item, item.expression, item.source_line, "eval"), namespace
        )
        obj = namespace if store_path is None else _resolve(namespace, store_path)

        if special == "persistent":
            if getattr(obj, name) is None:
                setattr(obj, name, value)
            return

        if keyword == "define" and item.operator != "=":
            found, current = _stored(obj, name)
            if not found:
                raise LoadError(f"define {item.name} {item.operator}: {item.name} is not set")
            value = current + value if item.operator == "+=" else current | value

        _assign(namespace, obj, name, value)

    def find_label(self, name: str) -> Label:
        """Return the label called ``name``, or raise a descriptive KeyError."""
        matches = [label for label in self.labels if label.name == name]
        if not matches:
            close = difflib.get_close_matches(name, [l.name for l in self.labels])
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            raise KeyError(f"No label named {name!r}.{hint}")
        if len(matches) > 1:
            where = ", ".join(f"{l.source_file}:{l.source_line}" for l in matches)
            raise KeyError(f"Label {name!r} is defined more than once: {where}")
        return matches[0]

    def run_label_python(self, name: str, namespace) -> LabelRunResult:
        """Run the Python statements of label ``name`` into ``namespace``.

        Only the label's top-level ``$`` lines and ``python:`` blocks run, in
        source order; dialogue, display, menus and Ren'Py control flow are
        skipped and listed on the result. Jump/Call/Return/Quit exceptions
        propagate unchanged; other errors are wrapped with file:line.
        """
        label = self.find_label(name)
        result = LabelRunResult(label=label)
        for stmt in label.body:
            if not stmt.is_python:
                result.skipped.append(stmt)
                continue
            try:
                code = _compile(stmt.code, label.source_file, stmt.code_line, "exec")
                exec(code, namespace)  # noqa: S102
            except _CONTROL_FLOW:
                raise
            except Exception as exc:
                raise RuntimeError(
                    f"Error running label {name} at "
                    f"{label.source_file}:{stmt.source_line}: {exc}"
                ) from exc
            result.executed.append(stmt)
        return result


def _file_key(rpy_file: Path, project_dir: Path) -> str:
    """Ren'Py's script order key: relative POSIX path without the suffix."""
    try:
        rel = rpy_file.relative_to(project_dir)
    except ValueError:
        rel = rpy_file
    return rel.with_suffix("").as_posix()


def load_project(project_dir: str | Path) -> ProjectData:
    """Load a Ren'Py project from a directory.

    Parses all .rpy files and orders init blocks, defines, and defaults into
    one init stream. Parse problems are recorded, never raised.

    Args:
        project_dir: Path to the project directory (should contain .rpy files,
            typically the game/ subdirectory).

    Returns:
        ProjectData with all parsed elements ready for execution.
    """
    project_dir = Path(project_dir)

    keyed_items = []
    labels: list[Label] = []
    parse_errors: list[ParseError] = []

    for rpy_file in sorted(project_dir.rglob("*.rpy")):
        try:
            parsed = parse_file(rpy_file)
        except ParseError as err:
            parse_errors.append(err)
            continue
        parse_errors.extend(parsed.parse_errors)
        labels.extend(parsed.labels)
        key = _file_key(rpy_file, project_dir)
        for item in (
            *parsed.init_blocks, *parsed.defines, *parsed.defaults, *parsed.transforms
        ):
            keyed_items.append(((item.priority, key, item.source_line), item))

    keyed_items.sort(key=lambda pair: pair[0])

    return ProjectData(
        init_items=[item for _, item in keyed_items],
        labels=labels,
        game_dir=project_dir,
        parse_errors=parse_errors,
    )
