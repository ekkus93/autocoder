"""Typed phase permissions, bounded source evidence and model-independent checks."""

import ast
import json
import subprocess
from pathlib import Path

from autocoder.budget import BudgetExhausted
from autocoder.protocol import digest
from autocoder.tool_schema import MODELS, inventory
from autocoder.v0.journal import NeedsUser
from autocoder.v0.schema import Phase, relative
from autocoder.v0.workspace import safe_file

READ_TOOLS = {"search_text", "read_file_range", "read_symbol", "find_references"}
WRITE_PHASES = {Phase.IMPLEMENT, Phase.REPAIR}


class ToolGateway:
    def __init__(self, workspace, budget, checks, navigator=None):
        self.workspace, self.project = workspace, workspace.project
        self.journal, self.budget, self.checks = workspace.journal, budget, checks
        self.navigator = navigator
        self.phase = Phase.ORIENT
        self.planned_paths = set()
        self.calls = 0
        self.fingerprints = {}
        self.reads = {}

    def enter(self, phase, paths=()):
        self.phase, self.planned_paths = phase, set(paths)
        self.calls, self.fingerprints = 0, {}

    def tools(self):
        allowed = READ_TOOLS | (
            {"apply_edit", "run_named_check"} if self.phase in WRITE_PHASES else set()
        )
        return [tool for tool in inventory(6) if tool["function"]["name"] in allowed]

    def read(self, name, start=1, end=120):
        if not self.project.can_read(name):
            raise ValueError("Path is not approved for source reading")
        _, data = safe_file(self.workspace.root, name)
        lines = data.decode("utf-8").splitlines()
        if start < 1 or end < start or end - start >= 120 or (start > len(lines) and lines):
            raise ValueError("Read range must be at most 120 existing source lines")
        excerpt = "\n".join(lines[start - 1 : end])
        result = {
            "path": name,
            "sha256": digest(data),
            "base_sha": self.workspace.base_sha,
            "start": start,
            "end": min(end, max(1, len(lines))),
            "total_lines": len(lines),
            "source": excerpt[:4000],
            "truncated": len(excerpt) > 4000,
        }
        result["end"] = start + max(1, len(result["source"].splitlines())) - 1
        self.reads.setdefault(name, []).append((start, result["end"], result["sha256"]))
        return result

    def evidence(self, paths=None):
        # Default text budget is divided across explicitly configured paths.
        selected = list(paths or self.project.readable_paths)
        if len(selected) > 8:
            selected = selected[:8]
        limit = min(3000, 12000 // max(1, len(selected)))
        files = {name: self.read(name) for name in selected}
        for entry in files.values():
            entry["truncated"] |= len(entry["source"]) > limit
            entry["source"] = entry["source"][:limit]
            entry["end"] = entry["start"] + max(1, len(entry["source"].splitlines())) - 1
            self.reads[entry["path"]][-1] = (entry["start"], entry["end"], entry["sha256"])
        return {
            "base_sha": self.workspace.base_sha,
            "files": files,
            "available_paths": self.project.readable_paths,
        }

    def search(self, pattern, path):
        relative(path)
        paths = [n for n in self.project.readable_paths if n == path or n.startswith(path + "/")]
        if not paths or len(pattern) > 256 or "\x00" in pattern:
            raise ValueError("Search must name an approved relative path and bounded literal")
        result = []
        for name in paths:
            file, data = safe_file(self.workspace.root, name)
            process = subprocess.run(
                [
                    "rg",
                    "--no-config",
                    "--color=never",
                    "--no-heading",
                    "-F",
                    "-n",
                    "--max-count",
                    "20",
                    "--max-columns",
                    "300",
                    "-e",
                    pattern,
                    "--",
                    str(file),
                ],
                capture_output=True,
                text=True,
                timeout=min(5, self.budget.remaining_seconds),
            )
            if process.returncode not in {0, 1}:
                raise ValueError("Bounded literal search failed")
            for line in process.stdout.splitlines()[:20]:
                result.append({"path": name, "sha256": digest(data), "match": line[:400]})
                if len(result) >= 20:
                    return result
        return result

    def dispatch(self, name, arguments):
        allowed = {tool["function"]["name"] for tool in self.tools()}
        if name not in allowed or name not in MODELS:
            raise ValueError("Tool is not permitted in this phase")
        self.workspace.assert_expected()
        self.calls += 1
        if self.calls > self.project.phase_tool_calls:
            raise BudgetExhausted("phase_tool_calls")
        self.budget.consume(tool_calls=1)
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        args = MODELS[name].model_validate(arguments)
        identity = digest(
            json.dumps(
                {"tool": name, "arguments": args.model_dump(), "source": self.workspace.expected()},
                sort_keys=True,
            ).encode()
        )
        self.fingerprints[identity] = self.fingerprints.get(identity, 0) + 1
        if self.fingerprints[identity] >= 2:
            raise BudgetExhausted("duplicate tool operation without source progress")
        input_ref = self.journal.artifact({"tool": name, "arguments": args.model_dump()})
        self.journal.emit(
            "TOOL_CALL", evidence_ref=input_ref, data={"tool": name, "fingerprint": identity}
        )
        try:
            if name == "apply_edit":
                if args.path not in self.planned_paths:
                    raise ValueError("Edit path is outside the validated plan")
                result = self.workspace.edit(args)
            elif name == "read_file_range":
                result = self.read(args.path, args.start, args.end)
            elif name == "search_text":
                result = self.search(args.pattern, args.path)
            elif name == "run_named_check":
                check = next((c for c in self.project.checks if c.name == args.name), None)
                if check is None:
                    raise ValueError("Unknown named check")
                result = self.checks.run(check, "model-requested")
            else:
                if not self.project.can_read(args.path):
                    raise ValueError("Symbol path is outside approved source")
                if self.navigator is not None:
                    result = self.navigator.lookup(name, args.path, args.symbol)
                elif name == "find_references":
                    result = {
                        "method": "rg lexical fallback; semantic references unavailable",
                        "matches": sum(
                            (self.search(args.symbol, p) for p in self.project.readable_paths), []
                        )[:20],
                    }
                else:
                    _, data = safe_file(self.workspace.root, args.path)
                    if Path(args.path).suffix != ".py":
                        raise ValueError(
                            "Semantic navigation unavailable; use bounded source reads"
                        )
                    tree = ast.parse(data)
                    nodes = [
                        n
                        for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                        and n.name == args.symbol
                    ]
                    if len(nodes) != 1:
                        raise ValueError("Symbol is missing or ambiguous")
                    result = self.read(
                        args.path, nodes[0].lineno, min(nodes[0].end_lineno, nodes[0].lineno + 119)
                    )
            ref = self.journal.artifact(result)
            self.journal.emit("TOOL_RESULT", evidence_ref=ref, status="pass", data={"tool": name})
            raw = json.dumps(result, ensure_ascii=False)
            if len(raw.encode()) > self.project.observation_bytes:
                return {"truncated": True, "evidence_ref": ref, "preview": raw[:1000]}
            return result
        except (ValueError, NeedsUser) as error:
            self.journal.emit(
                "TOOL_RESULT", status="fail", data={"tool": name, "error": type(error).__name__}
            )
            if isinstance(error, NeedsUser):
                raise
            return {"error": str(error)[:512]}
