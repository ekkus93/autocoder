"""Generate throwaway bug-fix projects for informal `autocoder-task` smoke tests.

Each project is a small Python repository with a seeded bug, a regression script that
prints `expected regression failure` for every failing check, a plain-language task
description, and one project policy file per model. Before anything is written for use,
every task is verified: the buggy tree must fail its regression script and a reference
fix must pass it. The projects are scratch material, not Stage 0 benchmark assets.

    uv run python scripts/make_scratch_tasks.py --output tmp/tasks
    uv run autocoder-task --config tmp/tasks/paginate.qwen3-5-9b.json start \
        --request-file tmp/tasks/paginate/task.txt
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PYTHON = "/usr/bin/python3"
DEFAULT_MODELS = ("qwen3.5:9b", "devstral-small-2:24b")
SIGNATURE = "expected regression failure"

TEST_HEAD = """import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

failures = []


def check(name, fn, want):
    try:
        got = fn()
    except Exception as exc:  # noqa: BLE001
        got = f"{type(exc).__name__}: {exc}"
    if got != want:
        failures.append(f"expected regression failure: {name}: got {got!r}, want {want!r}")

"""
TEST_TAIL = r"""
if failures:
    print("\n".join(failures))
    sys.exit(1)
print("ok")
"""

PAGER_BUGGY = '''"""Pagination helpers."""


def page_count(total_items, per_page):
    """Number of pages needed to show total_items; 0 items need 0 pages."""
    return total_items // per_page


def get_page(items, page, per_page):
    """Return the items on a 1-based page; out-of-range pages return []."""
    start = page * per_page
    return list(items[start:start + per_page])
'''
PAGER_FIXED = '''"""Pagination helpers."""


def page_count(total_items, per_page):
    """Number of pages needed to show total_items; 0 items need 0 pages."""
    return -(-total_items // per_page)


def get_page(items, page, per_page):
    """Return the items on a 1-based page; out-of-range pages return []."""
    if page < 1:
        return []
    start = (page - 1) * per_page
    return list(items[start:start + per_page])
'''

TOKENIZER_BUGGY = r'''"""Split an arithmetic expression into tokens."""

import re

_TOKEN = re.compile(r"\s*(\d+|[-+*/()])")


def tokenize(text):
    tokens = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            raise ValueError(f"bad character at {pos}")
        tokens.append(match.group(1))
        pos = match.end()
    return tokens
'''
TOKENIZER_FIXED = TOKENIZER_BUGGY.replace(r"(\d+|[-+*/()])", r"(\d+\.\d+|\d+|[-+*/()])")
assert TOKENIZER_FIXED != TOKENIZER_BUGGY

EVALUATOR_HEAD = '''"""Evaluate arithmetic expressions."""

from calc.tokenizer import tokenize


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self):
        token = self.peek()
        self.pos += 1
        return token

'''
EVALUATOR_TAIL = """
    def term(self):
        value = self.factor()
        while self.peek() in ("*", "/"):
            op = self.take()
            rhs = self.factor()
            value = value * rhs if op == "*" else value / rhs
        return value

    def factor(self):
        token = self.take()
        if token == "(":
            value = self.expr()
            if self.take() != ")":
                raise ValueError("expected )")
            return value
        if token == "-":
            return -self.factor()
        if token is None:
            raise ValueError("unexpected end")
        return float(token)


def evaluate(text):
    parser = _Parser(tokenize(text))
    value = parser.expr()
    if parser.peek() is not None:
        raise ValueError("trailing input")
    return value
"""
EXPR_BUGGY = """    def expr(self):
        value = self.factor()
        while self.peek() in ("+", "-", "*", "/"):
            op = self.take()
            rhs = self.factor()
            if op == "+":
                value += rhs
            elif op == "-":
                value -= rhs
            elif op == "*":
                value *= rhs
            else:
                value /= rhs
        return value
"""
EXPR_FIXED = """    def expr(self):
        value = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            rhs = self.term()
            value = value + rhs if op == "+" else value - rhs
        return value
