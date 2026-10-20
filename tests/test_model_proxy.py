import httpx

from autocoder.budget import Budget
from autocoder.model_proxy import ModelProxy
from autocoder.protocol import Limits


def test_proxy_enforces_model_routes_and_native_policy(tmp_path, monkeypatch):
    import autocoder.model_proxy

    calls = []

    async def fake_post(endpoint, route, payload, timeout):
        calls.append((route, payload))
        return {
            "message": {"role": "assistant", "content": "ok"},
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 2,
        }

    monkeypatch.setattr(autocoder.model_proxy, "post", fake_post)
    sock = tmp_path / "inference.sock"
    budget = Budget(Limits())
    proxy = ModelProxy(
        sock, "http://localhost:11434", "qwen3.5:9b", budget, tmp_path / "events.jsonl"
    )
    try:
        with httpx.Client(
            transport=httpx.HTTPTransport(uds=str(sock)), base_url="http://local"
        ) as client:
            assert client.get("/private-secrets").status_code == 403
            payload = {
                "model": "qwen3.5:9b",
                "messages": [{"role": "user", "content": "hello"}],
                "think": True,
                "options": {"num_ctx": 4096},
            }
            response = client.post("/v1/chat/completions", json=payload)
            assert response.status_code == 200
            assert response.json()["choices"][0]["message"]["content"] == "ok"
            assert calls[0][0] == "/api/chat"
            assert calls[0][1]["think"] is False
            assert calls[0][1]["options"]["num_ctx"] == 32768
            assert (
                client.post("/api/chat", json=dict(payload, model="unregistered")).status_code
                == 502
            )
            assert len(calls) == 1
    finally:
        proxy.close()
    assert budget.snapshot().request_tokens == 10


def test_proxy_budget_exhaustion_refuses_before_upstream(tmp_path, monkeypatch):
    import autocoder.model_proxy

    calls = []

    async def forbidden(*args):
        calls.append(args)
        raise AssertionError("upstream called")

    monkeypatch.setattr(autocoder.model_proxy, "post", forbidden)
    sock = tmp_path / "inference.sock"
    proxy = ModelProxy(
        sock,
        "http://localhost:11434",
        "qwen3.5:9b",
        Budget(Limits(request_tokens=1)),
        tmp_path / "events.jsonl",
    )
    try:
        with httpx.Client(
            transport=httpx.HTTPTransport(uds=str(sock)), base_url="http://local"
        ) as client:
            response = client.post("/api/chat", json={"model": "qwen3.5:9b", "messages": []})
            assert response.status_code == 400
            assert not calls
            assert "BudgetExhausted" in proxy.error
    finally:
        proxy.close()
