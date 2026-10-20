"""Inference-only Unix socket proxy for isolated baseline clients."""

import asyncio
import json
import socketserver
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from autocoder.budget import Budget, BudgetExhausted
from autocoder.experiments import append
from autocoder.inference import post
from autocoder.provenance import request_json


class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class ModelProxy:
    def __init__(self, socket_path: Path, endpoint: str, model: str, budget: Budget, log: Path):
        self.endpoint, self.model, self.budget, self.log = endpoint, model, budget, log
        self.lock = threading.Lock()
        self.error = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path not in {"/api/version", "/api/tags", "/v1/models"}:
                    self.send_error(403)
                    return
                if self.path == "/v1/models":
                    data = {"object": "list", "data": [{"id": owner.model, "object": "model"}]}
                else:
                    data = request_json(owner.endpoint, self.path)
                self.reply(json.dumps(data).encode(), "application/json")

            def do_POST(self):
                try:
                    with owner.lock:
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= 200_000:
                            raise ValueError("Unbounded or empty inference payload")
                        payload = json.loads(self.rfile.read(length))
                        if self.path == "/api/show":
                            self.reply(
                                json.dumps(
                                    request_json(owner.endpoint, self.path, {"model": owner.model})
                                ).encode(),
                                "application/json",
                            )
                            return
                        if self.path not in {"/api/chat", "/v1/chat/completions"}:
                            raise ValueError("Only inference API routes are allowed")
                        if payload.get("model") not in {owner.model, "openai/" + owner.model}:
                            raise ValueError("Unregistered model")
                        payload["model"] = owner.model
                        streaming = payload.get("stream", False)
                        payload["stream"] = False
                        requested = len(json.dumps(payload).encode()) + 1024
                        remaining = (
                            owner.budget.limits.output_tokens
                            - owner.budget.snapshot().output_tokens
                        )
                        maximum = min(2048, remaining)
                        if maximum <= 0:
                            raise BudgetExhausted("output_tokens")
                        if requested + maximum > 32768:
                            raise BudgetExhausted("conservative context reservation")
                        owner.budget.consume(request_tokens=requested, output_tokens=maximum)
                        payload["think"] = False
                        payload["temperature"] = 0
                        payload["seed"] = 42
                        payload.setdefault("options", {}).update(
                            {"num_ctx": 32768, "num_predict": maximum, "temperature": 0, "seed": 42}
                        )
                        if self.path.startswith("/v1"):
                            payload["max_tokens"] = maximum
                            payload.pop("stream_options", None)
                        started = time.monotonic()
                        actual_route = self.path
                        if self.path.startswith("/v1"):
                            actual_route = "/api/chat"
                            native_messages = []
                            tool_names = {}
                            for original in payload["messages"]:
                                original = dict(original)
                                for call in original.get("tool_calls") or []:
                                    call = dict(call)
                                    function = dict(call["function"])
                                    if isinstance(function.get("arguments"), str):
                                        function["arguments"] = json.loads(function["arguments"])
                                    tool_names[call.get("id")] = function["name"]
                                if original.get("tool_calls"):
                                    original["tool_calls"] = [
                                        {
                                            "function": {
                                                "name": call["function"]["name"],
                                                "arguments": json.loads(
                                                    call["function"]["arguments"]
                                                )
                                                if isinstance(
                                                    call["function"].get("arguments"), str
                                                )
                                                else call["function"].get("arguments", {}),
                                            }
                                        }
                                        for call in original["tool_calls"]
                                    ]
                                if original.get("role") == "tool":
                                    original["tool_name"] = tool_names.get(
                                        original.pop("tool_call_id", None), ""
                                    )
                                original.pop("reasoning_content", None)
                                original.pop("reasoning", None)
                                native_messages.append(original)
                            native_payload = {
                                "model": owner.model,
                                "messages": native_messages,
                                "stream": False,
                                "think": False,
                                "options": payload["options"],
                            }
                            if payload.get("tools"):
                                native_payload["tools"] = payload["tools"]
                            payload = native_payload
                        response = asyncio.run(
                            post(
                                owner.endpoint,
                                actual_route,
                                payload,
                                owner.budget.remaining_seconds,
                            )
                        )
                        if self.path.startswith("/v1"):
                            native = response
                            message = dict(native["message"])
                            if message.get("tool_calls"):
                                message["tool_calls"] = [
                                    {
                                        "id": "call_" + uuid.uuid4().hex,
                                        "type": "function",
                                        "function": {
                                            "name": call["function"]["name"],
                                            "arguments": json.dumps(
                                                call["function"].get("arguments", {})
                                            ),
                                        },
                                    }
                                    for call in message["tool_calls"]
                                ]
                            response = {
                                "id": "chatcmpl_" + uuid.uuid4().hex,
                                "object": "chat.completion",
                                "created": int(time.time()),
                                "model": owner.model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "message": message,
                                        "finish_reason": "tool_calls"
                                        if message.get("tool_calls")
                                        else "length"
                                        if native.get("done_reason") == "length"
                                        else "stop",
                                    }
                                ],
                                "usage": {
                                    "prompt_tokens": native["prompt_eval_count"],
                                    "completion_tokens": native["eval_count"],
                                    "total_tokens": native["prompt_eval_count"]
                                    + native["eval_count"],
                                },
                            }

                        if self.path == "/api/chat":
                            prompt, generated = (
                                response.get("prompt_eval_count"),
                                response.get("eval_count"),
                            )
                            message = response.get("message", {})
                        else:
                            usage = response.get("usage", {})
                            prompt, generated = (
                                usage.get("prompt_tokens"),
                                usage.get("completion_tokens"),
                            )
                            message = response["choices"][0]["message"]
                        if not all(
                            type(value) is int and value >= 0 for value in (prompt, generated)
                        ):
                            raise ValueError("Missing inference usage")
                        if prompt > requested or generated > maximum:
                            raise BudgetExhausted("Provider exceeded token reservation")
                        owner.budget.settle_inference(requested, maximum, prompt, generated)
                        owner.budget.consume(tool_calls=len(message.get("tool_calls") or []))
                        append(
                            owner.log,
                            {
                                "route": self.path,
                                "seconds": time.monotonic() - started,
                                "prompt_tokens": prompt,
                                "output_tokens": generated,
                                "usage": owner.budget.snapshot().model_dump(),
                                "response": response,
                            },
                        )
                        if streaming and self.path == "/api/chat":
                            self.reply(
                                json.dumps(response).encode() + b"\n", "application/x-ndjson"
                            )
                        elif streaming:
                            self.openai_stream(response)
                        else:
                            self.reply(json.dumps(response).encode(), "application/json")
                except Exception as error:
                    owner.error = f"{type(error).__name__}: {error}"
                    append(
                        owner.log,
                        {"error": owner.error, "usage": owner.budget.snapshot().model_dump()},
                    )
                    self.send_error(
                        400 if isinstance(error, BudgetExhausted) else 502,
                        "Inference proxy refused request",
                    )

            def openai_stream(self, response):
                choice = response["choices"][0]
                message = choice["message"]
                for index, call in enumerate(message.get("tool_calls") or []):
                    call["index"] = index
                chunks = []
                for delta, reason in ((message, None), ({}, choice.get("finish_reason", "stop"))):
                    chunk = {
                        "id": response.get("id", "local"),
                        "object": "chat.completion.chunk",
                        "created": response.get("created", 0),
                        "model": owner.model,
                        "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
                    }
                    chunks.append("data: " + json.dumps(chunk) + "\n\n")
                chunks.append(
                    "data: "
                    + json.dumps(
                        {
                            "id": response.get("id", "local"),
                            "object": "chat.completion.chunk",
                            "model": owner.model,
                            "choices": [],
                            "usage": response.get("usage", {}),
                        }
                    )
                    + "\n\n"
                )
                chunks.append("data: [DONE]\n\n")
                self.reply("".join(chunks).encode(), "text/event-stream")

            def reply(self, body: bytes, content_type: str):
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = UnixHTTPServer(str(socket_path), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
