"""Coding-round problem library (seeded by dsa/seed_problems.py).

Each problem's expected outputs are computed by running its own reference
solution, so the test cases can't disagree with the reference. The sandbox
compares output as exact text (`json.dumps(result)`), so every problem has
exactly one correct answer per input (ties are broken in the statement).
"""

import copy
import json
from typing import Any

from dsa.models import (
    AlternativeSolution,
    DSAProblem,
    HintPolicy,
    ReferenceSolution,
    SuboptimalSolution,
    TestCase,
)

Case = tuple[list[Any], str]  # (positional arguments, description)


def _cases(code: str, cases: list[Case], hidden: bool) -> list[TestCase]:
    namespace: dict[str, Any] = {}
    exec(code, namespace)  # our own reference solution, not candidate code
    solution = namespace["solution"]
    return [
        TestCase(
            input=json.dumps(args),
            expected_output=json.dumps(solution(*copy.deepcopy(args)), default=str),
            is_hidden=hidden,
            description=description,
        )
        for args, description in cases
    ]


def _problem(
    *, reference: ReferenceSolution, public: list[Case], hidden: list[Case], **fields: Any
) -> DSAProblem:
    return DSAProblem(
        reference_solution=reference,
        public_test_cases=_cases(reference.code, public, hidden=False),
        hidden_test_cases=_cases(reference.code, hidden, hidden=True),
        **fields,
    )


VALID_PARENTHESES = _problem(
    problem_id="valid_parentheses_001",
    title="Valid Parentheses",
    difficulty="easy",
    tags=["string", "stack"],
    statement=(
        "Given a string `s` made only of the characters `()[]{}`, decide whether it is valid.\n\n"
        "A string is valid when every opening bracket is closed by the same kind of bracket, "
        "in the correct order, and every closing bracket has a matching opening bracket.\n\n"
        "Implement `solution(s)` returning `True` or `False`.\n\n"
        'Examples: "()[]{}" -> True, "(]" -> False, "([)]" -> False, "{[]}" -> True.'
    ),
    constraints=["0 <= len(s) <= 10^4", "s contains only ()[]{}"],
    reference=ReferenceSolution(
        algorithm="stack",
        time_complexity="O(n)",
        space_complexity="O(n)",
        code=(
            "def solution(s):\n"
            "    pairs = {')': '(', ']': '[', '}': '{'}\n"
            "    stack = []\n"
            "    for ch in s:\n"
            "        if ch in pairs:\n"
            "            if not stack or stack.pop() != pairs[ch]:\n"
            "                return False\n"
            "        else:\n"
            "            stack.append(ch)\n"
            "    return not stack\n"
        ),
        explanation="Push opening brackets; each closing bracket must match the top of the stack.",
    ),
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="repeated_pair_removal",
            time_complexity="O(n^2)",
            space_complexity="O(n)",
            optimality_gap="Repeatedly deleting '()', '[]', '{}' is O(n^2) vs O(n) with a stack",
        )
    ],
    expected_concepts=["stack", "last_in_first_out", "matching_pairs"],
    important_edge_cases=[
        "empty string",
        "only opening brackets",
        "closing bracket first",
        "interleaved kinds like ([)]",
    ],
    follow_up_questions=["What would change if other characters could appear in the string?"],
    optimization_prompts=["Can you check validity in a single pass?"],
    public=[(["()[]{}"], "all kinds, in order"), (["(]"], "wrong kind"), (["{[]}"], "nested")],
    hidden=[
        ([""], "empty string is valid"),
        (["(("], "never closed"),
        (["))"], "closing first"),
        (["([)]"], "interleaved"),
        (["{[()()]}" * 500], "long and valid"),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "Which bracket must the next closing bracket match?",
            "You need to remember the opening brackets in the order they appeared, most recent first.",
            "A stack: push openers, and pop when you see a closer.",
        ],
    ),
)


