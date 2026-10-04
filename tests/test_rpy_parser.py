"""Tests for the .rpy file parser."""

from pytest_renpy.rpy_parser import (
    Default,
    Define,
    InitBlock,
    Label,
    ParseError,
    ParsedFile,
    parse_file,
)


# ---------------------------------------------------------------------------
# Happy path: single init python block
# ---------------------------------------------------------------------------


def test_single_init_python_block(tmp_path):
    """Parse a file with a single init python: block."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    x = 1\n"
        "    y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    block = result.init_blocks[0]
    assert block.priority == 0
    assert block.store_name is None
    assert block.source_line == 1
    assert "x = 1" in block.code
    assert "y = 2" in block.code
    # Verify extracted code is syntactically valid Python
    compile(block.code, "<test>", "exec")


def test_init_python_with_priority(tmp_path):
    """Parse init 100 python: block, verify priority=100."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init 100 python:\n"
        "    x = 42\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert result.init_blocks[0].priority == 100


def test_init_python_negative_priority(tmp_path):
    """Parse init -1 python: block, verify priority=-1."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init -1 python:\n"
        "    early_setup = True\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert result.init_blocks[0].priority == -1


def test_init_python_with_store_name(tmp_path):
    """Parse init python in mystore: block, verify store_name."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python in mystore:\n"
        "    val = 10\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert result.init_blocks[0].store_name == "mystore"


def test_init_python_priority_and_store(tmp_path):
    """Parse init 5 python in utils: block."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init 5 python in utils:\n"
        "    helper = True\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert result.init_blocks[0].priority == 5
    assert result.init_blocks[0].store_name == "utils"


# ---------------------------------------------------------------------------
# Happy path: define statements
# ---------------------------------------------------------------------------


def test_define_simple(tmp_path):
    """Parse define v = Character("Vince")."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text('define v = Character("Vince")\n')
    result = parse_file(rpy)
    assert len(result.defines) == 1
    d = result.defines[0]
    assert d.name == "v"
    assert d.expression == 'Character("Vince")'
    assert d.priority == 0


def test_define_with_priority(tmp_path):
    """Parse define 5 x = 42."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text("define 5 x = 42\n")
    result = parse_file(rpy)
    assert len(result.defines) == 1
    assert result.defines[0].priority == 5
    assert result.defines[0].name == "x"
    assert result.defines[0].expression == "42"


def test_define_complex_expression(tmp_path):
    """Parse define with complex expression including kwargs."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text('define v = Character("Vince", color="#8B2A3A")\n')
    result = parse_file(rpy)
    assert len(result.defines) == 1
    assert result.defines[0].expression == 'Character("Vince", color="#8B2A3A")'


# ---------------------------------------------------------------------------
# Happy path: default statements
# ---------------------------------------------------------------------------


def test_default_simple(tmp_path):
    """Parse default x = None."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text("default x = None\n")
    result = parse_file(rpy)
    assert len(result.defaults) == 1
    assert result.defaults[0].name == "x"
    assert result.defaults[0].expression == "None"


def test_default_persistent(tmp_path):
    """Parse default persistent.save_data = None."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text("default persistent.save_data = None\n")
    result = parse_file(rpy)
    assert len(result.defaults) == 1
    assert result.defaults[0].name == "persistent.save_data"
    assert result.defaults[0].expression == "None"


def test_default_complex_expression(tmp_path):
    """Parse default with a dict expression."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text('default cmd_dict = {"base_cmds": {}}\n')
    result = parse_file(rpy)
    assert len(result.defaults) == 1
    assert result.defaults[0].name == "cmd_dict"
    assert result.defaults[0].expression == '{"base_cmds": {}}'


# ---------------------------------------------------------------------------
# Happy path: label statements
# ---------------------------------------------------------------------------


def test_label_simple(tmp_path):
    """Parse label fenton_initialize:."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "label fenton_initialize:\n"
        "    \"Hello.\"\n"
    )
    result = parse_file(rpy)
    assert len(result.labels) == 1
    assert result.labels[0].name == "fenton_initialize"
    assert result.labels[0].source_line == 1


