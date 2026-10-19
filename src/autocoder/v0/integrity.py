"""Conservative protection for tests embedded in otherwise editable source files."""

import re

MARKERS = re.compile(
    r"(?m)^\s*(?:#\s*\[\s*(?:cfg\s*\(\s*test\s*\)|test)\s*\]"
    r"|(?:async\s+)?def\s+test_\w+\s*\(|class\s+Test\w*)"
)


def preserve_inline_tests(before, after):
    marker = MARKERS.search(before)
    if marker:
        # Preserve the complete trailing test region, including attributes and fixtures.
        original = before[marker.start() :]
        candidate = MARKERS.search(after)
        if candidate is None or after[candidate.start() :] != original:
            raise ValueError("Embedded tests require explicit approval for this file")
    if ">>>" in before or ("```" in before and "///" in before):
        # Ambiguous embedded doctest boundaries require a separately approved test edit.
        if before != after:
            raise ValueError("Source contains doctests; explicit test-file approval is required")