BEST_TIME_STOCK = _problem(
    problem_id="best_time_stock_001",
    title="Best Time to Buy and Sell Stock",
    difficulty="easy",
    tags=["array", "greedy"],
    statement=(
        "You are given a list `prices` where `prices[i]` is a stock's price on day `i`.\n\n"
        "Choose one day to buy and a later day to sell. Return the largest profit you can make. "
        "If no profit is possible, return 0.\n\n"
        "Implement `solution(prices)` returning an integer.\n\n"
        "Example: prices = [7, 1, 5, 3, 6, 4] -> 5 (buy at 1, sell at 6)."
    ),
    constraints=["1 <= len(prices) <= 10^5", "0 <= prices[i] <= 10^4"],
    reference=ReferenceSolution(
        algorithm="running_minimum",
        time_complexity="O(n)",
        space_complexity="O(1)",
        code=(
            "def solution(prices):\n"
            "    best, low = 0, float('inf')\n"
            "    for p in prices:\n"
            "        low = min(low, p)\n"
            "        best = max(best, p - low)\n"
            "    return best\n"
        ),
        explanation="Track the lowest price so far; the best sale today is today's price minus that.",
    ),
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="all_pairs",
            time_complexity="O(n^2)",
            space_complexity="O(1)",
            optimality_gap="Checking every buy/sell pair is O(n^2) vs O(n)",
        )
    ],
    expected_concepts=["running_minimum", "single_pass", "greedy"],
    important_edge_cases=["prices only fall", "single day", "best buy is after the global maximum"],
    follow_up_questions=["What if you could buy and sell as many times as you like?"],
    optimization_prompts=["Do you need to compare every pair of days?"],
    public=[([[7, 1, 5, 3, 6, 4]], "basic"), ([[7, 6, 4, 3, 1]], "no profit possible")],
    hidden=[
        ([[5]], "single day"),
        ([[2, 4, 1]], "minimum comes after the peak"),
        ([[3, 3, 3]], "flat"),
        ([[i % 97 for i in range(20000)]], "long repeating pattern"),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "For a given selling day, which buying day is best?",
            "What do you need to remember about the days before today?",
            "Keep the lowest price seen so far and compare today's price against it.",
        ],
    ),
)


LONGEST_UNIQUE_SUBSTRING = _problem(
    problem_id="longest_unique_substring_001",
    title="Longest Substring Without Repeating Characters",
    difficulty="medium",
    tags=["string", "sliding_window", "hash_table"],
    statement=(
        "Given a string `s`, return the length of the longest substring that contains no repeated "
        "characters. A substring is a contiguous run of characters.\n\n"
        "Implement `solution(s)` returning an integer.\n\n"
        'Examples: "abcabcbb" -> 3 ("abc"), "bbbbb" -> 1, "pwwkew" -> 3 ("wke").'
    ),
    constraints=["0 <= len(s) <= 5 * 10^4", "s may contain letters, digits, symbols and spaces"],
    reference=ReferenceSolution(
        algorithm="sliding_window_last_seen",
        time_complexity="O(n)",
        space_complexity="O(min(n, alphabet))",
        code=(
            "def solution(s):\n"
            "    last, start, best = {}, 0, 0\n"
            "    for i, ch in enumerate(s):\n"
            "        if ch in last and last[ch] >= start:\n"
            "            start = last[ch] + 1\n"
            "        last[ch] = i\n"
            "        best = max(best, i - start + 1)\n"
            "    return best\n"
        ),
        explanation="Grow a window; on a repeat, jump its start past the previous occurrence.",
    ),
    acceptable_alternatives=[
        AlternativeSolution(
            algorithm="sliding_window_set",
            time_complexity="O(n)",
            space_complexity="O(min(n, alphabet))",
            description="Window with a set, shrinking from the left until the repeat is gone.",
        )
    ],
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="check_every_substring",
            time_complexity="O(n^2) or O(n^3)",
            space_complexity="O(n)",
            optimality_gap="Checking all substrings vs one sliding window pass",
        )
    ],
    expected_concepts=["sliding_window", "two_pointers", "hash_map_last_index"],
    important_edge_cases=[
        "empty string",
        "all the same character",
        "repeat that lies before the window",
        "spaces",
    ],
    follow_up_questions=["How would you return the substring itself, not just its length?"],
    optimization_prompts=[
        "When you hit a repeated character, do you need to restart from scratch?"
    ],
    public=[
        (["abcabcbb"], "basic"),
        (["bbbbb"], "one repeated character"),
        (["pwwkew"], "answer in the middle"),
    ],
    hidden=[
        ([""], "empty"),
        (["abba"], "repeat before the window start"),
        (["a b c a"], "spaces count"),
        (["".join(chr(33 + (i * 7) % 90) for i in range(30000))], "long"),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "Think of a window over the string that never contains a repeat.",
            "When a character repeats, where can the window start from now on?",
            "Remember the last index of each character to move the start in one step.",
        ],
    ),
)


