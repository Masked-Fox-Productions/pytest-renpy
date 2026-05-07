## pytest-renpy Layer 2 test harness.
## Injected into the game directory at test time.
## Connects to a Unix domain socket for IPC with the pytest test runner.

init -999 python:
    import socket as _socket
    import json as _json
    import os as _os

    _harness_sock = None
    _harness_buf = b""
    _harness_connected = False

    def _harness_connect():
        global _harness_sock, _harness_connected
        sock_path = _os.environ.get("RENPY_TEST_SOCKET")
        if not sock_path:
            return False
        _harness_sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        _harness_sock.connect(sock_path)
        _harness_connected = True
        return True

    def _harness_send(data):
        _harness_sock.sendall((_json.dumps(data, default=_harness_fallback_serializer) + "\n").encode("utf-8"))

    def _harness_recv():
        global _harness_buf
        while b"\n" not in _harness_buf:
            chunk = _harness_sock.recv(8192)
            if not chunk:
                raise ConnectionError("IPC connection closed")
            _harness_buf += chunk
        line, _harness_buf = _harness_buf.split(b"\n", 1)
        return _json.loads(line.decode("utf-8"))

    def _harness_fallback_serializer(obj):
        return {"_type": type(obj).__name__, "_repr": repr(obj)}

    def _harness_serialize_value(val):
        try:
            _json.dumps(val)
            return val
        except (TypeError, ValueError):
            return _harness_fallback_serializer(val)

    def _harness_get_store_vars(var_names):
        values = {}
        for name in var_names:
            val = getattr(renpy.store, name, None)
            values[name] = _harness_serialize_value(val)
        return values

    def _harness_get_current_label():
        try:
            node_id = renpy.game.context().current
            if node_id is not None:
                node = renpy.game.script.lookup(node_id)
                if hasattr(node, "name"):
                    return node.name
                filename = getattr(node, "filename", "")
                linenumber = getattr(node, "linenumber", 0)
                return str(filename) + ":" + str(linenumber)
        except Exception:
            pass
        return None

    def _harness_find_label_for_node():
        """Walk up from current node to find the containing label name."""
        try:
            node_id = renpy.game.context().current
            node = renpy.game.script.lookup(node_id)
            for label_name, label_node in renpy.game.script.namemap.items():
                if not isinstance(label_name, str):
                    continue
                if label_name.startswith("_"):
                    continue
                if hasattr(label_node, "filename") and hasattr(node, "filename"):
                    if label_node.filename == node.filename:
                        if hasattr(label_node, "linenumber") and hasattr(node, "linenumber"):
                            if label_node.linenumber <= node.linenumber:
                                # Check if this is the closest label before our line
                                pass
        except Exception:
            pass
        return _harness_get_current_label()

    def _harness_command_loop():
        """Process IPC commands. Returns when navigation or advance requires
        returning control to Ren'Py's execution engine."""
        while True:
            cmd = _harness_recv()
            action = cmd.get("cmd", "")

            if action == "ping":
                _harness_send({"status": "pong"})

            elif action == "get_store":
                var_names = cmd.get("vars", [])
                values = _harness_get_store_vars(var_names)
                _harness_send({"status": "ok", "values": values})

            elif action == "set_store":
                for k, v in cmd.get("vars", {}).items():
                    setattr(renpy.store, k, v)
                _harness_send({"status": "ok"})

            elif action == "jump":
                raise renpy.game.JumpException(cmd["label"])

            elif action == "call":
                raise renpy.game.CallException(cmd["label"])

            elif action == "advance":
                return cmd

            elif action == "continue":
                return cmd

            elif action == "menu_select":
                return cmd

            elif action == "stop":
                _harness_send({"status": "stopping"})
                try:
                    _harness_sock.close()
                except Exception:
                    pass
                renpy.quit()

            else:
                _harness_send({"status": "error", "message": "unknown command: " + action})

    _original_ui_interact = renpy.ui.interact

    def _patched_ui_interact(**kwargs):
        if not _harness_connected:
            return _original_ui_interact(**kwargs)

        interact_type = kwargs.get("type", "unknown")
        label = _harness_get_current_label()

        response = {
            "status": "yielded",
            "at_label": label,
            "yield_type": interact_type,
        }

        _harness_send(response)

        cmd = _harness_command_loop()
        return True

    _original_display_menu = renpy.display_menu

    def _patched_display_menu(items, interact=True, **kwargs):
        if not _harness_connected or not interact:
            return _original_display_menu(items, interact=interact, **kwargs)

        response = {
            "status": "menu_waiting",
            "at_label": _harness_get_current_label(),
            "options": [],
        }
        selectable = []
        for text, val in items:
            if val is not None:
                response["options"].append({"text": str(text)})
                selectable.append((text, val))

        _harness_send(response)

        cmd = _harness_command_loop()
        action = cmd.get("cmd", "")

        if action == "menu_select":
            index = cmd.get("index", 0)
            if 0 <= index < len(selectable):
                chosen_text, chosen_val = selectable[index]
            elif selectable:
                chosen_text, chosen_val = selectable[0]
            else:
                return None

            if isinstance(chosen_val, renpy.ui.ChoiceReturn):
                chosen_val = chosen_val.value

            renpy.exports.checkpoint(chosen_val)
            return chosen_val

        return None

    if _os.environ.get("RENPY_TEST_SOCKET"):
        renpy.ui.interact = _patched_ui_interact
        renpy.display_menu = _patched_display_menu
        renpy.exports.display_menu = _patched_display_menu

        renpy.config.performance_test = False

        savedir = _os.environ.get("RENPY_TEST_SAVEDIR")
        if savedir:
            renpy.config.savedir = savedir

        renpy.random.seed(0)

        _harness_connect()

init 999 python:
    if _os.environ.get("RENPY_TEST_SOCKET"):
        renpy.store.menu = _patched_display_menu

label splashscreen:
    python:
        if _harness_connected:
            _harness_send({"status": "ready"})
            _harness_command_loop()
    return
