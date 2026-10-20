"""Tiny optional MAF qualification; never a second application backend."""

import argparse
import asyncio
import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path

from agent_framework import MCPStdioTool, Message
from agent_framework_ollama import OllamaChatClient
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from autocoder.fixtures import Fixture  # noqa: E402
from autocoder.protocol import write_json  # noqa: E402
from autocoder.provenance import inventory  # noqa: E402
from autocoder.serena_probe import SOURCE  # noqa: E402


class Probe(BaseModel):
    code: str


async def main(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", inventory(ROOT, "http://127.0.0.1:11434", "qwen3.5:9b"))
    result = {
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                "agent-framework-core",
                "agent-framework-ollama",
                "mcp",
                "pydantic",
                "ollama",
            )
        },
        "scope": "unscored tiny integration qualification",
    }
    try:
        async with asyncio.timeout(120):
            client = OllamaChatClient(
                host="http://127.0.0.1:11434",
                model="qwen3.5:9b",
                function_invocation_configuration={"enabled": False},
            )
            options = {
                "think": False,
                "num_ctx": 32768,
                "max_tokens": 512,
                "temperature": 0,
                "seed": 42,
                "response_format": Probe,
            }
            phases = []
            for prompt in (
                "Return a JSON object with code equal to ORCHID-731.",
                (
                    "What code did I give you in an earlier conversation? "
                    "If no earlier context is available, return code UNKNOWN."
                ),
            ):
                response = await client.get_response([Message("user", [prompt])], options=options)
                phases.append({"response": response.to_dict(), "text": response.text})
            result["fresh_phases"] = phases
            with Fixture({"module.py": "def value():\n    return 0\n"}) as fixture:
                with tempfile.TemporaryDirectory(prefix="autocoder-maf-serena-") as home:
                    async with MCPStdioTool(
                        name="serena",
                        command="uv",
                        args=[
                            "tool",
                            "run",
                            "--from",
                            SOURCE,
                            "serena",
                            "start-mcp-server",
                            "--project",
                            str(fixture.worktree),
                            "--context",
                            "desktop-app",
                            "--agent-interface",
                            "tools",
                            "--enable-web-dashboard",
                            "false",
                            "--enable-gui-log-window",
                            "false",
                            "--open-web-dashboard",
                            "false",
                            "--log-level",
                            "WARNING",
                        ],
                        env=dict(os.environ, SERENA_HOME=home),
                        load_prompts=False,
                        allowed_tools=["initial_instructions", "find_symbol"],
                        request_timeout=None,
                    ) as mcp:
                        await mcp.call_tool("initial_instructions")
                        result["mcp_lookup"] = await mcp.call_tool(
                            "find_symbol",
                            name_path_pattern="value",
                            relative_path="module.py",
                            include_body=True,
                            max_answer_chars=2048,
                        )
                        tool_options = {
                            key: value for key, value in options.items() if key != "response_format"
                        }
                        tool_options["tools"] = [
                            tool for tool in mcp.functions if tool.name == "find_symbol"
                        ]
                        response = await client.get_response(
                            [
                                Message(
                                    "user",
                                    [
                                        "Find value in module.py with find_symbol. "
                                        "Set include_body true."
                                    ],
                                )
                            ],
                            options=tool_options,
                        )
                        result["tool_response"] = response.to_dict()
            result["status"] = "completed_probe_review_required"
    except Exception as error:
        result["status"] = "failed_probe"
        result["error"] = f"{type(error).__name__}: {error}"
    write_json(output / "result.json", result)
    print(json.dumps({"status": result["status"], "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args().output))