MERGE_INTERVALS = _problem(
    problem_id="merge_intervals_001",
    title="Merge Intervals",
    difficulty="medium",
    tags=["array", "sorting"],
    statement=(
        "Given a list of intervals `[start, end]`, merge all overlapping intervals and return the "
        "result sorted by start.\n\n"
        "Intervals that touch (one ends where the next starts) count as overlapping.\n\n"
        "Implement `solution(intervals)` returning a list of `[start, end]` lists.\n\n"
        "Example: [[1, 3], [2, 6], [8, 10], [15, 18]] -> [[1, 6], [8, 10], [15, 18]]."
    ),
    constraints=[
        "1 <= len(intervals) <= 10^4",
        "0 <= start <= end <= 10^4",
        "Input may be in any order",
    ],
    reference=ReferenceSolution(
        algorithm="sort_then_sweep",
        time_complexity="O(n log n)",
        space_complexity="O(n)",
        code=(
            "def solution(intervals):\n"
            "    merged = []\n"
            "    for start, end in sorted(intervals):\n"
            "        if merged and start <= merged[-1][1]:\n"
            "            merged[-1][1] = max(merged[-1][1], end)\n"
            "        else:\n"
            "            merged.append([start, end])\n"
            "    return merged\n"
        ),
        explanation="After sorting by start, each interval either extends the last merged one or starts a new one.",
    ),
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="repeated_pairwise_merge",
            time_complexity="O(n^2)",
            space_complexity="O(n)",
            optimality_gap="Merging pairs until nothing changes vs one pass after sorting",
        )
    ],
    expected_concepts=["sorting", "sweep", "overlap_condition"],
    important_edge_cases=[
        "unsorted input",
        "touching intervals",
        "interval fully inside another",
        "single interval",
    ],
    follow_up_questions=["How would you insert one new interval into an already merged list?"],
    optimization_prompts=["Would sorting first make the merging simpler?"],
    public=[([[[1, 3], [2, 6], [8, 10], [15, 18]]], "basic"), ([[[1, 4], [4, 5]]], "touching")],
    hidden=[
        ([[[5, 7], [1, 2], [2, 3]]], "unsorted"),
        ([[[1, 10], [2, 3], [4, 5]]], "contained"),
        ([[[3, 3]]], "single point"),
        (
            [[[i, i + 2] for i in range(20000, 0, -1)] + [[30000, 30001]]],
            "many intervals, reversed, chaining into two",
        ),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "When is it easy to tell whether two intervals overlap?",
            "If the intervals were sorted by start, which ones could overlap the current one?",
            "Sort by start; compare each interval with the last one you kept.",
        ],
    ),
)


