"""Python code execution sandbox for DSA interviews.

Candidate code is untrusted. Two runners, picked by SANDBOX_MODE:

  docker (required in production)
    Every test case runs in its own throwaway container:
      - no network (--network none): cannot reach Redis, the API, or the internet
      - no host files: code arrives on stdin, nothing is mounted; read-only root
        filesystem with a small /tmp
      - unprivileged: nobody user, all capabilities dropped, no-new-privileges
      - limits: memory (no swap), CPU, process count, open files, file size
      - wall-clock timeout inside the container, plus a forced `docker rm -f`
        if the container does not exit in time
    Optional SANDBOX_RUNTIME (e.g. gVisor "runsc") adds a kernel boundary.

  subprocess (development only — NOT isolated)
    Plain local process with a sanitized environment. It can read the host
    filesystem and reach the network; the worker refuses this mode when
    ENVIRONMENT=production.

Both runners share: output capped while streaming (a flood of prints cannot
exhaust worker memory), runtime measured inside the harness around the
solution call only, and a bounded number of concurrent runs per worker.

Only Python is supported. The executor's ExecutionResult is the authoritative
source of truth for code correctness — the LLM must never contradict it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import textwrap
import time
import uuid
import weakref
from dataclasses import dataclass

from core.config import settings
from dsa.models import ExecutionResult, TestCase, TestCaseResult

logger = logging.getLogger(__name__)

# Hard limits
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MEMORY_LIMIT_MB = 128
MAX_OUTPUT_BYTES = 10 * 1024  # 10 KB per test case, per stream

RUNTIME_MARKER = "__RUNTIME_MS__="
NOT_RUN_ERROR = "Not run (previous test timed out)"
SANDBOX_UNAVAILABLE_ERROR = "Code runner unavailable"


# =============================================================================
# Code wrapper template
# =============================================================================

# The candidate writes a solution function/class. We wrap it in a test harness
# that reads input from stdin and writes the result to stdout. The harness
# reports how long the solution call took on stderr (RUNTIME_MARKER), so
# interpreter/container start-up is not counted as the candidate's runtime.
# (Literal braces are doubled: the template goes through str.format.)

_TEST_HARNESS_TEMPLATE = textwrap.dedent(
    """\
    import sys
    import json
    import traceback
    import time as _harness_time

    # ---- candidate code starts ----
    {candidate_code}
    # ---- candidate code ends ----

    def _run_test(raw_input):
        \"\"\"Execute the candidate's solution with the given input.\"\"\"
        # The harness calls `solution(...)` as the entry point.
        # Input is a JSON-encoded list of positional arguments.
        args = json.loads(raw_input)
        if isinstance(args, list):
            result = solution(*args)
        else:
            result = solution(args)
        return json.dumps(result, default=str)

    if __name__ == "__main__":
        raw = sys.stdin.read().strip()
        try:
            _t0 = _harness_time.perf_counter()
            output = _run_test(raw)
            _elapsed_ms = (_harness_time.perf_counter() - _t0) * 1000
            print(output)
            print("{runtime_marker}%.3f" % _elapsed_ms, file=sys.stderr)
        except Exception:
            print("__ERROR__", traceback.format_exc(), file=sys.stderr)
            sys.exit(1)
    """
)

# Runs inside the sandbox process: stdin carries {"script": ..., "input": ...};
# the wrapped script is executed as __main__ with the test input as its stdin.
# Passing code on stdin means no host directory has to be mounted.
_BOOTSTRAP = (
    "import io,json,sys\n"
    "_e=json.loads(sys.stdin.read())\n"
    "sys.stdin=io.StringIO(_e['input'])\n"
    "exec(compile(_e['script'],'solution.py','exec'),{'__name__':'__main__','__file__':'solution.py'})\n"
)


# =============================================================================
# Process plumbing
# =============================================================================


class SandboxUnavailableError(Exception):
    """The code runner itself failed (e.g. Docker daemon not running)."""


@dataclass
class _ProcessOutcome:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    wall_ms: float


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> bytes:
    """Read a stream to EOF, keeping only the first `limit` bytes."""
    buf = bytearray()
    while chunk := await stream.read(65536):
        if len(buf) < limit:
            buf += chunk[: limit - len(buf)]
    return bytes(buf)


async def _run_process(
    cmd: list[str],
    stdin_data: bytes,
    env: dict[str, str],
    timeout: float,
    on_timeout,
) -> _ProcessOutcome:
    """Run a command with stdin, capped output and a hard timeout."""
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        # start_new_session isolates the process group so we can kill it
        start_new_session=True,
    )

    async def feed() -> None:
        try:
            proc.stdin.write(stdin_data)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass  # process exited before reading all input
        finally:
            proc.stdin.close()

    async def communicate() -> tuple[bytes, bytes]:
        _, out, err, _ = await asyncio.gather(
            feed(),
            _read_capped(proc.stdout, MAX_OUTPUT_BYTES),
            _read_capped(proc.stderr, MAX_OUTPUT_BYTES),
            proc.wait(),
        )
        return out, err

    try:
        stdout, stderr = await asyncio.wait_for(communicate(), timeout=timeout)
        return _ProcessOutcome(
            proc.returncode, stdout, stderr, False, (time.monotonic() - start) * 1000
        )
    except asyncio.TimeoutError:
        await on_timeout(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            logger.error(f"Sandbox process {proc.pid} did not exit after kill")
        return _ProcessOutcome(None, b"", b"", True, (time.monotonic() - start) * 1000)


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


# =============================================================================
# Runners
# =============================================================================


class SubprocessRunner:
    """Local process with a sanitized environment. Development only: NOT isolated."""

    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds

    def _safe_env(self) -> dict[str, str]:
        """Minimal environment: no API keys, Redis URLs or other parent variables."""
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "PYTHONPATH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }

    async def run(self, envelope: bytes) -> _ProcessOutcome:
        async def on_timeout(proc):
            _kill_group(proc)

        return await _run_process(
            [sys.executable, "-I", "-c", _BOOTSTRAP],
            envelope,
            self._safe_env(),
            self.timeout_seconds,
            on_timeout,
        )


class DockerRunner:
    """Throwaway, locked-down container per test case."""

    # `timeout` exit status when the time limit is hit
    TIMEOUT_EXIT = 124
    # Docker's own failures (daemon down, image missing, bad flags)
    DOCKER_ERROR_EXITS = (125, 126, 127)

    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds

    def command(self, name: str) -> list[str]:
        mem = f"{settings.sandbox_memory_mb}m"
        cmd = [
            "docker", "run", "--rm", "-i",
            "--name", name,
            "--label", "alex.sandbox=1",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", mem,
            "--memory-swap", mem,
            "--cpus", str(settings.sandbox_cpus),
            "--pids-limit", str(settings.sandbox_pids_limit),
            "--ulimit", "nofile=64:64",
            "--ulimit", "fsize=1048576:1048576",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "PYTHONUNBUFFERED=1",
        ]
        if settings.sandbox_runtime:
            cmd += ["--runtime", settings.sandbox_runtime]
        cmd += [
            settings.sandbox_image,
            "timeout", "-k", "1", f"{self.timeout_seconds:g}",
            "python", "-I", "-c", _BOOTSTRAP,
        ]
        return cmd

    async def run(self, envelope: bytes) -> _ProcessOutcome:
        name = f"alex-sbx-{uuid.uuid4().hex[:12]}"

        async def on_timeout(proc):
            # Killing the docker client does not stop the container: remove it
            rm = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await rm.wait()
            _kill_group(proc)

        try:
            outcome = await _run_process(
                self.command(name),
                envelope,
                # The docker CLI is trusted and needs its own config (context,
                # DOCKER_HOST); the container only gets the -e vars above.
                dict(os.environ),
                self.timeout_seconds + settings.sandbox_startup_grace_seconds,
                on_timeout,
            )
        except FileNotFoundError as e:
            raise SandboxUnavailableError("docker CLI not found") from e

        if outcome.returncode in self.DOCKER_ERROR_EXITS and b"docker" in outcome.stderr.lower():
            raise SandboxUnavailableError(outcome.stderr.decode(errors="replace").strip()[:300])
        if outcome.returncode == self.TIMEOUT_EXIT:
            outcome.timed_out = True
        elif outcome.returncode == 137 and outcome.wall_ms >= self.timeout_seconds * 1000:
            # SIGTERM was ignored, so `timeout -k` sent SIGKILL: still a timeout,
            # not the memory limit (which also exits 137, but early)
            outcome.timed_out = True
        return outcome


# Concurrent sandbox runs per worker process (one semaphore per event loop)
_semaphores: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _concurrency_limit() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(settings.sandbox_max_concurrency)
        _semaphores[loop] = sem
    return sem


# =============================================================================
# Executor
# =============================================================================


def _split_runtime(stderr: str) -> tuple[str, float | None]:
    """Remove the harness's runtime marker from stderr and return its value."""
    runtime = None
    kept = []
    for line in stderr.splitlines():
        if line.startswith(RUNTIME_MARKER):
            try:
                runtime = float(line[len(RUNTIME_MARKER):])
            except ValueError:
                kept.append(line)
        else:
            kept.append(line)
    return "\n".join(kept).strip(), runtime


