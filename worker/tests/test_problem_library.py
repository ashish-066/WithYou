"""Every seeded coding problem must be solvable as packaged.

Runs each reference solution through the real sandbox executor against all of its
public and hidden tests, so test sizes, the output cap and the exact-text
comparison are checked the way a candidate's run is.
"""

import pytest

from dsa.seed_problems import ALL_PROBLEMS
from sandbox.executor import execute_candidate_code


@pytest.mark.parametrize("problem", ALL_PROBLEMS, ids=lambda p: p.problem_id)
async def test_reference_solution_passes_every_test(problem):
    tests = problem.public_test_cases + problem.hidden_test_cases
    result = await execute_candidate_code(problem.reference_solution.code, tests, run_hidden=True)
    failed = [
        (r.description, (r.error or r.actual_output)[:200])
        for r in result.test_results
        if not r.passed
    ]
    assert result.tests_passed == len(tests), failed


def test_problem_ids_are_unique_and_tests_exist():
    ids = [p.problem_id for p in ALL_PROBLEMS]
    assert len(ids) == len(set(ids))
    for p in ALL_PROBLEMS:
        assert p.public_test_cases and p.hidden_test_cases, p.problem_id
        assert all(t.is_hidden for t in p.hidden_test_cases), p.problem_id
        assert not any(t.is_hidden for t in p.public_test_cases), p.problem_id