def test_label_with_params(tmp_path):
    """Parse label name(param1, param2):."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "label my_label(param1, param2):\n"
        "    pass\n"
    )
    result = parse_file(rpy)
    assert len(result.labels) == 1
    assert result.labels[0].name == "my_label"


# ---------------------------------------------------------------------------
# Happy path: multiple init python blocks
# ---------------------------------------------------------------------------


def test_multiple_init_python_blocks(tmp_path):
    """Parse file with multiple init python: blocks."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    x = 1\n"
        "\n"
        "init python:\n"
        "    y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 2
    assert "x = 1" in result.init_blocks[0].code
    assert "y = 2" in result.init_blocks[1].code


# ---------------------------------------------------------------------------
# Edge case: blank lines within init python block
# ---------------------------------------------------------------------------


def test_init_python_with_blank_lines(tmp_path):
    """init python: followed by blank line then indented code."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "\n"
        "    x = 1\n"
        "    y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert "x = 1" in result.init_blocks[0].code
    assert "y = 2" in result.init_blocks[0].code
    compile(result.init_blocks[0].code, "<test>", "exec")


def test_init_python_blank_lines_between_statements(tmp_path):
    """Blank lines between statements within block are preserved."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    x = 1\n"
        "\n"
        "    y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    code = result.init_blocks[0].code
    assert "x = 1" in code
    assert "y = 2" in code
    # Blank line should be preserved
    lines = code.split("\n")
    assert "" in lines


# ---------------------------------------------------------------------------
# Edge case: mixed content
# ---------------------------------------------------------------------------


def test_mixed_content(tmp_path):
    """init python block, then label, then another init python block."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    x = 1\n"
        "\n"
        "label start:\n"
        "    \"Hello.\"\n"
        "\n"
        "init python:\n"
        "    y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 2
    assert "x = 1" in result.init_blocks[0].code
    assert "y = 2" in result.init_blocks[1].code
    assert len(result.labels) == 1
    assert result.labels[0].name == "start"


# ---------------------------------------------------------------------------
# Edge case: tab indentation
# ---------------------------------------------------------------------------


def test_tab_indentation(tmp_path):
    """init python: with tab indentation."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "\tx = 1\n"
        "\ty = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    code = result.init_blocks[0].code
    assert "x = 1" in code
    assert "y = 2" in code
    compile(code, "<test>", "exec")


# ---------------------------------------------------------------------------
# Edge case: nested indentation (function defs, if/for)
# ---------------------------------------------------------------------------


def test_nested_indentation(tmp_path):
    """Function defs and control flow within init python block."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    def greet(name):\n"
        "        if name:\n"
        "            return f'Hello, {name}!'\n"
        "        return 'Hello!'\n"
        "\n"
        "    for i in range(3):\n"
        "        pass\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    code = result.init_blocks[0].code
    assert "def greet(name):" in code
    assert "return f'Hello, {name}!'" in code
    compile(code, "<test>", "exec")


# ---------------------------------------------------------------------------
# Edge case: file with no extractable Python
# ---------------------------------------------------------------------------


def test_no_extractable_python(tmp_path):
    """File with only Ren'Py dialogue."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "label start:\n"
        '    "Hello, world!"\n'
        '    show character happy\n'
        '    "How are you?"\n'
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 0
    assert len(result.defines) == 0
    assert len(result.defaults) == 0
    assert len(result.labels) == 1


# ---------------------------------------------------------------------------
# Edge case: python early: blocks should be skipped
# ---------------------------------------------------------------------------


