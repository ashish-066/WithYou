"""Seed the coding-round problems into Redis.

Run from worker/:
    uv run python -m dsa.seed_problems            # add problems that are missing
    uv run python -m dsa.seed_problems --update   # also overwrite existing ones with this version

The problems besides Two Sum live in dsa/problem_library.py.
"""

import asyncio
import sys

from core.redis import get_redis_client
from dsa.models import (
    AlternativeSolution,
    DSAProblem,
    HintPolicy,
    ReferenceSolution,
    SuboptimalSolution,
    TestCase,
)
from dsa.problem_library import LIBRARY
from dsa.problem_store import DSAProblemStore

TWO_SUM = DSAProblem(
    problem_id="two_sum_001",
    title="Two Sum",
    difficulty="easy",
    tags=["array", "hash_table"],
    statement=(
        "Given a list of integers `nums` and an integer `target`, return the indices of the "
        "two numbers that add up to `target`.\n\n"
        "You may assume each input has exactly one solution, and you may not use the same "
        "element twice. You can return the answer in any order.\n\n"
        "Implement `solution(nums, target)` returning a list of two indices.\n\n"
        "Example: nums = [2, 7, 11, 15], target = 9 -> [0, 1], because nums[0] + nums[1] == 9."
    ),
    constraints=[
        "2 <= len(nums) <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
        "Exactly one valid answer exists",
    ],
    reference_solution=ReferenceSolution(
        algorithm="hash_map",
        time_complexity="O(n)",
        space_complexity="O(n)",
        code=(
            "def solution(nums, target):\n"
            "    seen = {}\n"
            "    for i, x in enumerate(nums):\n"
            "        if target - x in seen:\n"
            "            return [seen[target - x], i]\n"
            "        seen[x] = i\n"
        ),
        explanation="Single pass, store value->index, look up the complement.",
    ),
    acceptable_alternatives=[
        AlternativeSolution(
            algorithm="sort_two_pointers",
            time_complexity="O(n log n)",
            space_complexity="O(n)",
            description="Sort (value, index) pairs and use two pointers.",
        )
    ],
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="brute_force_nested_loops",
            time_complexity="O(n^2)",
            space_complexity="O(1)",
            optimality_gap="O(n^2) vs O(n) optimal",
        )
    ],
    expected_concepts=["hash_map", "complement", "time_space_tradeoff", "one_pass"],
    important_edge_cases=[
        "duplicate values",
        "negative numbers",
        "target made of the same value twice",
    ],
    optimization_prompts=["Can you avoid checking every pair?"],
    public_test_cases=[
        TestCase(input="[[2, 7, 11, 15], 9]", expected_output="[0, 1]", description="basic"),
        TestCase(
            input="[[3, 2, 4], 6]", expected_output="[1, 2]", description="not first elements"
        ),
    ],
    hidden_test_cases=[
        TestCase(
            input="[[3, 3], 6]", expected_output="[0, 1]", is_hidden=True, description="duplicates"
        ),
        TestCase(
            input="[[-1, -2, -3, -4, -5], -8]",
            expected_output="[2, 4]",
            is_hidden=True,
            description="negatives",
        ),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "Think about what you need to find for each number you look at.",
            "How could you remember numbers you've already seen so lookups are fast?",
            "A dictionary mapping value -> index lets you check for the complement in O(1).",
        ],
    ),
)


ALL_PROBLEMS = [TWO_SUM, *LIBRARY]


async def main() -> None:
    update = "--update" in sys.argv[1:]
    redis = await get_redis_client()
    try:
        store = DSAProblemStore(redis)
        for problem in ALL_PROBLEMS:
            if not await store.exists(problem.problem_id):
                await store.create(problem)
                print(f"created  {problem.problem_id}  ({problem.difficulty})")
            elif update:
                await store.update(problem)
                print(f"updated  {problem.problem_id}")
            else:
                print(f"exists   {problem.problem_id}")
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
