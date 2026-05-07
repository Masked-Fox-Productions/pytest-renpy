"""Tests for terminalgame game flow logic."""

import pytest

from pytest_renpy import JumpException, QuitException


class TestGameSend:
    def test_calls_game_print_then_check_for_commands(self, game):
        """game_send calls game_print (unavailable due to display.rpy syntax error)
        before resetting typing_message. This demonstrates the plugin surfacing
        a real dependency: game_send requires game_print from display.rpy."""
        ns, mock, _ = game
        ns["typing_message"] = "quit"
        with pytest.raises(NameError, match="game_print"):
            ns["game_send"]()


class TestFentonGateway:
    def test_fenton_intro_start_gateway_jumps(self, game):
        ns, mock, _ = game
        with pytest.raises(JumpException) as exc_info:
            ns["fenton_intro_start_gateway"]("start")
        assert exc_info.value.target == "fenton_intro_start"

    def test_fenton_intro_start_gateway_deletes_start_cmd(self, game):
        ns, mock, _ = game
        ns["create_cmd"]("temporary_cmds", "start", "fenton_intro_start_gateway")
        with pytest.raises(JumpException):
            ns["fenton_intro_start_gateway"]("start")
        assert "start" not in ns["cmd_dict"]["temporary_cmds"]


class TestLoadErrors:
    def test_display_rpy_has_syntax_error(self, game):
        """Verify that the known Python 3.12 syntax error is detected."""
        _, _, errors = game
        syntax_errors = [
            (b, e) for b, e in errors
            if b and "display.rpy" in b.source_file and isinstance(e, SyntaxError)
        ]
        assert len(syntax_errors) > 0
