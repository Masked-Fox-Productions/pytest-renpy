"""
Spike: Call-stack depth tracking and return-path verification.

Tests assumptions needed for auto-advance implementation:
1. Call stack depth at idle vs. inside a called label
2. _harness_idle re-entry after a called label returns
3. Nested call depth behavior
4. Jump-from-call depth behavior
5. exec-triggered call depth behavior
6. Duplicate label behavior
"""
import json
import os
import shutil
import subprocess
import socket
import sys
import tempfile

SDK_PATH = os.path.expanduser("~/tools/renpy-8.3.7-sdk")
SDK_PYTHON = os.path.join(SDK_PATH, "lib/py3-linux-x86_64/python")
RENPY_PY = os.path.join(SDK_PATH, "renpy.py")
FIXTURE_GAME = os.path.join(os.path.dirname(__file__), "fixture_game")


class IPC:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.buf = b""
        self.conn = None

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
                raise ConnectionError("IPC closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def close(self):
        for s in [self.conn, self.sock]:
            try:
                s.close()
            except Exception:
                pass
        try:
            os.unlink(self.socket_path)
        except Exception:
            pass


def eval_expr(ipc, expr):
    ipc.send({"cmd": "eval", "expr": expr})
    resp = ipc.recv()
    if resp.get("status") == "error":
        return f"ERROR: {resp.get('message')}"
    return resp.get("result")


def eval_depth(ipc):
    return eval_expr(ipc, "len(renpy.game.context().return_stack)")


def eval_current_node(ipc):
    return eval_expr(ipc, "str(renpy.game.context().current)")


def launch(tmp_dir, harness_override=None):
    socket_path = os.path.join(tmp_dir, "test.sock")
    save_dir = os.path.join(tmp_dir, "saves")
    os.makedirs(save_dir, exist_ok=True)

    tmp_project = os.path.join(tmp_dir, "project")
    game_src = os.path.join(FIXTURE_GAME, "game")
    shutil.copytree(game_src, os.path.join(tmp_project, "game"), symlinks=True)

    harness_src = harness_override or os.path.join(
        os.path.dirname(__file__), "..", "src", "pytest_renpy", "engine", "_test_harness.rpy"
    )
    shutil.copy2(harness_src, os.path.join(tmp_project, "game", "_test_harness.rpy"))

    for rpyc in _find_rpyc(os.path.join(tmp_project, "game")):
        os.unlink(rpyc)

    ipc = IPC(socket_path)
    ipc.bind_and_listen()

    env = os.environ.copy()
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["RENPY_TEST_SOCKET"] = socket_path
    env["RENPY_TEST_SAVEDIR"] = save_dir
    env["RENPY_LESS_UPDATES"] = "1"
    env["RENPY_SIMPLE_EXCEPTIONS"] = "1"
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    proc = subprocess.Popen(
        [SDK_PYTHON, RENPY_PY, tmp_project],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ipc.accept()
    msg = ipc.recv()
    assert msg["status"] == "ready", f"Expected ready, got {msg}"

    return proc, ipc


def _find_rpyc(game_dir):
    result = []
    for root, dirs, files in os.walk(game_dir):
        for f in files:
            if f.endswith(".rpyc"):
                result.append(os.path.join(root, f))
    return result


def cleanup(proc, ipc):
    try:
        ipc.send({"cmd": "stop"})
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    ipc.close()


def run_test(name, fn):
    print(f"\n{'='*60}")
    print(f"SPIKE: {name}")
    print(f"{'='*60}")
    tmp_dir = tempfile.mkdtemp(prefix="spike_cs_")
    try:
        proc, ipc = launch(tmp_dir)
        try:
            result = fn(ipc)
            print(f"  RESULT: {'PASS' if result else 'FAIL'}")
            return result
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode("utf-8", errors="replace")
                if stderr:
                    print(f"  STDERR:\n{stderr[:2000]}")
            return False
        finally:
            cleanup(proc, ipc)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# --- Spike tests ---

def spike_1_call_with_says(ipc):
    """Call a label with 2 say statements. Log depth at idle, each yield, and after return."""
    baseline = eval_depth(ipc)
    node_at_idle = eval_current_node(ipc)
    print(f"  Baseline depth (idle): {baseline}")
    print(f"  Node at idle: {node_at_idle}")

    ipc.send({"cmd": "call", "label": "call_with_says"})
    resp = ipc.recv()
    print(f"  After call cmd: status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_at_yield1 = eval_depth(ipc)
    node_at_yield1 = eval_current_node(ipc)
    print(f"  Depth at first yield: {depth_at_yield1}")
    print(f"  Node at first yield: {node_at_yield1}")

    # Check store - call_result should be "before" (set before first say)
    ipc.send({"cmd": "get_store", "vars": ["call_result"]})
    store = ipc.recv()
    print(f"  call_result at yield1: {store['values']['call_result']}")

    # Continue past first say
    ipc.send({"cmd": "continue"})
    resp = ipc.recv()
    print(f"  After continue (yield2): status={resp['status']}, yield_type={resp.get('yield_type')}")

    depth_at_yield2 = eval_depth(ipc)
    print(f"  Depth at second yield: {depth_at_yield2}")

    # Continue past second say — label should return, landing back in _harness_idle
    ipc.send({"cmd": "continue"})
    resp = ipc.recv()
    print(f"  After continue (post-return): status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_after_return = eval_depth(ipc)
    node_after_return = eval_current_node(ipc)
    print(f"  Depth after return: {depth_after_return}")
    print(f"  Node after return: {node_after_return}")

    # Check store - call_result should be "after"
    ipc.send({"cmd": "get_store", "vars": ["call_result"]})
    store = ipc.recv()
    print(f"  call_result after return: {store['values']['call_result']}")

    print(f"\n  SUMMARY:")
    print(f"    Baseline depth: {baseline}")
    print(f"    Depth inside call: {depth_at_yield1} (delta: +{depth_at_yield1 - baseline})")
    print(f"    Depth after return: {depth_after_return} (delta: {depth_after_return - baseline})")
    print(f"    _harness_idle re-entered: {node_after_return == node_at_idle or '_harness_idle' in str(node_after_return)}")

    return (
        depth_at_yield1 > baseline
        and depth_at_yield2 == depth_at_yield1
        and store['values']['call_result'] == "after"
    )


def spike_2_nested_call(ipc):
    """Call a label that itself calls another label. Log depth at each level."""
    baseline = eval_depth(ipc)
    print(f"  Baseline depth: {baseline}")

    ipc.send({"cmd": "call", "label": "call_nested"})
    resp = ipc.recv()
    print(f"  After call: status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_outer = eval_depth(ipc)
    print(f"  Depth in outer label (before nested call): {depth_outer} (delta: +{depth_outer - baseline})")

    # Continue past outer say — this should enter the inner call
    ipc.send({"cmd": "continue"})
    resp = ipc.recv()
    print(f"  After continue (inner call): status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_inner = eval_depth(ipc)
    print(f"  Depth in inner label: {depth_inner} (delta: +{depth_inner - baseline})")

    # Continue past inner say — inner label returns, outer label continues
    ipc.send({"cmd": "continue"})
    resp = ipc.recv()
    print(f"  After inner return: status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    # Check: did we actually get back to... somewhere? Need to figure out where.
    # After inner return, outer label sets call_result = "outer_done" and returns.
    # But wait — after inner return, there's no more yields in outer. So outer returns immediately.
    # That means _harness_idle re-enters and we should see a yield from there.

    depth_after = eval_depth(ipc)
    print(f"  Depth after all returns: {depth_after}")

    ipc.send({"cmd": "get_store", "vars": ["call_result", "inner_result"]})
    store = ipc.recv()
    print(f"  call_result: {store['values']['call_result']}")
    print(f"  inner_result: {store['values']['inner_result']}")

    print(f"\n  SUMMARY:")
    print(f"    Baseline: {baseline}")
    print(f"    Outer call depth: {depth_outer} (+{depth_outer - baseline})")
    print(f"    Inner call depth: {depth_inner} (+{depth_inner - baseline})")
    print(f"    After all returns: {depth_after}")

    return (
        depth_outer > baseline
        and depth_inner > depth_outer
        and store['values']['inner_result'] == "inner_done"
        and store['values']['call_result'] == "outer_done"
    )


def spike_3_call_with_jump(ipc):
    """Call a label that jumps instead of returning. Log depth at jump target."""
    baseline = eval_depth(ipc)
    print(f"  Baseline depth: {baseline}")

    ipc.send({"cmd": "call", "label": "call_with_jump"})
    resp = ipc.recv()
    print(f"  After call: status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_in_call = eval_depth(ipc)
    print(f"  Depth inside called label: {depth_in_call} (delta: +{depth_in_call - baseline})")

    # Continue past say — label jumps to jump_target
    ipc.send({"cmd": "continue"})
    resp = ipc.recv()
    print(f"  After jump: status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_at_target = eval_depth(ipc)
    print(f"  Depth at jump target: {depth_at_target} (delta: {depth_at_target - baseline:+d})")

    ipc.send({"cmd": "get_store", "vars": ["call_result"]})
    store = ipc.recv()
    print(f"  call_result: {store['values']['call_result']}")

    print(f"\n  SUMMARY:")
    print(f"    Baseline: {baseline}")
    print(f"    In called label: {depth_in_call} (+{depth_in_call - baseline})")
    print(f"    At jump target: {depth_at_target} ({depth_at_target - baseline:+d})")
    print(f"    Jump pops call frame: {depth_at_target <= baseline}")

    return depth_at_target <= baseline and store['values']['call_result'] == "jumped"


def spike_4_exec_triggered_call(ipc):
    """exec_code that triggers renpy.call(). Log depth."""
    baseline = eval_depth(ipc)
    print(f"  Baseline depth: {baseline}")

    ipc.send({"cmd": "exec", "code": "trigger_call()"})
    resp = ipc.recv()
    print(f"  After exec: status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    if resp.get("status") == "error":
        print(f"  ERROR: {resp.get('message')}")
        return False

    depth_in_exec_call = eval_depth(ipc)
    print(f"  Depth inside exec-triggered call: {depth_in_exec_call} (delta: +{depth_in_exec_call - baseline})")

    # Continue past say — label returns
    ipc.send({"cmd": "continue"})
    resp = ipc.recv()
    print(f"  After return: status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_after = eval_depth(ipc)
    print(f"  Depth after return: {depth_after}")

    ipc.send({"cmd": "get_store", "vars": ["exec_result"]})
    store = ipc.recv()
    print(f"  exec_result: {store['values']['exec_result']}")

    print(f"\n  SUMMARY:")
    print(f"    Baseline: {baseline}")
    print(f"    In exec-triggered call: {depth_in_exec_call} (+{depth_in_exec_call - baseline})")
    print(f"    After return: {depth_after}")

    return store['values']['exec_result'] == "exec_call_done"


def spike_5_duplicate_label(ipc):
    """Check if the engine booted successfully — duplicate label start: is in both
    harness and script.rpy. If we got here, it didn't crash."""
    # The fixture game defines label start:. The harness also has label splashscreen:.
    # We test if Ren'Py allows a second label start: by modifying the test harness.
    # But actually, we can just eval to check if the label exists.
    ipc.send({"cmd": "eval", "expr": "'start' in renpy.game.script.namemap"})
    resp = ipc.recv()
    print(f"  'start' in namemap: {resp.get('result')}")

    # Check what node start points to
    ipc.send({"cmd": "eval", "expr": "str(renpy.game.script.namemap.get('start', 'MISSING'))"})
    resp = ipc.recv()
    print(f"  start label node: {resp.get('result')}")

    print(f"\n  NOTE: Duplicate label test requires a separate run with modified harness.")
    print(f"  Engine booted fine with fixture game's label start: — no harness conflict yet.")
    return True


def spike_6_call_no_yields(ipc):
    """Call a label with no yields. Does _harness_idle re-enter immediately?"""
    baseline = eval_depth(ipc)
    print(f"  Baseline depth: {baseline}")

    ipc.send({"cmd": "call", "label": "call_no_yields"})
    resp = ipc.recv()
    print(f"  After call (no yields): status={resp['status']}, yield_type={resp.get('yield_type')}, at_label={resp.get('at_label')}")

    depth_after = eval_depth(ipc)
    print(f"  Depth after return: {depth_after}")

    ipc.send({"cmd": "get_store", "vars": ["call_result"]})
    store = ipc.recv()
    print(f"  call_result: {store['values']['call_result']}")

    print(f"\n  SUMMARY:")
    print(f"    Baseline: {baseline}")
    print(f"    After no-yield call return: {depth_after}")
    print(f"    Immediate re-entry: {resp['status'] in ('yielded', 'ready')}")

    return store['values']['call_result'] == "no_yield_done"


def spike_7_duplicate_start_label(ipc):
    """This spike needs a modified harness with 'label start:'. Skipped in basic run.
    See run_duplicate_label_spike() below."""
    print("  SKIPPED — requires modified harness. Run with --duplicate-label flag.")
    return True


def run_duplicate_label_spike():
    """Separate test: create a harness with 'label start:' and boot with fixture game."""
    print(f"\n{'='*60}")
    print("SPIKE: Duplicate label start: behavior")
    print(f"{'='*60}")

    tmp_dir = tempfile.mkdtemp(prefix="spike_dup_")
    try:
        harness_src = os.path.join(
            os.path.dirname(__file__), "..", "src", "pytest_renpy", "engine", "_test_harness.rpy"
        )
        modified_harness = os.path.join(tmp_dir, "_test_harness.rpy")

        with open(harness_src) as f:
            content = f.read()

        # Add a label start: to the harness
        content += """
label start:
    python:
        if _harness_connected:
            pass
    if _harness_connected:
        call _harness_idle
    return
"""
        with open(modified_harness, "w") as f:
            f.write(content)

        socket_path = os.path.join(tmp_dir, "test.sock")
        save_dir = os.path.join(tmp_dir, "saves")
        os.makedirs(save_dir, exist_ok=True)

        tmp_project = os.path.join(tmp_dir, "project")
        game_src = os.path.join(FIXTURE_GAME, "game")
        shutil.copytree(game_src, os.path.join(tmp_project, "game"), symlinks=True)
        shutil.copy2(modified_harness, os.path.join(tmp_project, "game", "_test_harness.rpy"))

        for rpyc in _find_rpyc(os.path.join(tmp_project, "game")):
            os.unlink(rpyc)

        ipc_obj = IPC(socket_path)
        ipc_obj.bind_and_listen()

        env = os.environ.copy()
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
        env["RENPY_TEST_SOCKET"] = socket_path
        env["RENPY_TEST_SAVEDIR"] = save_dir
        env["RENPY_LESS_UPDATES"] = "1"
        env["RENPY_SIMPLE_EXCEPTIONS"] = "1"
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)

        proc = subprocess.Popen(
            [SDK_PYTHON, RENPY_PY, tmp_project],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            ipc_obj.sock.settimeout(15)
            ipc_obj.accept()
            msg = ipc_obj.recv()

            if msg["status"] == "ready":
                print("  Engine booted WITH duplicate label start: — NO ERROR!")
                print("  Ren'Py allows duplicate labels (last definition wins).")

                # Check which start label is active
                ipc_obj.send({"cmd": "eval", "expr": "str(renpy.game.script.namemap.get('start'))"})
                resp = ipc_obj.recv()
                print(f"  start label node: {resp.get('result')}")

                result = True
            else:
                print(f"  Unexpected status: {msg}")
                result = False

        except Exception as e:
            stderr = ""
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode("utf-8", errors="replace")
            print(f"  Engine FAILED to boot: {e}")
            if stderr:
                # Check if it's a duplicate label error
                if "duplicate label" in stderr.lower() or "already defined" in stderr.lower():
                    print("  Ren'Py ERRORS on duplicate labels!")
                    print(f"  Error: {stderr[:500]}")
                else:
                    print(f"  STDERR: {stderr[:500]}")
            result = False

        finally:
            try:
                ipc_obj.send({"cmd": "stop"})
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            ipc_obj.close()

        print(f"  RESULT: {'PASS' if result else 'FAIL'}")
        return result

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    results = {}

    tests = [
        ("1. Call + 2 says — depth tracking", spike_1_call_with_says),
        ("2. Nested call — depth at each level", spike_2_nested_call),
        ("3. Call + jump — depth at jump target", spike_3_call_with_jump),
        ("4. exec-triggered call — depth tracking", spike_4_exec_triggered_call),
        ("5. Label namespace check", spike_5_duplicate_label),
        ("6. Call with no yields — immediate re-entry", spike_6_call_no_yields),
    ]

    for name, fn in tests:
        results[name] = run_test(name, fn)

    # Run duplicate label test
    if "--duplicate-label" in sys.argv or "--all" in sys.argv:
        results["7. Duplicate label start:"] = run_duplicate_label_spike()

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
