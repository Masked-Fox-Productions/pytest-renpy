"""Project loader: parse all .rpy files, sort by init priority, execute into namespace."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from pytest_renpy.mock_renpy.store import StoreNamespace
from pytest_renpy.rpy_parser import Default, Define, InitBlock, Label, parse_file


@dataclass
class ProjectData:
    """Parsed representation of a Ren'Py project."""

    init_blocks: list[InitBlock] = field(default_factory=list)
    defines: list[Define] = field(default_factory=list)
    defaults: list[Default] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    game_dir: Path | None = None

    def execute_into(self, namespace: StoreNamespace, mock_renpy=None):
        """Execute all init blocks and apply defines/defaults into the namespace.

        Args:
            namespace: The StoreNamespace dict to execute code into.
            mock_renpy: A MockRenpy instance to inject. If None, creates a fresh one.
        """
        if mock_renpy is None:
            mock_renpy = create_mock()

        persistent = MockPersistent()

        namespace["renpy"] = mock_renpy
        namespace["persistent"] = persistent
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

        path_added = None
        if self.game_dir is not None:
            game_dir_str = str(self.game_dir)
            if game_dir_str not in sys.path:
                sys.path.insert(0, game_dir_str)
                path_added = game_dir_str

        try:
            for block in self.init_blocks:
                try:
                    exec(block.code, namespace)  # noqa: S102
                except SyntaxError as exc:
                    raise SyntaxError(
                        f"{exc.msg} (from {block.source_file}:{block.source_line})",
                        (block.source_file,
                         (exc.lineno or 0) + block.source_line - 1,
                         exc.offset,
                         exc.text),
                    ) from exc
                except Exception as exc:
                    raise RuntimeError(
                        f"Error executing init block from "
                        f"{block.source_file}:{block.source_line}: {exc}"
                    ) from exc

            sorted_defines = sorted(self.defines, key=lambda d: d.priority)
            for defn in sorted_defines:
                try:
                    namespace[defn.name] = eval(defn.expression, namespace)  # noqa: S307
                except Exception as exc:
                    raise RuntimeError(
                        f"Error evaluating define '{defn.name} = {defn.expression}': {exc}"
                    ) from exc

            for default in self.defaults:
                if default.name not in namespace:
                    try:
                        namespace[default.name] = eval(default.expression, namespace)  # noqa: S307
                    except Exception as exc:
                        raise RuntimeError(
                            f"Error evaluating default '{default.name} = {default.expression}': {exc}"
                        ) from exc
        finally:
            if path_added is not None:
                try:
                    sys.path.remove(path_added)
                except ValueError:
                    pass


def load_project(project_dir: str | Path) -> ProjectData:
    """Load a Ren'Py project from a directory.

    Parses all .rpy files, collects init blocks sorted by priority,
    and gathers defines, defaults, and labels.

    Args:
        project_dir: Path to the project directory (should contain .rpy files,
            typically the game/ subdirectory).

    Returns:
        ProjectData with all parsed elements ready for execution.
    """
    project_dir = Path(project_dir)

    rpy_files = sorted(project_dir.rglob("*.rpy"))

    all_init_blocks: list[InitBlock] = []
    all_defines: list[Define] = []
    all_defaults: list[Default] = []
    all_labels: list[Label] = []

    for rpy_file in rpy_files:
        parsed = parse_file(rpy_file)
        all_init_blocks.extend(parsed.init_blocks)
        all_defines.extend(parsed.defines)
        all_defaults.extend(parsed.defaults)
        all_labels.extend(parsed.labels)

    all_init_blocks.sort(key=lambda b: (b.priority, b.source_file, b.source_line))

    return ProjectData(
        init_blocks=all_init_blocks,
        defines=all_defines,
        defaults=all_defaults,
        labels=all_labels,
        game_dir=project_dir,
    )