def test_python_early_skipped(tmp_path):
    """python early: blocks should be skipped entirely."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "python early:\n"
        "    config.something = True\n"
        "\n"
        "init python:\n"
        "    x = 1\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert "x = 1" in result.init_blocks[0].code
    # python early block should NOT appear
    for block in result.init_blocks:
        assert "config.something" not in block.code


def test_init_python_early_skipped(tmp_path):
    """init python early: blocks should also be skipped."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python early:\n"
        "    config.something = True\n"
        "\n"
        "init python:\n"
        "    x = 1\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert "x = 1" in result.init_blocks[0].code


# ---------------------------------------------------------------------------
# Edge case: screen blocks are skipped
# ---------------------------------------------------------------------------


def test_screen_skipped(tmp_path):
    """Screen definitions are skipped."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "screen main_menu:\n"
        "    vbox:\n"
        '        textbutton "Start" action Start()\n'
        "\n"
        "init python:\n"
        "    x = 1\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert "x = 1" in result.init_blocks[0].code


# ---------------------------------------------------------------------------
# Edge case: comments within init python blocks are preserved
# ---------------------------------------------------------------------------


def test_comments_preserved_in_init_block(tmp_path):
    """Comment lines within init python blocks are preserved."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    # This is a comment\n"
        "    x = 1\n"
        "    # Another comment\n"
        "    y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    code = result.init_blocks[0].code
    assert "# This is a comment" in code
    assert "# Another comment" in code
    compile(code, "<test>", "exec")


# ---------------------------------------------------------------------------
# Edge case: flexible indentation (2 spaces)
# ---------------------------------------------------------------------------


def test_two_space_indentation(tmp_path):
    """init python: with 2-space indentation."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "  x = 1\n"
        "  y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    code = result.init_blocks[0].code
    assert "x = 1" in code
    assert "y = 2" in code
    compile(code, "<test>", "exec")


def test_eight_space_indentation(tmp_path):
    """init python: with 8-space indentation."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "        x = 1\n"
        "        y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    code = result.init_blocks[0].code
    assert "x = 1" in code
    assert "y = 2" in code
    compile(code, "<test>", "exec")


# ---------------------------------------------------------------------------
# Edge case: source_file tracking
# ---------------------------------------------------------------------------


def test_source_file_tracking(tmp_path):
    """ParsedFile and InitBlock track source file path."""
    rpy = tmp_path / "game" / "script.rpy"
    rpy.parent.mkdir(parents=True, exist_ok=True)
    rpy.write_text(
        "init python:\n"
        "    x = 1\n"
    )
    result = parse_file(rpy)
    assert result.source_file == str(rpy)
    assert result.init_blocks[0].source_file == str(rpy)


def test_source_line_tracking(tmp_path):
    """InitBlock tracks the correct source line."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "# Comment\n"
        "\n"
        "init python:\n"
        "    x = 1\n"
    )
    result = parse_file(rpy)
    assert result.init_blocks[0].source_line == 3


# ---------------------------------------------------------------------------
# Error path: nonexistent file
# ---------------------------------------------------------------------------


def test_nonexistent_file(tmp_path):
    """Parser raises ParseError for nonexistent file."""
    import pytest

    rpy = tmp_path / "nonexistent.rpy"
    with pytest.raises(ParseError) as exc_info:
        parse_file(rpy)
    assert "nonexistent.rpy" in str(exc_info.value)
    assert exc_info.value.source_file == str(rpy)
    assert exc_info.value.source_line == 0


# ---------------------------------------------------------------------------
# Edge case: empty file
# ---------------------------------------------------------------------------


def test_empty_file(tmp_path):
    """Parsing an empty file returns empty ParsedFile."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text("")
    result = parse_file(rpy)
    assert len(result.init_blocks) == 0
    assert len(result.defines) == 0
    assert len(result.defaults) == 0
    assert len(result.labels) == 0


# ---------------------------------------------------------------------------
# Complex scenario: realistic .rpy file
# ---------------------------------------------------------------------------


