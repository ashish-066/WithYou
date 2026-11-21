"""Sandbox self-check, run by the deploy script after the worker starts.

    python -m sandbox.selfcheck

Exit 0 when the configured sandbox runs a known-good solution correctly and
the code inside it cannot open a network connection. Anything else exits 1,
and the deploy rolls back.
"""

import asyncio
import sys

from dsa.models import TestCase
from sandbox.executor import CodeExecutor

CASE = [TestCase(input="[1, 2]", expected_output="3", description="selfcheck")]

ADD = "def solution(a, b):\n    return a + b\n"

# Returns the right answer only if the connection attempt fails
NETWORK_PROBE = """
def solution(a, b):
    import socket
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        return "network reachable"
    except OSError:
        return a + b
"""


async def check() -> list[str]:
    executor = CodeExecutor(timeout_seconds=10)
    problems = []
    for name, code in (("known-good solution", ADD), ("network probe", NETWORK_PROBE)):
        result = await executor.run(code, CASE)
        if result.tests_passed != result.tests_total:
            detail = result.compilation_error or result.runtime_error or [
                (t.actual_output, t.error) for t in result.test_results
            ]
            problems.append(f"{name} failed: {detail}")
    return problems


def main() -> int:
    problems = asyncio.run(check())
    for p in problems:
        print(f"sandbox selfcheck: {p}", file=sys.stderr)
    print("sandbox selfcheck: " + ("FAILED" if problems else "ok"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
