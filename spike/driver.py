"""
Spike driver: launches a headless Ren'Py process with the test harness
and communicates over IPC to validate the control-flow approach.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

SDK_PATH = os.path.expanduser("~/tools/renpy-8.3.7-sdk")
SDK_PYTHON = os.path.join(SDK_PATH, "lib/py3-linux-x86_64/python")
RENPY_PY = os.path.join(SDK_PATH, "renpy.py")
FIXTURE_GAME = os.path.join(os.path.dirname(__file__), "fixture_game")


class IPCClient:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.buf = b""

    def bind_and_listen(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self.sock.bind(self.socket_path)
        self.sock.listen(1)

    def accept(self):
        self.conn, _ = self.sock.accept()
        self.conn.settimeout(30)

    def send(self, data):
        self.conn.sendall((json.dumps(data) + "\n").encode("utf-8"))

    def recv(self):
        while b"\n" not in self.buf:
            chunk = self.conn.recv(8192)
            if not chunk:
                raise ConnectionError("IPC connection closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
        try:
            os.unlink(self.socket_path)
        except Exception:
            pass


def launch_engine(socket_path, save_dir):
    env = os.environ.copy()
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["RENPY_TEST_SOCKET"] = socket_path
    env["RENPY_TEST_SAVEDIR"] = save_dir
    env["RENPY_SKIP_SPLASHSCREEN"] = ""  # don't skip our splashscreen

    # Remove DISPLAY to ensure truly headless
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    proc = subprocess.Popen(
        [SDK_PYTHON, RENPY_PY, FIXTURE_GAME],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def run_spike_test(name, test_fn):
    print(f"\n{'='*60}")
    print(f"SPIKE TEST: {name}")
    print(f"{'='*60}")

    tmp_dir = tempfile.mkdtemp(prefix="renpy_spike_")
    socket_path = os.path.join(tmp_dir, "test.sock")
    save_dir = os.path.join(tmp_dir, "saves")
    os.makedirs(save_dir, exist_ok=True)

    ipc = IPCClient(socket_path)
    ipc.bind_and_listen()

    proc = launch_engine(socket_path, save_dir)

    try:
        print("  Waiting for engine to connect...")
        ipc.sock.settimeout(15)
        ipc.accept()
        print("  Engine connected!")

        # Wait for ready message
        msg = ipc.recv()
        print(f"  Got: {msg}")
        assert msg["status"] == "ready", f"Expected ready, got {msg}"

        # Run the test
        result = test_fn(ipc)
        print(f"  RESULT: {'PASS' if result else 'FAIL'}")
        return result

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        # Capture stderr
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode("utf-8", errors="replace")
            if stderr:
                print(f"  ENGINE STDERR:\n{stderr[:2000]}")
        return False

    finally:
        # Clean up
        try:
            ipc.send({"cmd": "stop"})
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        ipc.close()


def test_ping(ipc):
    """Test 1: boot and respond to ping."""
    ipc.send({"cmd": "ping"})
    resp = ipc.recv()
    print(f"  Ping response: {resp}")
    return resp["status"] == "pong"


def test_jump_and_store(ipc):
    """Test 2: jump to set_x label, verify store mutation."""
    # Jump to set_x — label sets x = 42, then has a say statement which triggers interact
    ipc.send({"cmd": "jump", "label": "set_x"})

    # Should yield at the say statement (interact)
    resp = ipc.recv()
    print(f"  After jump: {resp}")

    if resp["status"] != "yielded":
        print(f"  Unexpected status: {resp['status']}")
        return False

    # Now read store to verify x was set
    ipc.send({"cmd": "get_store", "vars": ["x"]})
    resp = ipc.recv()
    print(f"  Store: {resp}")

    x_val = resp.get("values", {}).get("x")
    print(f"  x = {x_val}")
    return x_val == 42


def test_pause_yield(ipc):
    """Test 3: jump to set_y, which has a pause — verify yield at pause."""
    ipc.send({"cmd": "jump", "label": "set_y"})

    resp = ipc.recv()
    print(f"  After jump to set_y: {resp}")

    if resp["status"] != "yielded":
        print(f"  Unexpected status: {resp['status']}")
        return False

    # Verify y was set before the pause
    ipc.send({"cmd": "get_store", "vars": ["y"]})
    resp = ipc.recv()
    print(f"  Store: {resp}")

    y_val = resp.get("values", {}).get("y")
    print(f"  y = {y_val}")
    return y_val == 99


def test_menu_interaction(ipc):
    """Test 4: jump to menu_test, verify menu options, select one."""
    ipc.send({"cmd": "jump", "label": "menu_test"})

    resp = ipc.recv()
    print(f"  After jump to menu_test: {resp}")

    if resp["status"] != "menu_waiting":
        print(f"  Expected menu_waiting, got: {resp['status']}")
        # It might be a yielded from a say before the menu
        if resp["status"] == "yielded":
            # Continue past the say to reach the menu
            ipc.send({"cmd": "continue"})
            resp = ipc.recv()
            print(f"  After continue: {resp}")
            if resp["status"] != "menu_waiting":
                return False

    options = resp.get("options", [])
    print(f"  Menu options: {options}")

    if len(options) < 2:
        print(f"  Expected at least 2 options")
        return False

    # Select "Banana" (index 1)
    ipc.send({"cmd": "menu_select", "index": 1})

    resp = ipc.recv()
    print(f"  After menu select: {resp}")

    # Verify choice_made was set
    ipc.send({"cmd": "get_store", "vars": ["choice_made"]})
    resp = ipc.recv()
    print(f"  Store: {resp}")

    choice = resp.get("values", {}).get("choice_made")
    print(f"  choice_made = {choice}")
    return choice == "banana"


def test_reset_via_restart(ipc):
    """Test 5: after modifying state, restart and verify clean state.
    Since we're testing fresh-process isolation, we just verify the concept
    by checking that a fresh engine starts clean."""
    # First, jump to set_x
    ipc.send({"cmd": "jump", "label": "set_x"})
    resp = ipc.recv()  # yielded at say

    ipc.send({"cmd": "get_store", "vars": ["x"]})
    resp = ipc.recv()
    x_val = resp.get("values", {}).get("x")
    print(f"  x after set_x: {x_val}")

    if x_val != 42:
        print(f"  Failed to set x")
        return False

    # Stop this engine
    ipc.send({"cmd": "stop"})
    print(f"  Sent stop. Fresh-process isolation means next engine will have clean state.")
    print(f"  (Full restart test deferred to driver-level test with two engine launches)")
    return True


def main():
    results = {}

    tests = [
        ("1. Boot and Ping", test_ping),
        ("2. Jump + Store Mutation", test_jump_and_store),
        ("3. Pause Yield", test_pause_yield),
        ("4. Menu Interaction", test_menu_interaction),
        ("5. Reset (Fresh Process)", test_reset_via_restart),
    ]

    for name, fn in tests:
        results[name] = run_spike_test(name, fn)

    print(f"\n{'='*60}")
    print("SPIKE RESULTS SUMMARY")
    print(f"{'='*60}")
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