def test_realistic_rpy_file(tmp_path):
    """Parse a realistic .rpy file with mixed content."""
    rpy = tmp_path / "script.rpy"
    rpy.write_text(
        '# Game script\n'
        '\n'
        'define v = Character("Vince", color="#8B2A3A")\n'
        'define n = Character("Narrator")\n'
        '\n'
        'default persistent.save_data = None\n'
        'default typing_message = ""\n'
        '\n'
        'init python:\n'
        '    import random\n'
        '\n'
        '    LOG_WIDTH_LIMIT = 60\n'
        '\n'
        '    def game_print(msg):\n'
        '        terminal_log.append(msg)\n'
        '\n'
        'label start:\n'
        '    "Welcome to the game."\n'
        '    jump main_loop\n'
        '\n'
        'init 100 python:\n'
        '    def late_init():\n'
        '        pass\n'
        '\n'
        'label main_loop:\n'
        '    "Game running..."\n'
    )
    result = parse_file(rpy)

    # Defines
    assert len(result.defines) == 2
    assert result.defines[0].name == "v"
    assert result.defines[1].name == "n"

    # Defaults
    assert len(result.defaults) == 2
    assert result.defaults[0].name == "persistent.save_data"
    assert result.defaults[1].name == "typing_message"

    # Init blocks
    assert len(result.init_blocks) == 2
    assert result.init_blocks[0].priority == 0
    assert "import random" in result.init_blocks[0].code
    assert "LOG_WIDTH_LIMIT = 60" in result.init_blocks[0].code
    assert "def game_print(msg):" in result.init_blocks[0].code
    compile(result.init_blocks[0].code, "<test>", "exec")

    assert result.init_blocks[1].priority == 100
    assert "def late_init():" in result.init_blocks[1].code
    compile(result.init_blocks[1].code, "<test>", "exec")

    # Labels
    assert len(result.labels) == 2
    assert result.labels[0].name == "start"
    assert result.labels[1].name == "main_loop"


# ---------------------------------------------------------------------------
# Edge case: init python block at end of file (no trailing newline)
# ---------------------------------------------------------------------------


def test_init_block_at_eof(tmp_path):
    """init python block at end of file without trailing newline."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    x = 1"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    assert "x = 1" in result.init_blocks[0].code


# ---------------------------------------------------------------------------
# Edge case: various Ren'Py statements are skipped at top level
# ---------------------------------------------------------------------------


def test_renpy_statements_skipped(tmp_path):
    """show, scene, jump, call, return, with, menu are skipped at top level."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    x = 1\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1


# ---------------------------------------------------------------------------
# Edge case: define and default with equals sign in expression
# ---------------------------------------------------------------------------


def test_define_with_equals_in_expression(tmp_path):
    """define with = in the expression part."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text('define pos = Transform(xalign=0.5, yalign=1.0)\n')
    result = parse_file(rpy)
    assert len(result.defines) == 1
    assert result.defines[0].name == "pos"
    assert result.defines[0].expression == "Transform(xalign=0.5, yalign=1.0)"


# ---------------------------------------------------------------------------
# Edge case: label followed immediately by another label
# ---------------------------------------------------------------------------


def test_consecutive_labels(tmp_path):
    """Two labels back to back."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "label first:\n"
        '    "Hello"\n'
        "\n"
        "label second:\n"
        '    "World"\n'
    )
    result = parse_file(rpy)
    assert len(result.labels) == 2
    assert result.labels[0].name == "first"
    assert result.labels[1].name == "second"


# ---------------------------------------------------------------------------
# Edge case: init python block with nested function having deeper indent
# ---------------------------------------------------------------------------


def test_deeply_nested_code(tmp_path):
    """Deeply nested code within init python block."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    def outer():\n"
        "        def inner():\n"
        "            for i in range(10):\n"
        "                if i > 5:\n"
        "                    return i\n"
        "        return inner()\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 1
    code = result.init_blocks[0].code
    compile(code, "<test>", "exec")
    # Execute to verify it works
    ns = {}
    exec(code, ns)
    assert ns["outer"]() == 6


# ---------------------------------------------------------------------------
# Edge case: mixed indentation widths across different blocks
# ---------------------------------------------------------------------------


def test_mixed_indent_widths_across_blocks(tmp_path):
    """Different blocks use different indent widths."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "  x = 1\n"
        "\n"
        "init python:\n"
        "        y = 2\n"
    )
    result = parse_file(rpy)
    assert len(result.init_blocks) == 2
    compile(result.init_blocks[0].code, "<test>", "exec")
    compile(result.init_blocks[1].code, "<test>", "exec")


