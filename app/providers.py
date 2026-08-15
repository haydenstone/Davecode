"""AENIMUS provider adapters v0.1.0."""

import os
import json
import httpx
from .config import settings


DEFAULT_PROVIDERS = {
    "ollama": {
        "label": "Local Ollama",
        "base_url": settings.ollama_url,
        "api_key_env": None,
    },
    "openai": {
        "label": "OpenAI compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
}
try:
    for key, value in json.loads(settings.providers_json).items():
        DEFAULT_PROVIDERS[key] = {
            "label": value.get("label", key),
            "base_url": value["base_url"],
            "api_key_env": value.get("api_key_env"),
            "protocol": value.get("protocol", "openai"),
        }
except (ValueError, TypeError, KeyError):
    pass


async def list_models(provider):
    spec = DEFAULT_PROVIDERS[provider]
    headers = _headers(spec)
    url = spec["base_url"].rstrip("/") + (
        "/api/tags" if provider == "ollama" else "/models"
    )
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
    rows = data.get("models", data.get("data", []))
    return [{"id": x.get("name", x.get("id")), "size": x.get("size")} for x in rows]


def _headers(spec):
    env = spec.get("api_key_env")
    key = os.getenv(env) if env else None
    return {"Authorization": f"Bearer {key}"} if key else {}


async def complete(agent, messages):
    spec = DEFAULT_PROVIDERS.get(agent["provider"])
    if not spec:
        raise ValueError("Unknown provider")
    system = (
        f"{agent.get('persona', '')}\n\nMission: {agent.get('mission', '')}".strip()
    )
    payload_messages = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-agent.get("memory", {}).get("retain_turns", 24) :]
        if m["role"] in ("user", "assistant")
    ]
    async with httpx.AsyncClient(timeout=120) as client:
        if agent["provider"] == "ollama" or spec.get("protocol") == "ollama":
            r = await client.post(
                spec["base_url"].rstrip("/") + "/api/chat",
                json={
                    "model": agent["model"],
                    "messages": payload_messages,
                    "stream": False,
                    "options": {
                        "temperature": agent["temperature"],
                        "num_ctx": agent["context_window"],
                        **agent.get("tuning", {}),
                    },
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
        r = await client.post(
            spec["base_url"].rstrip("/") + "/chat/completions",
            headers=_headers(spec),
            json={
                "model": agent["model"],
                "messages": payload_messages,
                "temperature": agent["temperature"],
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
