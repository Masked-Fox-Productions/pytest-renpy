"""Tests for terminalgame command routing logic."""

import pytest

from pytest_renpy import JumpException, QuitException


class TestCheckForCommands:
    def test_quit_raises_quit_exception(self, game):
        ns, mock, _ = game
        with pytest.raises(QuitException):
            ns["check_for_commands"]("quit")

    def test_quit_dispatches_to_quit_command(self, game):
        ns, mock, _ = game
        with pytest.raises(QuitException):
            ns["check_for_commands"]("quit")
        assert mock.quit_called

    def test_unknown_command_jumps_to_handle_tick(self, game):
        ns, mock, _ = game
        with pytest.raises(JumpException) as exc_info:
            ns["check_for_commands"]("nonexistent_command")
        assert exc_info.value.target == "handle_tick"


class TestCreateCmd:
    def test_creates_command_in_category(self, game):
        ns, mock, _ = game
        ns["create_cmd"](
            "temporary_cmds", "test_cmd", "test_dest", info="test info"
        )
        assert "test_cmd" in ns["cmd_dict"]["temporary_cmds"]
        assert ns["cmd_dict"]["temporary_cmds"]["test_cmd"]["destination"] == "test_dest"

    def test_command_becomes_routable(self, game):
        ns, mock, _ = game
        ns["create_cmd"]("temporary_cmds", "test_cmd", "quit_command")
        with pytest.raises(QuitException):
            ns["check_for_commands"]("test_cmd")


class TestDeleteCmd:
    def test_deletes_from_temporary_cmds(self, game):
        ns, mock, _ = game
        ns["create_cmd"]("temporary_cmds", "test_cmd", "test_dest")
        ns["delete_cmd"]("temporary_cmds", "test_cmd")
        assert "test_cmd" not in ns["cmd_dict"]["temporary_cmds"]

    def test_bug_ignores_category_parameter(self, game):
        """The known bug: delete_cmd ignores its category parameter entirely.

        Passing "base_cmds" as the category still deletes from "temporary_cmds"
        because the function hardcodes `cmd_dict['temporary_cmds']`.
        """
        ns, mock, _ = game
        ns["create_cmd"]("temporary_cmds", "test_cmd", "test_dest")
        ns["delete_cmd"]("base_cmds", "test_cmd")
        assert "test_cmd" not in ns["cmd_dict"]["temporary_cmds"]


class TestTakeInput:
    def test_sets_input_mode(self, game):
        from pytest_renpy import CallException

        ns, mock, _ = game
        with pytest.raises(CallException) as exc_info:
            ns["take_input"]("test_dest")
        assert exc_info.value.target == "handle_tick"
        assert ns["input_mode"]["active"] is True
        assert ns["input_mode"]["destination"] == "test_dest"