# ---------------------------------------------------------------------------
# Logical lines: multi-line define/default
# ---------------------------------------------------------------------------


def _parse(tmp_path, content, name="test.rpy"):
    rpy = tmp_path / name
    rpy.write_text(content, encoding="utf-8")
    return parse_file(rpy)


def test_multiline_default_dict(tmp_path):
    """kid-and-king BOOKS shape: a default spanning several lines."""
    result = _parse(
        tmp_path,
        "default BOOKS = {\n"
        '    "a": 1,\n'
        '    "b": 2,\n'
        '    "c": 3,\n'
        '    "d": 4,\n'
        "}\n",
    )
    assert len(result.defaults) == 1
    d = result.defaults[0]
    assert d.name == "BOOKS"
    assert d.source_line == 1
    assert eval(d.expression) == {"a": 1, "b": 2, "c": 3, "d": 4}


def test_multiline_define_nested_dicts(tmp_path):
    result = _parse(
        tmp_path,
        "define WEAPONS = {\n"
        '    "sword": {\n'
        '        "damage": 3,\n'
        '        "tags": ["sharp", "metal",],\n'
        "    },\n"
        '    "club": {"damage": 2},\n'
        "}\n"
        "define AFTER = 1\n",
    )
    assert [d.name for d in result.defines] == ["WEAPONS", "AFTER"]
    assert eval(result.defines[0].expression)["sword"]["tags"] == ["sharp", "metal"]
    assert result.defines[1].source_line == 8


def test_triple_quoted_define(tmp_path):
    result = _parse(
        tmp_path,
        'define gui.about = _p("""\n'
        "First paragraph.\n"
        "\n"
        "label not_a_label:\n"
        '""")\n'
        "define x = 1\n",
    )
    assert [d.name for d in result.defines] == ["gui.about", "x"]
    assert result.labels == []


def test_brackets_inside_strings_ignored(tmp_path):
    result = _parse(
        tmp_path,
        "define a = \"{\"\n"
        "define b = ('(', ')')\n"
        "define c = [1,\n"
        "    2]\n",
    )
    assert [eval(d.expression) for d in result.defines] == ["{", ("(", ")"), [1, 2]]


def test_statement_text_inside_literal_not_dispatched(tmp_path):
    result = _parse(
        tmp_path,
        "define TABLE = [\n"
        "label fake:\n"
        "define fake = 1\n"
        "]\n",
    )
    assert [d.name for d in result.defines] == ["TABLE"]
    assert result.labels == []


def test_comments_and_blanks_inside_literal(tmp_path):
    result = _parse(
        tmp_path,
        "default stats = {\n"
        "    # a comment with { and \" in it\n"
        "\n"
        '    "hp": 10,  # trailing ( comment\n'
        "}\n",
    )
    assert eval(result.defaults[0].expression) == {"hp": 10}


def test_multiline_dialogue_hides_default(tmp_path):
    result = _parse(
        tmp_path,
        'e "first line\n'
        "default score = 99\n"
        'last line"\n'
        "default real = 1\n",
    )
    assert [d.name for d in result.defaults] == ["real"]
    assert result.defaults[0].source_line == 4


def test_single_quoted_string_spanning_lines(tmp_path):
    result = _parse(tmp_path, "define s = 'a\nb'\ndefine t = 2\n")
    assert [(d.name, d.source_line) for d in result.defines] == [("s", 1), ("t", 3)]


def test_backslash_continuation(tmp_path):
    result = _parse(tmp_path, "define total = 1 + \\\n    2\ndefine t = 2\n")
    assert eval(result.defines[0].expression) == 3
    assert result.defines[1].source_line == 3


