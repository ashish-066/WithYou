"""DSA code sandbox: correctness in both modes, isolation in docker mode.

Docker tests run only when a Docker daemon is reachable and the sandbox image
is present (`docker pull python:3.12-slim`); otherwise they are skipped.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from core.config import settings
from dsa.models import TestCase
from sandbox.executor import CodeExecutor

ADD = "def solution(a, b):\n    return a + b\n"
CASES = [
    TestCase(input="[1, 2]", expected_output="3", description="small"),
    TestCase(input="[-5, 5]", expected_output="0", description="zero"),
    TestCase(input="[10, 20]", expected_output="30", description="tens"),
]


def docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(
            ["docker", "image", "inspect", settings.sandbox_image],
            check=True, capture_output=True, timeout=15,
        )
        return True
    except Exception:
        return False


MODES = ["subprocess", pytest.param("docker", marks=pytest.mark.skipif(
    not docker_ready(), reason="Docker daemon or sandbox image not available"))]
needs_docker = pytest.mark.skipif(not docker_ready(), reason="Docker not available")


async def run(code, cases=CASES, mode="docker", timeout=3.0):
    return await CodeExecutor(timeout_seconds=timeout, mode=mode).run(code, cases)


# --------------------------------------------------------------------------
# Correctness (both modes)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
async def test_correct_solution_passes(mode):
    r = await run(ADD, mode=mode)

    assert r.success and r.tests_passed == 3 and r.tests_total == 3
    assert all(t.runtime_ms < 1000 for t in r.test_results)  # harness-measured, not start-up


@pytest.mark.parametrize("mode", MODES)
async def test_wrong_answer_fails(mode):
    r = await run("def solution(a, b):\n    return a - b\n", mode=mode)

    # ran fine (success = no crash/timeout) but every answer is wrong
    assert r.success and r.tests_passed == 0
    assert r.test_results[0].actual_output == "-1"


@pytest.mark.parametrize("mode", MODES)
async def test_exception_reported(mode):
    r = await run("def solution(a, b):\n    raise ValueError('boom')\n", mode=mode)

    assert not r.success and "ValueError" in r.runtime_error


@pytest.mark.parametrize("mode", MODES)
async def test_syntax_error(mode):
    r = await run("def solution(a, b)\n    return a\n", mode=mode)

    assert r.compilation_error and r.tests_passed == 0


@pytest.mark.parametrize("mode", MODES)
async def test_timeout_marks_rest_not_run(mode):
    r = await run("def solution(a, b):\n    while True: pass\n", mode=mode, timeout=1.0)

    assert r.timed_out and not r.success
    assert "Timeout" in r.test_results[0].error
    assert all(t.error.startswith("Not run") for t in r.test_results[1:])


@pytest.mark.parametrize("mode", MODES)
async def test_output_flood_is_capped(mode):
    code = "def solution(a, b):\n    print('x' * 50_000_000)\n    return a + b\n"
    r = await run(code, cases=CASES[:1], mode=mode, timeout=10.0)

    assert len(r.test_results[0].actual_output) <= 10 * 1024


@pytest.mark.parametrize("mode", MODES)
async def test_braces_and_marker_in_candidate_code(mode):
    code = (
        "def solution(a, b):\n"
        "    d = {'k': [a, b]}\n"
        "    return sum(d['k'])\n"
    )
    r = await run(code, mode=mode)

    assert r.tests_passed == 3


def test_subprocess_mode_refused_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")

    with pytest.raises(RuntimeError):
        CodeExecutor(mode="subprocess")


# --------------------------------------------------------------------------
# Isolation (docker only): each must fail safely and not affect the worker
# --------------------------------------------------------------------------

PROBE = TestCase(input="[0, 0]", expected_output="SAFE", description="probe")


async def probe(body: str, timeout: float = 5.0):
    code = "def solution(a, b):\n" + "".join(f"    {line}\n" for line in body.splitlines())
    r = await run(code, cases=[PROBE], mode="docker", timeout=timeout)
    return r.test_results[0], r


@needs_docker
async def test_cannot_read_host_files():
    worker_dir = str(Path(__file__).resolve().parent.parent)  # e.g. /Users/.../worker
    t, _ = await probe(
        "import os\n"
        f"return [os.path.exists({worker_dir!r}), os.path.exists({worker_dir + '/.env'!r}),"
        " os.path.exists('/Users'), os.listdir('/home')]"
    )
    # the worker's code and .env, and host home folders, are not visible
    assert t.actual_output == "[false, false, false, []]"


@needs_docker
async def test_cannot_read_worker_environment(monkeypatch):
    # The docker CLI gets the worker's environment; the container must not
    monkeypatch.setenv("ALEX_TEST_SECRET", "s3cr3t-value")
    t, _ = await probe(
        "import os\n"
        "return [k for k, v in os.environ.items() if 'ALEX_TEST' in k or 's3cr3t' in v]"
    )
    assert t.actual_output == "[]"


@needs_docker
@pytest.mark.parametrize("target", [("host.docker.internal", 6379), ("127.0.0.1", 6379), ("1.1.1.1", 443)])
async def test_no_network(target):
    host, port = target
    t, _ = await probe(
        "import socket\n"
        "try:\n"
        f"    socket.create_connection(({host!r}, {port}), timeout=2)\n"
        "    return 'CONNECTED'\n"
        "except Exception as e:\n"
        "    return 'BLOCKED'"
    )
    assert t.actual_output == '"BLOCKED"'


@needs_docker
async def test_cannot_write_outside_tmp():
    t, _ = await probe(
        "out = []\n"
        "for p in ['/sandbox_x', '/usr/x', '/tmp/x']:\n"
        "    try:\n"
        "        open(p, 'w').write('x')\n"
        "        out.append(p)\n"
        "    except Exception:\n"
        "        pass\n"
        "return out"
    )
    assert t.actual_output == '["/tmp/x"]'


@needs_docker
async def test_large_file_write_is_limited():
    t, _ = await probe(
        "try:\n"
        "    open('/tmp/big', 'wb').write(b'0' * 50_000_000)\n"
        "    return 'WROTE'\n"
        "except Exception as e:\n"
        "    return 'LIMITED'"
    )
    assert t.actual_output != '"WROTE"'


@needs_docker
async def test_memory_bomb_is_killed():
    t, r = await probe("x = bytearray(2_000_000_000)\nreturn len(x)", timeout=10)

    assert not t.passed and not r.success
    assert t.error  # MemoryError or killed


@needs_docker
async def test_fork_bomb_is_contained():
    t, r = await probe(
        "import os\n"
        "n = 0\n"
        "try:\n"
        "    for _ in range(1000):\n"
        "        if os.fork() == 0:\n"
        "            import time; time.sleep(30)\n"
        "        n += 1\n"
        "except OSError:\n"
        "    return 'LIMITED %d' % n\n"
        "return 'FORKED %d' % n",
        timeout=5,
    )
    assert "LIMITED" in t.actual_output or not r.success


@needs_docker
async def test_runs_as_unprivileged_user():
    t, _ = await probe("import os\nreturn os.getuid()")

    assert t.actual_output == "65534"


@needs_docker
async def test_no_leftover_containers():
    await probe("return 1")
    out = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "label=alex.sandbox=1"],
        capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    assert out == ""


async def test_ensure_image_reports_missing_docker_cli(monkeypatch):
    import asyncio

    from sandbox import executor

    async def no_docker(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", no_docker)
    assert await executor.ensure_sandbox_image() is False


@needs_docker
async def test_ensure_image_finds_present_image():
    from sandbox.executor import ensure_sandbox_image

    assert await ensure_sandbox_image() is True


@needs_docker
def test_selfcheck_passes_with_docker_sandbox(monkeypatch):
    from sandbox import selfcheck

    monkeypatch.setattr(settings, "sandbox_mode", "docker")
    assert selfcheck.main() == 0


def test_selfcheck_fails_when_code_reaches_network(monkeypatch):
    # The subprocess runner isn't isolated: the probe gets out, so the check must fail
    from sandbox import selfcheck

    monkeypatch.setattr(settings, "sandbox_mode", "subprocess")
    monkeypatch.setattr(selfcheck, "NETWORK_PROBE", "def solution(a, b):\n    return 'network reachable'\n")
    assert selfcheck.main() == 1
