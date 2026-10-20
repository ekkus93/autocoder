import asyncio
import json

from autocoder.fixtures import Fixture
from autocoder.v0.cli import journal_for
from autocoder.v0.coordinator import Coordinator
from autocoder.v0.gateway import ToolGateway
from autocoder.v0.schema import Check, Phase, Project


def coordinator_for(repository, temporary, transport):
    project = Project(
        repository=repository,
        state_dir=temporary / "state",
        readable_paths=["source.py", "helper.py"],
        editable_paths=["source.py"],
        checks=[Check(name="unit", command=["/usr/bin/true"])],
        context=16384,
    )
    journal = journal_for(project, "c" * 32, create=True)
    controller = Coordinator(project, journal, transport=transport)
    controller.workspace.create()
    controller.gateway = ToolGateway(controller.workspace, controller.budget, None)
    controller.transition(Phase.ORIENT)
    return controller


def answer(message):
    return {
        "message": message,
        "prompt_tokens": 10,
        "output_tokens": 10,
        "truncated": False,
        "finished": True,
    }


def test_orientation_hands_off_before_native_tool_history_exceeds_context(tmp_path):
    source = "".join(f"# line {i:03}: " + "a" * 100 + "\n" for i in range(200))
    with Fixture({"source.py": source, "helper.py": source}) as fixture:
        calls = []

        async def transport(endpoint, model, messages, budget, **options):
            calls.append(options.get("tools") is not None)
            if options.get("tools"):
                assert calls == [True], "Oversized history should transition to a fresh handoff"
                return answer(
                    {
                        "content": "I am examining the relevant source. " * 80,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {"path": "source.py", "start": 80, "end": 115},
                                }
                            }
                        ],
                    }
                )
            assert len(messages) == 2
            evidence = json.loads(messages[1]["content"])["evidence"]
            assert "source" not in evidence["last_retrieval"][0]
            frame = evidence["files"]["source.py"]
            assert frame["start"] == 80
            return answer(
                {
                    "content": json.dumps(
                        {
                            "base_sha": evidence["base_sha"],
                            "findings": [
                                {
                                    "path": "source.py",
                                    "sha256": frame["sha256"],
                                    "start": 80,
                                    "end": 81,
                                    "summary": "Relevant current source",
                                }
                            ],
                        }
                    )
                }
            )

        controller = coordinator_for(fixture.repository, tmp_path, transport)
        artifact = asyncio.run(controller.orient("Locate the source defect"))
        assert artifact.findings[0].start == 80
        assert calls == [True, False]
        resets = [row for row in controller.journal.read() if row["kind"] == "CONTEXT_RESET"]
        assert len(resets) == 1 and "orientation history" in resets[0]["data"]["reason"]


def test_qualified_method_focus_survives_unrelated_orientation_reads(tmp_path):
    source = (
        "class Client:\n"
        "    def consume(self, row):\n"
        '        self.status = row.get("status")\n'
        "\n"
        "def run():\n"
        + "".join("    # unrelated " + "x" * 80 + "\n" for _ in range(200))
        + "    pass\n"
    )
    helper = "".join("# helper " + "y" * 100 + "\n" for _ in range(200))
    with Fixture({"source.py": source, "helper.py": helper}) as fixture:
        discovery = 0

        async def transport(endpoint, model, messages, budget, **options):
            nonlocal discovery
            evidence = json.loads(messages[1]["content"])["evidence"]
            if options.get("tools") and discovery == 0:
                discovery += 1
                return answer(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_file_range",
                                    "arguments": {"path": "source.py", "start": 80, "end": 90},
                                }
                            }
                        ]
                    }
                )
            if options.get("tools"):
                return answer({"content": "Enough source retrieved"})
            frame = evidence["files"]["source.py"]
            assert frame["focused_symbol"] is True
            assert frame["start"] == 2 and frame["end"] == 3
            assert "def consume" in frame["source"] and "unrelated" not in frame["source"]
            return answer(
                {
                    "content": json.dumps(
                        {
                            "base_sha": evidence["base_sha"],
                            "findings": [
                                {
                                    "path": "source.py",
                                    "sha256": frame["sha256"],
                                    "start": 2,
                                    "end": 3,
                                    "summary": "Missing phase update",
                                }
                            ],
                        }
                    )
                }
            )

        controller = coordinator_for(fixture.repository, tmp_path, transport)
        artifact = asyncio.run(controller.orient("Fix Client.consume, then run all checks."))
        assert artifact.findings[0].start == 2