def test_init_python_continuation_indented_less(tmp_path):
    """A bracketed continuation line shallower than the body doesn't end the block."""
    result = _parse(
        tmp_path,
        "init python:\n"
        "    DATA = [\n"
        "1, 2,\n"
        "    ]\n"
        "    AFTER = len(DATA)\n",
    )
    assert len(result.init_blocks) == 1
    ns = {}
    exec(result.init_blocks[0].code, ns)
    assert ns["AFTER"] == 2


def test_fstring_nested_same_quotes(tmp_path):
    result = _parse(
        tmp_path,
        'define msg = f"{d["k"]}"\n'
        "define after = 1\n",
    )
    assert [d.name for d in result.defines] == ["msg", "after"]
    assert result.parse_errors == []


def test_unterminated_bracket_drops_rest_of_file(tmp_path):
    result = _parse(
        tmp_path,
        "define BEFORE = 0\n"
        "define BROKEN = {\n"
        "define AFTER = 1\n",
    )
    assert [d.name for d in result.defines] == ["BEFORE"]
    assert len(result.parse_errors) == 1
    err = result.parse_errors[0]
    assert err.source_file.endswith("test.rpy")
    assert err.source_line == 2
    assert "bracket" in str(err)


def test_unterminated_string_at_eof(tmp_path):
    result = _parse(
        tmp_path,
        "define BEFORE = 0\n"
        "init python:\n"
        "    x = 1\n"
        '    y = "never closed\n',
    )
    assert [d.name for d in result.defines] == ["BEFORE"]
    # The init block containing the bad line is dropped, not truncated.
    assert result.init_blocks == []
    assert result.parse_errors[0].source_line == 4
    assert "string opened on line 4" in str(result.parse_errors[0])


def test_init_block_line_mapping_with_comments_and_blanks(tmp_path):
    """A runtime error inside an init block maps to the .rpy line."""
    rpy = tmp_path / "test.rpy"
    rpy.write_text(
        "init python:\n"
        "    def ok():\n"
        "        return 1\n"
        "# a comment at column 0\n"
        "\n"
        "    def boom():\n"
        "        raise KeyError('x')\n"
    )
    block = parse_file(rpy).init_blocks[0]
    raise_line = block.code.split("\n").index("    raise KeyError('x')")
    assert block.code_line + raise_line == 7


def test_triple_quoted_string_in_block_not_dedented(tmp_path):
    result = _parse(
        tmp_path,
        "init python:\n"
        '    TEXT = """line one\n'
        "        indented two\n"
        '    three"""\n',
    )
    ns = {}
    exec(result.init_blocks[0].code, ns)
    assert ns["TEXT"] == "line one\n        indented two\n    three"


def test_bom_then_init_offset(tmp_path):
    rpy = tmp_path / "gui.rpy"
    rpy.write_bytes("\ufeffinit offset = -2\ndefine gui.x = 1\n".encode("utf-8"))
    result = parse_file(rpy)
    assert result.defines[0].priority == -2


def test_define_default_carry_location(tmp_path):
    result = _parse(tmp_path, "\ndefine a = 1\n\ndefault b = 2\n")
    assert (result.defines[0].source_file, result.defines[0].source_line) == (
        str(tmp_path / "test.rpy"),
        2,
    )
    assert result.defaults[0].source_line == 4


# ---------------------------------------------------------------------------
# Label bodies: hoisting init-time statements
# ---------------------------------------------------------------------------


def test_init_python_inside_label(tmp_path):
    result = _parse(
        tmp_path,
        "label init_utils:\n"
        "    init python:\n"
        "        def f():\n"
        "            return 1\n",
    )
    assert len(result.init_blocks) == 1
    block = result.init_blocks[0]
    assert block.source_line == 2
    ns = {}
    exec(block.code, ns)
    assert ns["f"]() == 1


