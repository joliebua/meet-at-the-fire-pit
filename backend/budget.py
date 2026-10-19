"""App-wide spending guard, on top of each agent's own per-run limits.

Before any agent runs from the web app:
  * daily budget: billed model spend so far today (UTC, from output/runs) must be under VILLA_DAILY_BUDGET_USD
  * rate limit: at most VILLA_MAX_AGENT_RUNS agent runs in any VILLA_RATE_WINDOW_SECONDS window, so repeated
    clicks or a misbehaving script can't keep running agents
Both are environment settings with safe defaults, so a grader clicking around can't run up a bill.
"""
from collections import deque
from datetime import datetime, timezone
import os
import threading
import time

from backend import usage_log


class BudgetExceeded(RuntimeError):
    pass


def daily_budget() -> float:
    return float(os.getenv("VILLA_DAILY_BUDGET_USD", "1.00"))


def max_runs() -> int:
    return int(os.getenv("VILLA_MAX_AGENT_RUNS", "30"))


def window_seconds() -> int:
    return int(os.getenv("VILLA_RATE_WINDOW_SECONDS", "600"))


_recent: deque[float] = deque()
_lock = threading.Lock()


def spent_today() -> float:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return sum(r["cost_usd"] for r in usage_log.load_runs()
               if r["billed"] and r["file"].rsplit("_", 1)[-1].startswith(today))


def check(now: float | None = None, budget: float | None = None, limit: int | None = None, window: int | None = None) -> None:
    """Raise BudgetExceeded if today's spend or the recent run count is over the line; otherwise count this run."""
    now = now if now is not None else time.monotonic()
    budget = daily_budget() if budget is None else budget
    limit = max_runs() if limit is None else limit
    window = window_seconds() if window is None else window
    spent = spent_today()
    if spent >= budget:
        raise BudgetExceeded(f"Today's AI budget is used up (${spent:.4f} of ${budget:.2f}). It resets at midnight UTC.")
    with _lock:
        while _recent and now - _recent[0] > window:
            _recent.popleft()
        if len(_recent) >= limit:
            wait = int(window - (now - _recent[0])) + 1
            raise BudgetExceeded(f"Too many AI runs in a row ({limit} per {window // 60} min). Try again in {wait}s.")
        _recent.append(now)


def status() -> dict:
    return {"spent_today_usd": round(spent_today(), 6), "daily_budget_usd": daily_budget(),
            "max_agent_runs": max_runs(), "window_seconds": window_seconds()}