"""

INTERVALS_BUGGY = '''"""Interval helpers."""


def merge(intervals):
    """Merge overlapping or touching [start, end] intervals.

    Returns a list of (start, end) tuples sorted by start. The input is not modified.
    """
    result = []
    for start, end in intervals:
        if result and start < result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result
'''
INTERVALS_FIXED = '''"""Interval helpers."""


def merge(intervals):
    """Merge overlapping or touching [start, end] intervals.

    Returns a list of (start, end) tuples sorted by start. The input is not modified.
    """
    result = []
    for start, end in sorted(tuple(pair) for pair in intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result
'''

FORMATTING = '''"""Number formatting."""


def format_number(value):
    """Show whole numbers without a decimal point, others to 2 places."""
    if float(value).is_integer():
        return str(int(value))
    return str(round(value, 2))
'''
STATS_BUGGY = '''"""Basic statistics."""


def mean(values):
    return sum(values) / len(values)


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
'''
STATS_FIXED = '''"""Basic statistics."""


def mean(values):
    return sum(values) / len(values)


def median(values):
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
'''
REPORT_BUGGY = '''"""Summary report."""

from report.formatting import format_number
from report.stats import mean, median


def render(values):
    return (
        f"n={len(values)} mean={format_number(mean(values))} "
        f"median={format_number(median(values))} max={format_number(values[-1])}"
    )
'''
REPORT_FIXED = REPORT_BUGGY.replace("values[-1]", "max(values)")
assert REPORT_FIXED != REPORT_BUGGY

TASKS = {
    "paginate": {
        "request": (
            "Our pagination helper returns wrong results. Page counts come out too low when "
            "the item count is not an exact multiple of the page size, page 1 returns the "
            "second page of items, and asking for page 0 should return an empty list instead "
            "of items. Fix the helper in src/pager.py.\n"
        ),
        "buggy": {"src/pager.py": PAGER_BUGGY},
        "fixed": {"src/pager.py": PAGER_FIXED},
        "editable": ["src/pager.py"],
        "test": TEST_HEAD
        + """from pager import get_page, page_count

check("count 10/3", lambda: page_count(10, 3), 4)
check("count 9/3", lambda: page_count(9, 3), 3)
check("count 0/3", lambda: page_count(0, 3), 0)
check("count 1/5", lambda: page_count(1, 5), 1)
check("page 1", lambda: get_page(list(range(10)), 1, 3), [0, 1, 2])
check("page 4", lambda: get_page(list(range(10)), 4, 3), [9])
check("page 5 out of range", lambda: get_page(list(range(10)), 5, 3), [])
check("page 0", lambda: get_page(list(range(10)), 0, 3), [])
check("page -1", lambda: get_page(list(range(10)), -1, 3), [])
"""
        + TEST_TAIL,
    },
    "calc": {
        "request": (
            'The calculator gives wrong answers. "2+3*4" should be 14 but we get 20 '
            "(multiplication and division must bind tighter than addition and subtraction), "
            'and decimal numbers such as "3.5*2" raise an error instead of returning 7.0. '
            "Fix the calculator package under src/calc.\n"
        ),
        "buggy": {
            "src/calc/__init__.py": "",
            "src/calc/tokenizer.py": TOKENIZER_BUGGY,
            "src/calc/evaluator.py": EVALUATOR_HEAD + EXPR_BUGGY + EVALUATOR_TAIL,
        },
        "fixed": {
            "src/calc/tokenizer.py": TOKENIZER_FIXED,
            "src/calc/evaluator.py": EVALUATOR_HEAD + EXPR_FIXED + EVALUATOR_TAIL,
        },
        "editable": ["src/calc/tokenizer.py", "src/calc/evaluator.py"],
        "test": TEST_HEAD
        + """from calc.evaluator import evaluate

check("precedence", lambda: evaluate("2+3*4"), 14.0)
check("parens", lambda: evaluate("(2+3)*4"), 20.0)
check("left assoc minus", lambda: evaluate("10-4-3"), 3.0)
check("decimal", lambda: evaluate("3.5*2"), 7.0)
check("unary minus", lambda: evaluate("-2*3"), -6.0)
check("left assoc divide", lambda: evaluate("8/4/2"), 1.0)
check("mixed", lambda: evaluate("1+2*3-4/2"), 5.0)
check("decimal add", lambda: evaluate("0.5+0.25"), 0.75)
"""
        + TEST_TAIL,
    },
    "intervals": {
        "request": (
            "merge() in src/intervals.py is supposed to combine overlapping or touching "
            "intervals, but it gives wrong results: unsorted input is not merged correctly, "
            "and intervals that touch at an endpoint (like (1, 2) and (2, 3)) are left "
            "separate. Fix it.\n"
        ),
        "buggy": {"src/intervals.py": INTERVALS_BUGGY},
        "fixed": {"src/intervals.py": INTERVALS_FIXED},
        "editable": ["src/intervals.py"],
        "test": TEST_HEAD
        + """from intervals import merge