def test_init_python_priority_store_inside_label(tmp_path):
    result = _parse(
        tmp_path,
        "label x:\n"
        "    init -5 python in mystore:\n"
        "        a = 1\n"
        "    init python hide:\n"
        "        b = 1\n"
        "    init python in a.b:\n"
        "        c = 1\n",
    )
    assert [(b.priority, b.store_name) for b in result.init_blocks] == [
        (-5, "mystore"),
        (0, None),
        (0, "a.b"),
    ]


def test_multiline_default_inside_label(tmp_path):
    result = _parse(
        tmp_path,
        "label init_item_library:\n"
        "    default item_library = {\n"
        '        "potion": 1,\n'
        "    }\n"
        "    return\n",
    )
    assert result.defaults[0].name == "item_library"
    assert eval(result.defaults[0].expression) == {"potion": 1}


def test_explicit_priorities_on_define_and_default(tmp_path):
    result = _parse(tmp_path, "default 5 late = 1\ndefine -3 early = 0\n")
    assert result.defaults[0].priority == 5
    assert result.defines[0].priority == -3


def test_label_continues_after_init_python(tmp_path):
    result = _parse(
        tmp_path,
        "label a:\n"
        "    init python:\n"
        "        x = 1\n"
        '    "Some dialogue"\n'
        "    define later = 2\n"
        "    init python:\n"
        "        y = 2\n"
        "label b:\n"
        "    define in_b = 3\n",
    )
    assert len(result.init_blocks) == 2
    assert result.init_blocks[0].code == "x = 1"
    assert [d.name for d in result.defines] == ["later", "in_b"]
    assert [l.name for l in result.labels] == ["a", "b"]


def test_forests_bane_shape_comment_at_lower_indent(tmp_path):
    result = _parse(
        tmp_path,
        "label init_utils:\n"
        "    init python:\n"
        "        def one():\n"
        "            return 1\n"
        "    # section comment at label indent\n"
        "        def two():\n"
        "            return 2\n",
    )
    assert len(result.init_blocks) == 1
    ns = {}
    exec(result.init_blocks[0].code, ns)
    assert ns["two"]() == 2


def test_init_offset_toplevel(tmp_path):
    result = _parse(
        tmp_path,
        "init offset = -2\n"
        "define gui.x = 1\n"
        "init python:\n"
        "    a = 1\n"
        "init offset = 0\n"
        "define y = 1\n",
    )
    assert [d.priority for d in result.defines] == [-2, 0]
    assert result.init_blocks[0].priority == -2


def test_init_offset_block_scoped(tmp_path):
    result = _parse(
        tmp_path,
        "label a:\n"
        "    init offset = 5\n"
        "    define in_label = 1\n"
        "define after = 1\n",
    )
    assert [(d.name, d.priority) for d in result.defines] == [
        ("in_label", 5),
        ("after", 0),
    ]


def test_init_offset_inherited_by_label(tmp_path):
    result = _parse(tmp_path, "init offset = -2\nlabel a:\n    define x = 1\n")
    assert result.defines[0].priority == -2


def test_enclosing_init_priority(tmp_path):
    result = _parse(
        tmp_path,
        "init -10:\n"
        "    define d = 1\n"
        "    define 5 e = 2\n"
        "    default f = 3\n",
    )
    assert [d.priority for d in result.defines] == [-10, -10]
    assert result.defaults[0].priority == -10

    result = _parse(
        tmp_path,
        "init offset = 3\n"
        "init -10:\n"
        "    define d = 1\n"
        "    default f = 3\n",
        name="offset.rpy",
    )
    assert result.defines[0].priority == -7
    assert result.defaults[0].priority == -7


def test_nested_init_keeps_own_priority(tmp_path):
    result = _parse(
        tmp_path,
        "init -10:\n"
        "    init python:\n"
        "        X = 1\n"
        "    init 5 python:\n"
        "        Y = 1\n",
    )
    assert [b.priority for b in result.init_blocks] == [0, 5]