PRODUCT_EXCEPT_SELF = _problem(
    problem_id="product_except_self_001",
    title="Product of Array Except Self",
    difficulty="medium",
    tags=["array", "prefix_sum"],
    statement=(
        "Given a list of integers `nums`, return a list `answer` where `answer[i]` is the product of "
        "all elements of `nums` except `nums[i]`.\n\n"
        "Do it without using division.\n\n"
        "Implement `solution(nums)` returning a list of integers.\n\n"
        "Example: [1, 2, 3, 4] -> [24, 12, 8, 6]."
    ),
    constraints=["2 <= len(nums) <= 10^5", "-30 <= nums[i] <= 30", "Do not use division"],
    reference=ReferenceSolution(
        algorithm="prefix_and_suffix_products",
        time_complexity="O(n)",
        space_complexity="O(1) extra (output not counted)",
        code=(
            "def solution(nums):\n"
            "    n = len(nums)\n"
            "    out = [1] * n\n"
            "    left = 1\n"
            "    for i in range(n):\n"
            "        out[i] = left\n"
            "        left *= nums[i]\n"
            "    right = 1\n"
            "    for i in range(n - 1, -1, -1):\n"
            "        out[i] *= right\n"
            "        right *= nums[i]\n"
            "    return out\n"
        ),
        explanation="answer[i] = (product of everything left of i) * (product of everything right of i).",
    ),
    acceptable_alternatives=[
        AlternativeSolution(
            algorithm="prefix_and_suffix_arrays",
            time_complexity="O(n)",
            space_complexity="O(n)",
            description="Build separate prefix and suffix product arrays, then multiply.",
        )
    ],
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="nested_loops",
            time_complexity="O(n^2)",
            space_complexity="O(1)",
            optimality_gap="Multiplying all others for each index vs two passes",
        )
    ],
    expected_concepts=["prefix_product", "suffix_product", "no_division"],
    important_edge_cases=["one zero", "two or more zeros", "negative numbers", "two elements"],
    follow_up_questions=["Why is the division approach a problem when the list contains zeros?"],
    optimization_prompts=["Can you reuse work between neighbouring positions?"],
    public=[([[1, 2, 3, 4]], "basic"), ([[-1, 1, 0, -3, 3]], "one zero")],
    hidden=[
        ([[0, 0, 2]], "two zeros"),
        ([[2, 3]], "two elements"),
        ([[-2, -3, 4]], "negatives"),
        ([[(i % 3) - 1 or 1 for i in range(1000)]], "long, ones and minus ones"),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "Split 'all except i' into two parts.",
            "What is the product of everything to the left of i? To the right?",
            "One pass left to right, one pass right to left.",
        ],
    ),
)


