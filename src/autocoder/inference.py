"""Finite Ollama transport with conservative token reservations and total deadlines."""

import asyncio
import json
import time
import urllib.parse

import httpx

from autocoder.budget import Budget, BudgetExhausted


class InferenceError(RuntimeError):
    pass


async def post(endpoint: str, route: str, payload: dict, timeout: float) -> dict:
    parsed = urllib.parse.urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Endpoint must be an HTTP(S) origin without credentials")
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=timeout
        ) as client:
            async with client.stream(
                "POST", endpoint.rstrip("/") + route, json=payload
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 4_000_000:
                        raise InferenceError("Inference response exceeded byte cap")
                return json.loads(body)


async def infer(
    endpoint: str,
    model: str,
    messages: list[dict],
    budget: Budget,
    *,
    context: int,
    think: bool = False,
    tools: list[dict] | None = None,
    api: str = "native",
    schema: dict | None = None,
    max_output: int = 512,
) -> dict:
    if len(messages) > 64:
        raise InferenceError("Message count exceeds the qualified token-overhead bound")
    rendered = json.dumps({"messages": messages, "tools": tools, "schema": schema}).encode()
    # Each UTF-8 byte is an upper bound of one text token; reserve extra template overhead.
    request_reservation = len(rendered) + 1024
    if request_reservation + max_output > context:
        raise BudgetExhausted("request cannot fit the conservative context bound")
    budget.consume(request_tokens=request_reservation, output_tokens=max_output)
    if api == "native":
        route = "/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": think,
            "keep_alive": "5m",
            "options": {
                "num_ctx": context,
                "num_predict": max_output,
                "temperature": 0,
                "seed": 42,
            },
        }
        if tools:
            payload["tools"] = tools
        if schema:
            payload["format"] = schema
    elif api == "openai":
        route = "/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": 0,
            "seed": 42,
            "max_tokens": max_output,
            "think": think,
            "options": {"num_ctx": context},
        }
        if tools:
            payload["tools"] = tools
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema,
                },
            }
    else:
        raise ValueError(f"Unsupported inference API: {api}")
    started = time.monotonic()
    # No automatic replay: a timeout may have reached inference; record it as ambiguous.
    try:
        response = await post(endpoint, route, payload, budget.remaining_seconds)
    except TimeoutError as error:
        raise BudgetExhausted("wall_seconds; inference cancelled, no source mutation") from error
    except (httpx.HTTPError, json.JSONDecodeError) as error:
        raise InferenceError(f"{type(error).__name__}; inference not replayed") from error
    _ = budget.remaining_seconds
    if api == "native":
        prompt_tokens = response.get("prompt_eval_count")
        output_tokens = response.get("eval_count")
        message = response.get("message", {})
        finished = response.get("done") is True
        reason = response.get("done_reason")
    else:
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        choices = response.get("choices", [])
        message = choices[0].get("message", {}) if choices else {}
        reason = choices[0].get("finish_reason") if choices else None
        finished = bool(choices)
    if not all(type(value) is int and value >= 0 for value in (prompt_tokens, output_tokens)):
        raise InferenceError("Missing trustworthy usage metrics; reservations remain charged")
    if prompt_tokens > request_reservation or output_tokens > max_output:
        raise BudgetExhausted("Provider exceeded reserved token cap; response cannot be accepted")
    budget.settle_inference(request_reservation, max_output, prompt_tokens, output_tokens)
    return {
        "message": message,
        "raw": response,
        "elapsed_seconds": time.monotonic() - started,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "truncated": reason == "length",
        "finished": finished,
    }
