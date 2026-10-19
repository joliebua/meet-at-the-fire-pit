"""Read every agent run from output/runs/ and decide which ones were really billed.

A run counts as billed when it reached the model (requests > 0 with input tokens) and took at least
MIN_BILLED_SECONDS. A few early runs were logged before Portkey cache hits were tracked: they show
several model calls finishing in about a second, which only a gateway cache replay can do, so they
are excluded instead of being counted as spend twice.
"""
import json

from backend import config

MIN_BILLED_SECONDS = 3.0


def load_runs() -> list[dict]:
    runs = []
    for f in sorted((config.OUTPUT / "runs").glob("*.json")):
        data = json.loads(f.read_text())
        run = data.get("run", data)
        u = run.get("usage", {})
        parts = [u["scout_agent"], u["web_search_tool"]] if "scout_agent" in u else [u]
        row = {"file": f.name, "agent": run.get("agent", f.stem.split("_")[0]), "week": run.get("week"),
               "mode": run.get("mode"), "self_correct": run.get("self_correct"), "seconds": run.get("seconds", 0),
               "requests": parts[0].get("requests", 0), "gateway_cache_hits": parts[0].get("gateway_cache_hits", 0),
               "web_searches": sum(p.get("web_searches", 0) for p in parts),
               "web_search_input_tokens": parts[1].get("input_tokens", 0) if len(parts) > 1 else 0}
        for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "cost_usd"):
            row[k] = sum(p.get(k, 0) for p in parts)
        row["billed"] = row["requests"] > 0 and row["input_tokens"] > 0 and row["seconds"] >= MIN_BILLED_SECONDS
        runs.append(row)
    return runs


def per_agent(runs: list[dict] | None = None) -> dict[str, dict]:
    """Averages over billed runs, plus counts of free (cache/blocked) runs."""
    out: dict[str, dict] = {}
    for r in runs if runs is not None else load_runs():
        a = out.setdefault(r["agent"], {"runs": 0, "free_runs": 0, "cost_usd": 0.0, "input_tokens": 0,
                                        "cached_input_tokens": 0, "output_tokens": 0, "seconds": 0.0,
                                        "gateway_cache_hits": 0, "web_searches": 0})
        a["gateway_cache_hits"] += r["gateway_cache_hits"]
        if not r["billed"]:
            a["free_runs"] += 1
            continue
        a["runs"] += 1
        for k in ("cost_usd", "input_tokens", "cached_input_tokens", "output_tokens", "seconds", "web_searches"):
            a[k] += r[k]
    for a in out.values():
        n = max(a["runs"], 1)
        a["avg_cost_usd"] = round(a["cost_usd"] / n, 6)
        a["avg_seconds"] = round(a["seconds"] / n, 1)
        a["avg_input_tokens"] = round(a["input_tokens"] / n)
        a["avg_cached_input_tokens"] = round(a["cached_input_tokens"] / n)
        a["avg_output_tokens"] = round(a["output_tokens"] / n)
        a["cost_usd"] = round(a["cost_usd"], 6)
        a["seconds"] = round(a["seconds"], 1)
    return out