check("basic", lambda: merge([(1, 3), (2, 6), (8, 10)]), [(1, 6), (8, 10)])
check("unsorted", lambda: merge([(8, 10), (1, 3), (2, 6)]), [(1, 6), (8, 10)])
check("touching", lambda: merge([(1, 2), (2, 3)]), [(1, 3)])
check("contained", lambda: merge([(1, 10), (2, 3)]), [(1, 10)])
check("empty", lambda: merge([]), [])
check("lists", lambda: merge([[5, 6], [1, 2], [2, 3]]), [(1, 3), (5, 6)])
data = [(3, 4), (1, 2)]
merge(data)
check("input not modified", lambda: data, [(3, 4), (1, 2)])
"""
        + TEST_TAIL,
    },
    "report": {
        "request": (
            "The summary line printed by report.render() is wrong in some cases. For an even "
            "number of values the median is wrong (it should be the average of the two middle "
            'values), and for unsorted data the "max" shows the last value instead of the '
            "largest. Fix the report package under src/report. Number formatting is believed "
            "to be correct.\n"
        ),
        "buggy": {
            "src/report/__init__.py": "",
            "src/report/formatting.py": FORMATTING,
            "src/report/stats.py": STATS_BUGGY,
            "src/report/report.py": REPORT_BUGGY,
        },
        "fixed": {
            "src/report/stats.py": STATS_FIXED,
            "src/report/report.py": REPORT_FIXED,
        },
        "editable": ["src/report/stats.py", "src/report/report.py", "src/report/formatting.py"],
        "test": TEST_HEAD
        + """from report.report import render

check("even count", lambda: render([3, 1, 2, 4]), "n=4 mean=2.5 median=2.5 max=4")
check("odd count", lambda: render([5, 1, 3]), "n=3 mean=3 median=3 max=5")
check("single", lambda: render([7]), "n=1 mean=7 median=7 max=7")
check("unsorted max", lambda: render([2, 2, 10, 1]), "n=4 mean=3.75 median=2 max=10")
check("max not last", lambda: render([9, 1, 2]), "n=3 mean=4 median=2 max=9")
"""
        + TEST_TAIL,
    },
}


def write_files(base, files):
    for relative, content in files.items():
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def run_regression(base):
    done = subprocess.run(
        [PYTHON, "tests/regression.py"], cwd=base, capture_output=True, text=True, timeout=60
    )
    return done.returncode, done.stdout.strip()


def verify(name, task, scratch):
    """Return the number of failing checks in the buggy tree; raise if a task is unsound."""
    buggy = scratch / name / "buggy"
    write_files(buggy, task["buggy"])
    write_files(buggy, {"tests/regression.py": task["test"]})
    fixed = scratch / name / "fixed"
    shutil.copytree(buggy, fixed)
    write_files(fixed, task["fixed"])
    buggy_code, buggy_output = run_regression(buggy)
    fixed_code, fixed_output = run_regression(fixed)
    failing = [line for line in buggy_output.splitlines() if SIGNATURE in line]
    if buggy_code == 0 or not failing:
        raise RuntimeError(f"{name}: buggy tree does not fail with the expected signature")
    if fixed_code != 0 or fixed_output != "ok":
        raise RuntimeError(f"{name}: reference fix does not pass:\n{fixed_output}")
    return len(failing)


def slug(model):
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def create_project(root, name, task, models, endpoint, state_dir):
    project = root / name
    write_files(project, task["buggy"])
    write_files(project, {"tests/regression.py": task["test"]})
    write_files(project, {"task.txt": task["request"], ".gitignore": "__pycache__/\n"})
    git = ["git", "-c", "user.name=scratch", "-c", "user.email=scratch@example.invalid"]
    subprocess.run([*git, "init", "-q", "-b", "main"], cwd=project, check=True)
    subprocess.run([*git, "add", "-A"], cwd=project, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "Initial scratch project"], cwd=project, check=True)
    for model in models:
        policy = {
            "repository": str(project),
            "state_dir": str(state_dir),
            "endpoint": endpoint,
            "model": model,
            "readable_paths": task["editable"],
            "editable_paths": task["editable"],
            "checks": [
                {
                    "name": "regression",
                    "kind": "tests",
                    "language": "python",
                    "command": [PYTHON, "tests/regression.py"],
                    "regression_pattern": SIGNATURE,
                    "timeout": 30,
                }
            ],
        }
        (root / f"{name}.{slug(model)}.json").write_text(json.dumps(policy, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path, required=True, help="new directory to create")
    parser.add_argument("--state-dir", type=Path, help="task state root (default OUTPUT/state)")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--model", action="append", help="repeatable (default: two local models)")
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        parser.error(f"{root} already exists")
    models = args.model or list(DEFAULT_MODELS)
    state_dir = (args.state_dir or root / "state").resolve()
    with tempfile.TemporaryDirectory() as scratch:
        counts = {name: verify(name, task, Path(scratch)) for name, task in TASKS.items()}
    root.mkdir(parents=True)
    for name, task in TASKS.items():
        create_project(root, name, task, models, args.endpoint, state_dir)
        print(f"{name}: {counts[name]} failing checks in the seeded bug; reference fix passes")
    print(f"Created {len(TASKS)} projects in {root}")


if __name__ == "__main__":
    sys.exit(main())