NUMBER_OF_ISLANDS = _problem(
    problem_id="number_of_islands_001",
    title="Number of Islands",
    difficulty="medium",
    tags=["graph", "bfs", "dfs", "matrix"],
    statement=(
        'Given a grid of strings `"1"` (land) and `"0"` (water), return the number of islands.\n\n'
        "An island is land connected horizontally or vertically (not diagonally). Everything "
        "outside the grid is water.\n\n"
        "Implement `solution(grid)` returning an integer.\n\n"
        'Example: [["1","1","0"],["0","1","0"],["0","0","1"]] -> 2.'
    ),
    constraints=["1 <= rows, cols <= 300", 'grid[r][c] is "0" or "1"'],
    reference=ReferenceSolution(
        algorithm="flood_fill_bfs",
        time_complexity="O(rows * cols)",
        space_complexity="O(rows * cols)",
        code=(
            "def solution(grid):\n"
            "    from collections import deque\n"
            "    rows, cols = len(grid), len(grid[0])\n"
            "    seen = set()\n"
            "    count = 0\n"
            "    for r in range(rows):\n"
            "        for c in range(cols):\n"
            "            if grid[r][c] != '1' or (r, c) in seen:\n"
            "                continue\n"
            "            count += 1\n"
            "            seen.add((r, c))\n"
            "            queue = deque([(r, c)])\n"
            "            while queue:\n"
            "                y, x = queue.popleft()\n"
            "                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):\n"
            "                    if 0 <= ny < rows and 0 <= nx < cols and grid[ny][nx] == '1' and (ny, nx) not in seen:\n"
            "                        seen.add((ny, nx))\n"
            "                        queue.append((ny, nx))\n"
            "    return count\n"
        ),
        explanation="Every unvisited land cell starts a new island; flood-fill it so it isn't counted again.",
    ),
    acceptable_alternatives=[
        AlternativeSolution(
            algorithm="dfs_or_union_find",
            time_complexity="O(rows * cols)",
            space_complexity="O(rows * cols)",
            description="Recursive/iterative DFS, or union-find over land cells.",
        )
    ],
    expected_concepts=["graph_traversal", "visited_set", "connected_components"],
    important_edge_cases=[
        "all water",
        "all land",
        "diagonal neighbours are separate",
        "single cell",
    ],
    follow_up_questions=["What happens to recursive DFS on a 300 x 300 grid of land?"],
    optimization_prompts=["How do you make sure each cell is processed only once?"],
    public=[
        ([[["1", "1", "0"], ["0", "1", "0"], ["0", "0", "1"]]], "basic"),
        ([[["1", "1", "1"], ["0", "1", "0"], ["1", "1", "1"]]], "one winding island"),
    ],
    hidden=[
        ([[["0", "0"], ["0", "0"]]], "all water"),
        ([[["1", "0"], ["0", "1"]]], "diagonal is not connected"),
        ([[["1"]]], "single cell"),
        ([[["1"] * 200 for _ in range(200)]], "large solid island"),
        (
            [[[("1" if (r + c) % 2 == 0 else "0") for c in range(60)] for r in range(60)]],
            "checkerboard",
        ),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "Think of land cells as nodes in a graph.",
            "When you find new land, how do you mark the whole island as seen?",
            "Flood fill (BFS or DFS) from each unvisited land cell and count how many times you start.",
        ],
    ),
)


COIN_CHANGE = _problem(
    problem_id="coin_change_001",
    title="Coin Change",
    difficulty="medium",
    tags=["dynamic_programming"],
    statement=(
        "Given coin values `coins` and an `amount`, return the fewest coins that add up to "
        "`amount`. You may use each coin value as many times as you like. If the amount can't be "
        "made, return -1.\n\n"
        "Implement `solution(coins, amount)` returning an integer.\n\n"
        "Examples: coins = [1, 2, 5], amount = 11 -> 3 (5 + 5 + 1); coins = [2], amount = 3 -> -1."
    ),
    constraints=["1 <= len(coins) <= 12", "1 <= coins[i] <= 10^4", "0 <= amount <= 10^4"],
    reference=ReferenceSolution(
        algorithm="bottom_up_dp",
        time_complexity="O(amount * len(coins))",
        space_complexity="O(amount)",
        code=(
            "def solution(coins, amount):\n"
            "    best = [0] + [amount + 1] * amount\n"
            "    for a in range(1, amount + 1):\n"
            "        for c in coins:\n"
            "            if c <= a and best[a - c] + 1 < best[a]:\n"
            "                best[a] = best[a - c] + 1\n"
            "    return best[amount] if best[amount] <= amount else -1\n"
        ),
        explanation="best[a] = 1 + min(best[a - c]) over coins c; build it up from 0.",
    ),
    acceptable_alternatives=[
        AlternativeSolution(
            algorithm="bfs_over_amounts",
            time_complexity="O(amount * len(coins))",
            space_complexity="O(amount)",
            description="Breadth-first search from 0; the first level that reaches amount is the answer.",
        )
    ],
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="recursion_with_memo",
            time_complexity="O(amount * len(coins))",
            space_complexity="O(amount) plus recursion depth",
            optimality_gap="Correct, but deep recursion risks the stack limit for large amounts",
        )
    ],
    expected_concepts=["dynamic_programming", "optimal_substructure", "greedy_fails"],
    important_edge_cases=[
        "amount 0",
        "impossible amount",
        "greedy gives the wrong answer (coins [1, 3, 4], amount 6)",
    ],
    follow_up_questions=[
        "Why doesn't always taking the largest coin work?",
        "How would you count the number of ways instead?",
    ],
    optimization_prompts=["Are you solving the same smaller amounts more than once?"],
    public=[([[1, 2, 5], 11], "basic"), ([[2], 3], "impossible")],
    hidden=[
        ([[1], 0], "zero amount"),
        ([[1, 3, 4], 6], "greedy fails"),
        ([[186, 419, 83, 408], 6249], "large mixed coins"),
        ([[7, 11], 10000], "large amount"),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "Try coins [1, 3, 4] and amount 6 with 'largest coin first'. What goes wrong?",
            "If you knew the answer for every smaller amount, how would you get this one?",
            "Fill a table best[0..amount], where best[a] = 1 + min(best[a - coin]).",
        ],
    ),
)


