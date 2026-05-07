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
