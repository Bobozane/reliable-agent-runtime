from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .reliability import RetryPolicy, call_with_retry


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, str]


class LocalMCPClient:
    """Small MCP-shaped client used when the official SDK is not installed."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, Callable[[dict[str, Any]], Any]]] = {}

    def register(self, spec: ToolSpec, handler: Callable[[dict[str, Any]], Any]) -> None:
        self._tools[spec.name] = (spec, handler)

    def list_tools(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values()]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"unknown MCP tool: {name}")
        return self._tools[name][1](arguments)


class FailurePlan:
    def __init__(self, *, errors: int = 0, timeouts: int = 0) -> None:
        self.errors = errors
        self.timeouts = timeouts


class FaultInjectingMCPClient:
    def __init__(self, inner: LocalMCPClient, plans: dict[str, FailurePlan] | None = None) -> None:
        self.inner = inner
        self.plans = plans or {}

    def list_tools(self) -> list[ToolSpec]:
        return self.inner.list_tools()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        plan = self.plans.get(name)
        if plan and plan.errors:
            plan.errors -= 1
            raise RuntimeError(f"injected tool error: {name}")
        if plan and plan.timeouts:
            plan.timeouts -= 1
            time.sleep(1.0)
        return self.inner.call_tool(name, arguments)


def build_local_client() -> LocalMCPClient:
    client = LocalMCPClient()
    docs = [
        {"id": "i-message", "title": "用观察、感受、需要和请求表达", "text": "描述具体行为，表达自己的感受和需要，再提出可执行请求。"},
        {"id": "boundary", "title": "边界表达", "text": "边界应说明自己的可接受范围和后续行动，而不是威胁或控制对方。"},
        {"id": "repair", "title": "关系修复", "text": "先承认影响，再说明意图，最后讨论下一步具体做法。"},
    ]

    def search(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(arguments.get("query", "")).lower()
        terms = set(query.split())
        scored = []
        for doc in docs:
            score = sum(1 for term in terms if term and term in (doc["title"] + doc["text"]).lower())
            scored.append((score, doc))
        return [doc for _, doc in sorted(scored, key=lambda item: item[0], reverse=True)[:3]]

    saved: dict[str, dict[str, Any]] = {}

    def save_recap(arguments: dict[str, Any]) -> dict[str, Any]:
        key = str(arguments["idempotency_key"])
        if key not in saved:
            saved[key] = {"idempotency_key": key, "reply": str(arguments["reply"]), "saved": True}
        return saved[key]

    client.register(ToolSpec("search_knowledge", "Search local communication principles", {"query": "string"}), search)
    client.register(ToolSpec("save_recap", "Persist a confirmed reply", {"idempotency_key": "string", "reply": "string"}), save_recap)
    return client


def reliable_tool_call(client: Any, name: str, arguments: dict[str, Any], policy: RetryPolicy, fallback: Callable[[Exception], Any] | None = None):
    result = call_with_retry(lambda: client.call_tool(name, arguments), policy, fallback=fallback)
    return result

