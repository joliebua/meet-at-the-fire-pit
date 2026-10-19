"""gpt-6-luna through Portkey, plus exact token accounting from the raw API responses."""
from openai import AsyncOpenAI
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
import httpx2 as httpx  # the HTTP client the openai SDK uses

from backend import config


class UsageRecorder:
    """httpx hook that keeps the exact `usage` object the API returns for every model call."""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, response: httpx.Response) -> None:
        if response.request.url.path.endswith("/responses"):
            await response.aread()
            body = response.json()
            self.calls.append({"response_id": body.get("id"), "usage": body.get("usage"),
                               "portkey_cache": response.headers.get("x-portkey-cache-status", "")})


def build_model(recorder: UsageRecorder) -> OpenAIResponsesModel:
    client = AsyncOpenAI(
        api_key=config.portkey_key(),
        base_url=config.PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": "openai"},
        http_client=httpx.AsyncClient(timeout=120, event_hooks={"response": [recorder]}),
    )
    # Responses API: gpt-6-luna rejects function tools + reasoning on /chat/completions.
    return OpenAIResponsesModel(config.MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def cost_usd(input_tokens: int, cached: int, cache_write: int, output_tokens: int, web_searches: int = 0) -> float:
    p = config.prices()
    uncached = input_tokens - cached - cache_write
    return (uncached * p["input_per_1m"] + cached * p["cached_input_per_1m"]
            + cache_write * p["cache_write_per_1m"] + output_tokens * p["output_per_1m"]) / 1_000_000 \
        + web_searches * p["web_search_per_call"]


def usage_totals(usages: list[dict], web_searches: int = 0, gateway_hits: int = 0) -> dict:
    """Sum raw Responses-API usage objects for one run (pass only calls that reached the model)."""
    t = {"requests": len(usages), "gateway_cache_hits": gateway_hits, "input_tokens": 0, "cached_input_tokens": 0,
         "cache_write_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "web_searches": web_searches}
    for u in usages:
        u = u or {}
        details = u.get("input_tokens_details") or {}
        t["input_tokens"] += u.get("input_tokens", 0)
        t["cached_input_tokens"] += details.get("cached_tokens", 0) or 0
        t["cache_write_tokens"] += details.get("cache_write_tokens", 0) or 0
        t["output_tokens"] += u.get("output_tokens", 0)
        t["reasoning_tokens"] += (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0) or 0
    t["cost_usd"] = round(cost_usd(t["input_tokens"], t["cached_input_tokens"], t["cache_write_tokens"],
                                   t["output_tokens"], web_searches), 6)
    return t


def recorder_totals(recorder: UsageRecorder) -> dict:
    """Usage for a run. Calls answered from Portkey's response cache never reached OpenAI, so they cost nothing."""
    hits = [c for c in recorder.calls if c["portkey_cache"].upper() == "HIT"]
    real = [c["usage"] for c in recorder.calls if c not in hits]
    return usage_totals(real, gateway_hits=len(hits))


def tool_trace(messages, limit: int = 600) -> list[dict]:
    """Every tool call paired with (the start of) its result, in order."""
    calls, results = [], {}
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name != "final_result":
                calls.append(part)
            elif isinstance(part, ToolReturnPart):
                results[part.tool_call_id] = part.content
    return [{"tool": c.tool_name, "arguments": c.args_as_dict(),
             "result": str(results.get(c.tool_call_id, "(no result)"))[:limit]} for c in calls]