async def ensure_sandbox_image(pull_timeout: float = 600) -> bool:
    """Make sure the docker sandbox image is on the daemon, pulling it if not.

    Run at worker start-up: `docker run` would otherwise pull on a candidate's
    first run, which can take longer than the run's time limit.
    """

    async def docker(*args: str, timeout: float, log_failure: bool = True) -> int:
        proc = await asyncio.create_subprocess_exec(
            "docker", *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error(f"docker {args[0]} timed out after {timeout:g}s")
            return -1
        if proc.returncode and log_failure:
            logger.warning(f"docker {' '.join(args)}: {err.decode(errors='replace').strip()[:300]}")
        return proc.returncode

    image = settings.sandbox_image
    try:
        # a missing image is expected on a fresh daemon: no warning
        if await docker("image", "inspect", image, timeout=30, log_failure=False) == 0:
            return True
        logger.info(f"Pulling sandbox image {image}")
        return await docker("pull", image, timeout=pull_timeout) == 0
    except FileNotFoundError:
        logger.error("docker CLI not found; code runs will report the sandbox as unavailable")
        return False


class CodeExecutor:
    """Runs candidate Python code against test cases in the configured sandbox.

    Usage:
        executor = CodeExecutor()
        result = await executor.run(code, test_cases)
    """

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
        mode: str | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.memory_limit_mb = memory_limit_mb
        self.mode = mode or settings.sandbox_mode
        if self.mode == "docker":
            self.runner = DockerRunner(timeout_seconds)
        elif self.mode == "subprocess":
            if settings.environment == "production":
                raise RuntimeError("Unisolated subprocess sandbox is not allowed in production")
            self.runner = SubprocessRunner(timeout_seconds)
        else:
            raise ValueError(f"Unknown sandbox mode {self.mode!r}")

    # -------------------------------------------------------------------------
    # Single test case execution
    # -------------------------------------------------------------------------

    async def _run_single_test(
        self,
        script: str,
        test_case: TestCase,
        test_index: int,
    ) -> TestCaseResult:
        """Run a single test case and return its result."""

        def result(**kwargs) -> TestCaseResult:
            return TestCaseResult(
                test_index=test_index,
                description=test_case.description,
                input=test_case.input,
                expected_output=test_case.expected_output,
                **kwargs,
            )

        envelope = json.dumps({"script": script, "input": test_case.input}).encode()
        async with _concurrency_limit():
            outcome = await self.runner.run(envelope)

        if outcome.timed_out:
            return result(
                passed=False,
                actual_output="",
                error=f"Timeout after {self.timeout_seconds}s",
                runtime_ms=outcome.wall_ms,
            )

        raw_stdout = outcome.stdout.decode(errors="replace").strip()
        raw_stderr, harness_ms = _split_runtime(outcome.stderr.decode(errors="replace"))
        runtime_ms = harness_ms if harness_ms is not None else outcome.wall_ms

        # Check for runtime error
        if outcome.returncode != 0 or "__ERROR__" in raw_stderr:
            error = raw_stderr or "Non-zero exit code"
            if outcome.returncode == 137 and not raw_stderr:
                error = "Killed (memory limit exceeded)"
            return result(passed=False, actual_output=raw_stdout, error=error, runtime_ms=runtime_ms)

        passed = raw_stdout.strip() == test_case.expected_output.strip()
        return result(passed=passed, actual_output=raw_stdout, runtime_ms=runtime_ms)

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------

    async def run(
        self,
        code: str,
        test_cases: list[TestCase],
        code_version: int = 1,
        run_hidden: bool = False,
    ) -> ExecutionResult:
        """Execute candidate Python code against test cases.

        Args:
            code: Candidate's Python source code
            test_cases: List of TestCase objects to run
            code_version: Monotonic version counter (for tracking code edits)
            run_hidden: If True, include hidden test cases in the run

        Returns:
            ExecutionResult — the authoritative source of truth for correctness.
            The LLM must never contradict or ignore this result.
        """
        if not test_cases:
            return ExecutionResult(
                success=True,
                tests_passed=0,
                tests_total=0,
                pass_rate=0.0,
                code_version=code_version,
            )

        # Filter test cases
        cases_to_run = test_cases if run_hidden else [
            tc for tc in test_cases if not tc.is_hidden
        ]

        try:
            # Check for syntax errors first (fast, no sandbox needed)
            try:
                compile(code, "<candidate_code>", "exec")
            except SyntaxError as e:
                return ExecutionResult(
                    success=False,
                    compilation_error=str(e),
                    tests_passed=0,
                    tests_total=len(cases_to_run),
                    pass_rate=0.0,
                    code_version=code_version,
                )

            script = _TEST_HARNESS_TEMPLATE.format(
                candidate_code=code, runtime_marker=RUNTIME_MARKER
            )

            # Test cases are independent: run them concurrently (bounded)
            results = list(
                await asyncio.gather(
                    *(self._run_single_test(script, tc, i) for i, tc in enumerate(cases_to_run))
                )
            )

            # Same reporting as sequential runs: after the first timeout, the
            # remaining tests count as not run
            test_results: list[TestCaseResult] = []
            timed_out = False
            total_runtime_ms = 0.0
            for i, r in enumerate(results):
                if timed_out:
                    test_results.append(
                        TestCaseResult(
                            test_index=i,
                            description=cases_to_run[i].description,
                            passed=False,
                            input=cases_to_run[i].input,
                            expected_output=cases_to_run[i].expected_output,
                            actual_output="",
                            error=NOT_RUN_ERROR,
                        )
                    )
                    continue
                test_results.append(r)
                total_runtime_ms += r.runtime_ms
                if "Timeout" in r.error:
                    timed_out = True

            tests_passed = sum(1 for r in test_results if r.passed)
            tests_total = len(test_results)
            pass_rate = tests_passed / tests_total if tests_total > 0 else 0.0

            # Check if any had runtime errors
            runtime_errors = [
                r.error for r in test_results
                if r.error and "Timeout" not in r.error and r.error != NOT_RUN_ERROR
            ]
            runtime_error = runtime_errors[0] if runtime_errors else ""

            return ExecutionResult(
                success=not timed_out and not runtime_error,
                timed_out=timed_out,
                timeout_seconds=self.timeout_seconds,
                runtime_error=runtime_error,
                test_results=test_results,
                tests_passed=tests_passed,
                tests_total=tests_total,
                pass_rate=pass_rate,
                total_runtime_ms=total_runtime_ms,
                code_version=code_version,
            )

        except SandboxUnavailableError as e:
            logger.error(f"Sandbox unavailable: {e}")
            return ExecutionResult(
                success=False,
                sandbox_unavailable=True,
                runtime_error=SANDBOX_UNAVAILABLE_ERROR,
                tests_passed=0,
                tests_total=len(cases_to_run),
                pass_rate=0.0,
                code_version=code_version,
            )

        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return ExecutionResult(
                success=False,
                runtime_error=str(e),
                tests_passed=0,
                tests_total=len(cases_to_run),
                pass_rate=0.0,
                code_version=code_version,
            )


# =============================================================================
# Module-level convenience function
# =============================================================================


async def execute_candidate_code(
    code: str,
    test_cases: list[TestCase],
    code_version: int = 1,
    run_hidden: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ExecutionResult:
    """Execute candidate Python code. Module-level convenience wrapper."""
    executor = CodeExecutor(timeout_seconds=timeout_seconds)
    return await executor.run(
        code=code,
        test_cases=test_cases,
        code_version=code_version,
        run_hidden=run_hidden,
    )
