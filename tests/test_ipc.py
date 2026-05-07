"""Tests for IPC protocol and socket communication."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading

import pytest

from pytest_renpy.engine.ipc import IPCClient, IPCServer
from pytest_renpy.engine.protocol import (
    Command,
    Response,
    deserialize,
    serialize,
    serialize_value,
)


class TestProtocol:
    def test_serialize_dict(self):
        data = {"cmd": "ping"}
        result = serialize(data)
        assert result.endswith("\n")
        assert json.loads(result.strip()) == {"cmd": "ping"}

    def test_deserialize_json_line(self):
        result = deserialize('{"status": "pong"}')
        assert result == {"status": "pong"}

    def test_roundtrip_nested_primitives(self):
        data = {
            "str": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
            "list": [1, "two", 3.0],
            "dict": {"nested": {"deep": True}},
        }
        line = serialize(data)
        result = deserialize(line.strip())
        assert result == data

    def test_serialize_non_json_object(self):
        class CustomObj:
            pass

        obj = CustomObj()
        data = {"val": obj}
        line = serialize(data)
        result = deserialize(line.strip())
        assert result["val"]["_type"] == "CustomObj"
        assert "_repr" in result["val"]

    def test_serialize_mixed_values(self):
        class Gadget:
            pass

        data = {"name": "test", "count": 5, "obj": Gadget()}
        line = serialize(data)
        result = deserialize(line.strip())
        assert result["name"] == "test"
        assert result["count"] == 5
        assert result["obj"]["_type"] == "Gadget"

    def test_serialize_value_primitive(self):
        assert serialize_value(42) == 42
        assert serialize_value("hello") == "hello"
        assert serialize_value([1, 2]) == [1, 2]

    def test_serialize_value_non_serializable(self):
        result = serialize_value(object())
        assert isinstance(result, dict)
        assert result["_type"] == "object"

    def test_deserialize_malformed_json(self):
        with pytest.raises(json.JSONDecodeError):
            deserialize("not json at all")

    def test_command_to_dict(self):
        cmd = Command("jump", {"label": "start"})
        assert cmd.to_dict() == {"cmd": "jump", "label": "start"}

    def test_response_to_dict(self):
        resp = Response("ok", {"values": {"x": 42}})
        assert resp.to_dict() == {"status": "ok", "values": {"x": 42}}


class TestIPCClientServer:
    @pytest.fixture
    def socket_path(self, tmp_path):
        return str(tmp_path / "test.sock")

    @pytest.fixture
    def server(self, socket_path):
        srv = IPCServer(socket_path, timeout=5.0)
        srv.bind_and_listen()
        yield srv
        srv.close()

    def _connect_client(self, socket_path):
        client = IPCClient(socket_path, timeout=5.0)
        client.connect()
        return client

    def test_client_server_roundtrip(self, server, socket_path):
        def server_side():
            server.accept()
            cmd = server.receive_command()
            server.send_response({"status": "pong", "echo": cmd["cmd"]})

        t = threading.Thread(target=server_side)
        t.start()

        client = self._connect_client(socket_path)
        try:
            resp = client.send_command({"cmd": "ping"})
            assert resp == {"status": "pong", "echo": "ping"}
        finally:
            client.close()
            t.join(timeout=5)

    def test_multiple_roundtrips(self, server, socket_path):
        def server_side():
            server.accept()
            for _ in range(3):
                cmd = server.receive_command()
                server.send_response({"status": "ok", "n": cmd["n"]})

        t = threading.Thread(target=server_side)
        t.start()

        client = self._connect_client(socket_path)
        try:
            for i in range(3):
                resp = client.send_command({"cmd": "test", "n": i})
                assert resp["n"] == i
        finally:
            client.close()
            t.join(timeout=5)

    def test_large_payload(self, server, socket_path):
        large_data = {"cmd": "bulk", "data": "x" * 15000}

        def server_side():
            server.accept()
            cmd = server.receive_command()
            server.send_response({"status": "ok", "len": len(cmd["data"])})

        t = threading.Thread(target=server_side)
        t.start()

        client = self._connect_client(socket_path)
        try:
            resp = client.send_command(large_data)
            assert resp["len"] == 15000
        finally:
            client.close()
            t.join(timeout=5)

    def test_client_connect_closed_server(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.sock")
        client = IPCClient(bad_path, timeout=1.0)
        with pytest.raises((ConnectionError, FileNotFoundError, ConnectionRefusedError)):
            client.connect()

    def test_read_timeout(self, server, socket_path):
        def server_side():
            server.accept()
            # Don't send anything — let client time out

        t = threading.Thread(target=server_side)
        t.start()

        client = IPCClient(socket_path, timeout=0.5)
        client.connect()
        try:
            with pytest.raises(TimeoutError):
                client.recv()
        finally:
            client.close()
            t.join(timeout=5)

    def test_server_cleanup_removes_socket(self, tmp_path):
        path = str(tmp_path / "cleanup.sock")
        srv = IPCServer(path, timeout=1.0)
        srv.bind_and_listen()
        assert os.path.exists(path)
        srv.close()
        assert not os.path.exists(path)


class TestCrossProcessIPC:
    def test_two_processes_communicate(self, tmp_path):
        socket_path = str(tmp_path / "cross.sock")
        server = IPCServer(socket_path, timeout=10.0)
        server.bind_and_listen()

        child_script = f"""
import socket, json, sys
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect({socket_path!r})
sock.sendall((json.dumps({{"cmd": "hello", "pid": __import__("os").getpid()}}) + "\\n").encode())
buf = b""
while b"\\n" not in buf:
    buf += sock.recv(4096)
resp = json.loads(buf.split(b"\\n")[0])
sock.close()
sys.exit(0 if resp["status"] == "ok" else 1)
"""
        proc = subprocess.Popen(
            [sys.executable, "-c", child_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            server.accept()
            cmd = server.receive_command()
            assert cmd["cmd"] == "hello"
            assert isinstance(cmd["pid"], int)
            server.send_response({"status": "ok"})

            rc = proc.wait(timeout=10)
            assert rc == 0
        finally:
            server.close()
            proc.kill()