def test_python_and_dollar_inside_init_block(tmp_path):
    """MVR shape: `init:` / `$ ...`, and `init -1:` / `python:`."""
    result = _parse(
        tmp_path,
        "init:\n"
        "    call init_utils\n"
        "    $ config.rollback_enabled = False\n"
        "init -1:\n"
        "    python:\n"
        "        X = 1\n",
    )
    assert [(b.priority, b.code, b.source_line) for b in result.init_blocks] == [
        (0, "config.rollback_enabled = False", 3),
        (-1, "X = 1", 5),
    ]


def test_dialogue_continuation_in_label_not_hoisted(tmp_path):
    result = _parse(
        tmp_path,
        "label a:\n"
        '    e "first\n'
        "    default score = 99\n"
        '    last"\n',
    )
    assert result.defaults == []


def test_define_inside_triple_quoted_python_string_not_hoisted(tmp_path):
    result = _parse(
        tmp_path,
        "label a:\n"
        "    python:\n"
        '        s = """\n'
        "define x = 1\n"
        '        """\n',
    )
    assert result.defines == []


def test_screen_default_not_extracted(tmp_path):
    result = _parse(
        tmp_path,
        "screen top:\n"
        "    default local = 1\n"
        "label a:\n"
        "    pass\n"
        "screen after_label:\n"
        "    default other = 1\n"
        "    python:\n"
        "        z = 1\n",
    )
    assert result.defaults == []
    assert result.init_blocks == []


def test_label_python_block_not_hoisted(tmp_path):
    """R10: plain python: in a label stays runtime (MVR layer boundary)."""
    result = _parse(
        tmp_path,
        "label init_utils:\n"
        "    python:\n"
        "        def g():\n"
        "            return 1\n",
    )
    assert result.init_blocks == []


def test_define_inside_label_if_block_hoisted(tmp_path):
    result = _parse(
        tmp_path,
        "label a:\n"
        "    if True:\n"
        "        define nested = 1\n",
    )
    assert result.defines[0].name == "nested"


def test_label_metadata_location(tmp_path):
    result = _parse(tmp_path, "\nlabel start:\n    pass\n")
    assert (result.labels[0].name, result.labels[0].source_line) == ("start", 2)
    assert result.labels[0].source_file == str(tmp_path / "test.rpy")


def test_label_body_statements_recorded(tmp_path):
    result = _parse(
        tmp_path,
        "label a:\n"
        '    e "Hi"\n'
        "    $ x = {\n"
        "        1: 2,\n"
        "    }\n"
        "    python:\n"
        "        y = 1\n"
        "    menu:\n"
        '        "Choice":\n'
        "            $ z = 1\n"
        "    define d = 1\n",
    )
    body = result.labels[0].body
    assert [(s.kind, s.source_line) for s in body] == [
        ("e", 2),
        ("python", 3),
        ("python", 6),
        ("menu", 8),
        ("define", 11),
    ]
    assert eval(compile(body[1].code, "<t>", "exec")) is None
    assert body[2].code == "y = 1"
    assert body[2].code_line == 7


def test_transform_statement_recorded(tmp_path):
    result = _parse(
        tmp_path,
        "transform slide_down:\n"
        "    yoffset -50\n"
        "init offset = -1\n"
        "transform 2 pulse(d=1.0):\n"
        "    alpha 1.0\n",
    )
    assert [(t.name, t.priority, t.source_line) for t in result.transforms] == [
        ("slide_down", 0, 1),
        ("pulse", 1, 4),
    ]


def test_label_header_variants(tmp_path):
    result = _parse(
        tmp_path,
        "label start(a=(1, 2), b=f(3)):\n"
        "    pass\n"
        "label hidden hide:\n"
        "    pass\n"
        "label .sub:\n"
        "    pass\n"
        "label start.other:\n"
        "    pass\n",
    )
    assert [l.name for l in result.labels] == [
        "start",
        "hidden",
        "hidden.sub",
        "start.other",
    ]
