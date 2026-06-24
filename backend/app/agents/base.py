"""
BaseAgent — shared foundation for all LLM agents in the FDD Engine.

Responsibilities:
  - Holds the OpenAI async client (one per process, shared across agents)
  - Enforces the mock/real mode switch via USE_MOCK_LLM
  - Provides _call() with exponential-backoff retry for transient API errors
  - Tracks token usage per call for cost visibility
  - Enforces the golden rule: agents never receive DataFrames or return raw numbers
    for arithmetic — inputs and outputs are always Pydantic models or plain dicts

Subclasses override:
  _mock_response(payload) -> dict   used when USE_MOCK_LLM=true
  _build_messages(payload) -> list  the prompt construction
  _parse_response(raw) -> dict      extract structured data from tool-call response
"""

import asyncio
import logging
import time
from typing import Any

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic, RateLimitError

from app.config import settings

logger = logging.getLogger(__name__)

# Singleton async client — created once, reused across all agents
_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


class AgentError(Exception):
    pass


class BaseAgent:
    """
    Abstract base for all FDD LLM agents.

    Usage pattern:
        agent = SomeAgent()
        result = await agent.run(payload)

    Subclasses must implement: _build_messages, _tools, _parse_response, _mock_response
    """

    #: Override in subclass with the OpenAI function/tool definitions
    _tools: list[dict] = []

    #: Name used in logs
    name: str = "BaseAgent"

    async def run(self, payload: Any) -> Any:
        """
        Entry point. Dispatches to mock or real depending on USE_MOCK_LLM.
        Wraps _call with logging and timing.
        """
        if settings.use_mock_llm:
            logger.debug("[%s] MOCK mode — returning fixture response", self.name)
            return self._mock_response(payload)

        start = time.monotonic()
        result = await self._call(payload)
        elapsed = time.monotonic() - start
        logger.info("[%s] completed in %.2fs", self.name, elapsed)
        return result

    async def _call(self, payload: Any, *, max_retries: int = 3) -> Any:
        """Call the Anthropic API with retry on transient errors."""
        messages = self._build_messages(payload)
        last_exc: Exception | None = None

        # 1. Extract system prompt if present in messages (Anthropic expects it as a top-level parameter)
        system_prompt: str | None = None
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.get("role") == "system":
                system_prompt = m.get("content")
            else:
                api_messages.append({
                    "role": m["role"],
                    "content": m["content"]
                })

        # 2. Format tools from OpenAI format to Anthropic format if self._tools is set
        anthropic_tools = []
        if self._tools:
            for tool in self._tools:
                if tool.get("type") == "function" and "function" in tool:
                    func = tool["function"]
                    anthropic_tools.append({
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                    })
                else:
                    anthropic_tools.append(tool)

        for attempt in range(max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": settings.anthropic_model,
                    "messages": api_messages,
                    "temperature": 0.0,
                    "max_tokens": 4000,
                }
                if system_prompt:
                    kwargs["system"] = system_prompt
                if anthropic_tools:
                    kwargs["tools"] = anthropic_tools
                    kwargs["tool_choice"] = {"type": "any"}

                resp = await get_client().messages.create(**kwargs)

                usage = resp.usage
                if usage:
                    logger.info(
                        "[%s] tokens — input: %d, output: %d, total: %d",
                        self.name, usage.input_tokens, usage.output_tokens,
                        usage.input_tokens + usage.output_tokens,
                    )

                return self._parse_response(resp)

            except RateLimitError as exc:
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning("[%s] rate limited — retrying in %ds (attempt %d)", self.name, wait, attempt + 1)
                await asyncio.sleep(wait)
                last_exc = exc

            except APIConnectionError as exc:
                wait = 2 ** attempt * 2
                logger.warning("[%s] connection error — retrying in %ds", self.name, wait)
                await asyncio.sleep(wait)
                last_exc = exc

            except APIStatusError as exc:
                # 4xx errors are not retryable
                raise AgentError(f"[{self.name}] API error {exc.status_code}: {exc.message}") from exc

        raise AgentError(
            f"[{self.name}] failed after {max_retries} attempts: {last_exc}"
        ) from last_exc

    # ── Subclass interface ────────────────────────────────────────────────────

    def _build_messages(self, payload: Any) -> list[dict]:
        raise NotImplementedError

    def _parse_response(self, response: Any) -> Any:
        raise NotImplementedError

    def _mock_response(self, payload: Any) -> Any:
        raise NotImplementedError
