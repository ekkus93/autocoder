import difflib

import pytest

from autocoder.editing_probe import apply
from autocoder.fixtures import Fixture
from autocoder.protocol import digest
from autocoder.serena_probe import Serena

SOURCE = "def value():\n    return 0\n"


def test_exact_stale_ambiguous_and_outside_edits_fail_without_mutation():
    with Fixture({"module.py": SOURCE}) as fixture:
        payload = {
            "path": "module.py",
            "old": "return 0",
            "new": "return 1",
            "expected_sha256": "0" * 64,
        }
        with pytest.raises(ValueError, match="Stale"):
            apply(fixture, "exact", payload)
        payload["expected_sha256"] = digest(SOURCE.encode())
        payload["path"] = "../module.py"
        with pytest.raises(ValueError, match="Unsafe"):
            apply(fixture, "exact", payload)
        assert not fixture.diff()
        payload["path"] = "module.py"
        apply(fixture, "exact", payload)
        assert "return 1" in (fixture.worktree / "module.py").read_text()
    ambiguous = SOURCE + "\ndef other():\n    return 0\n"
    with Fixture({"module.py": ambiguous}) as fixture:
        with pytest.raises(ValueError, match="uniquely"):
            apply(
                fixture,
                "exact",
                {
                    "path": "module.py",
                    "old": "return 0",
                    "new": "return 1",
                    "expected_sha256": digest(ambiguous.encode()),
                },
            )
        assert not fixture.diff()


def test_validated_diff_changes_only_registered_file():
    new = SOURCE.replace("return 0", "return 1")
    patch = "".join(
        difflib.unified_diff(
            SOURCE.splitlines(True),
            new.splitlines(True),
            fromfile="a/module.py",
            tofile="b/module.py",
        )
    )
    with Fixture({"module.py": SOURCE}) as fixture:
        apply(
            fixture,
            "diff",
            {"path": "module.py", "patch": patch, "expected_sha256": digest(SOURCE.encode())},
        )
        assert (fixture.worktree / "module.py").read_text() == new


def test_serena_symbol_edit_is_scoped_to_owned_worktree():
    with Fixture({"module.py": SOURCE}) as fixture:
        with Serena(fixture.worktree) as serena:
            assert not serena.call("initial_instructions", {}).get("isError")
            assert not serena.call("get_current_config", {}).get("isError")
            apply(
                fixture,
                "symbol",
                {
                    "path": "module.py",
                    "symbol": "value",
                    "body": "def value():\n    return 1",
                    "expected_sha256": digest(SOURCE.encode()),
                },
                serena,
            )
        assert (fixture.worktree / "module.py").read_text() == SOURCE.replace(
            "return 0", "return 1"
        )
        assert (fixture.repository / "module.py").read_text() == SOURCE