TRAPPING_RAIN_WATER = _problem(
    problem_id="trapping_rain_water_001",
    title="Trapping Rain Water",
    difficulty="hard",
    tags=["array", "two_pointers", "stack"],
    statement=(
        "`height` lists the heights of bars of width 1, side by side. Return how much rain water is "
        "trapped between the bars after it rains.\n\n"
        "Implement `solution(height)` returning an integer.\n\n"
        "Example: [0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1] -> 6."
    ),
    constraints=["1 <= len(height) <= 2 * 10^4", "0 <= height[i] <= 10^5"],
    reference=ReferenceSolution(
        algorithm="two_pointers",
        time_complexity="O(n)",
        space_complexity="O(1)",
        code=(
            "def solution(height):\n"
            "    left, right = 0, len(height) - 1\n"
            "    left_max = right_max = water = 0\n"
            "    while left < right:\n"
            "        if height[left] < height[right]:\n"
            "            left_max = max(left_max, height[left])\n"
            "            water += left_max - height[left]\n"
            "            left += 1\n"
            "        else:\n"
            "            right_max = max(right_max, height[right])\n"
            "            water += right_max - height[right]\n"
            "            right -= 1\n"
            "    return water\n"
        ),
        explanation="Water above a bar = min(tallest left, tallest right) - its height; the lower side decides, so move that pointer.",
    ),
    acceptable_alternatives=[
        AlternativeSolution(
            algorithm="prefix_max_arrays",
            time_complexity="O(n)",
            space_complexity="O(n)",
            description="Precompute tallest-to-the-left and tallest-to-the-right arrays.",
        ),
        AlternativeSolution(
            algorithm="monotonic_stack",
            time_complexity="O(n)",
            space_complexity="O(n)",
            description="Stack of decreasing bars; fill water layer by layer when a taller bar arrives.",
        ),
    ],
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="scan_both_sides_per_bar",
            time_complexity="O(n^2)",
            space_complexity="O(1)",
            optimality_gap="Finding left/right maximum for each bar separately vs one pass",
        )
    ],
    expected_concepts=["left_max_right_max", "two_pointers", "min_of_boundaries"],
    important_edge_cases=[
        "fewer than three bars",
        "strictly increasing",
        "flat",
        "a single deep valley",
    ],
    follow_up_questions=["Why is it safe to move the pointer on the lower side?"],
    optimization_prompts=[
        "Do you need both maximum arrays, or can you get away with constant extra space?"
    ],
    public=[
        ([[0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]], "basic"),
        ([[4, 2, 0, 3, 2, 5]], "deep middle"),
    ],
    hidden=[
        ([[1]], "single bar"),
        ([[1, 2, 3, 4]], "increasing"),
        ([[3, 3, 3]], "flat"),
        ([[5, 0, 0, 0, 5]], "one valley"),
        ([[(i * 37) % 101 for i in range(20000)]], "long jagged"),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "How much water can sit on top of one particular bar?",
            "It depends on the tallest bar to its left and the tallest to its right.",
            "With pointers at both ends, the side with the lower maximum is the one you can settle.",
        ],
    ),
)


MINIMUM_WINDOW_SUBSTRING = _problem(
    problem_id="minimum_window_substring_001",
    title="Minimum Window Substring",
    difficulty="hard",
    tags=["string", "sliding_window", "hash_table"],
    statement=(
        "Given strings `s` and `t`, return the shortest substring of `s` that contains every "
        "character of `t`, including repeats (if `t` has two 'a's, the window needs two 'a's).\n\n"
        "If several shortest windows exist, return the one that starts first. If there is none, "
        "return an empty string.\n\n"
        "Implement `solution(s, t)` returning a string.\n\n"
        'Example: s = "ADOBECODEBANC", t = "ABC" -> "BANC".'
    ),
    constraints=[
        "1 <= len(s), len(t) <= 10^5",
        "Upper and lower case letters are different characters",
    ],
    reference=ReferenceSolution(
        algorithm="sliding_window_counts",
        time_complexity="O(len(s) + len(t))",
        space_complexity="O(alphabet)",
        code=(
            "def solution(s, t):\n"
            "    from collections import Counter\n"
            "    need = Counter(t)\n"
            "    missing = len(t)\n"
            "    best_start, best_len = 0, float('inf')\n"
            "    left = 0\n"
            "    for right, ch in enumerate(s):\n"
            "        if need[ch] > 0:\n"
            "            missing -= 1\n"
            "        need[ch] -= 1\n"
            "        while missing == 0:\n"
            "            if right - left + 1 < best_len:\n"
            "                best_start, best_len = left, right - left + 1\n"
            "            need[s[left]] += 1\n"
            "            if need[s[left]] > 0:\n"
            "                missing += 1\n"
            "            left += 1\n"
            "    return '' if best_len == float('inf') else s[best_start:best_start + best_len]\n"
        ),
        explanation="Expand right until the window covers t, then shrink from the left while it still does.",
    ),
    suboptimal_valid=[
        SuboptimalSolution(
            algorithm="check_every_window",
            time_complexity="O(n^2) or worse",
            space_complexity="O(alphabet)",
            optimality_gap="Testing all substrings vs one sliding window",
        )
    ],
    expected_concepts=["sliding_window", "character_counts", "shrink_while_valid"],
    important_edge_cases=[
        "t longer than s",
        "no valid window",
        "repeated characters in t",
        "case matters",
        "s equals t",
    ],
    follow_up_questions=["How do you know the window is valid without re-counting it each time?"],
    optimization_prompts=["Once a window is valid, can you make it shorter before moving on?"],
    public=[(["ADOBECODEBANC", "ABC"], "basic"), (["a", "aa"], "not enough characters")],
    hidden=[
        (["a", "a"], "s equals t"),
        (["aa", "aa"], "repeats needed"),
        (["abcAbc", "Ab"], "case matters"),
        (["ab", "c"], "missing character"),
        (["xyz" * 20000 + "ABC" + "xyz" * 20000, "CBA"], "long, answer in the middle"),
    ],
    hint_policy=HintPolicy(
        max_hints=3,
        hints=[
            "Use a window over s. When does it contain everything t needs?",
            "Keep counts of what the window still needs, so checking validity is O(1).",
            "Once valid, move the left edge right as far as you can while it stays valid.",
        ],
    ),
)


LIBRARY: list[DSAProblem] = [
    VALID_PARENTHESES,
    BEST_TIME_STOCK,
    LONGEST_UNIQUE_SUBSTRING,
    MERGE_INTERVALS,
    PRODUCT_EXCEPT_SELF,
    NUMBER_OF_ISLANDS,
    COIN_CHANGE,
    TRAPPING_RAIN_WATER,
    MINIMUM_WINDOW_SUBSTRING,
]
