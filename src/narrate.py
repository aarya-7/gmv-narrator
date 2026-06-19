"""
LLM narration layer — the ONLY place the Anthropic API is called.

The LLM receives a pre-computed fact packet and turns it into language.
It does not detect anomalies, do attribution math, or see raw data.
"""
import os
import pathlib
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

from config import MODEL_NAME

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a business intelligence narrator for an e-commerce analytics platform.
You are given PRE-COMPUTED anomaly detection and segment attribution results. You do not have access
to raw data and must not invent numbers, segments, or causes that are not in the input.

Write the insight in exactly three labeled sections:
1. WHAT HAPPENED — one sentence: the metric, the direction, the magnitude vs baseline, the date.
2. WHY — two to three sentences naming the top contributing segments and their direction and share
   of the move. Use only the drivers provided. If a historical note is present, reference it briefly.
3. RECOMMENDED ACTION — one concrete, specific next step for the data or business team
   (e.g. which segment to investigate first, what to check). No generic advice.

Rules: Be direct. State facts, not speculation. No hedging ("it appears", "might suggest").
Do not output any number that is not derivable from the input. Keep it under 120 words total."""


def _build_user_prompt(ctx: dict) -> str:
    drivers_text = "\n".join(
        f"- {d['segment']}: {d['contribution_pct']:+.1f}% of the total move "
        f"(segment itself {d['pct_change']:+.1f}% vs baseline), direction={d['direction']}"
        for d in ctx["top_drivers"]
        if d["contribution_pct"] is not None and d["pct_change"] is not None
    )
    hist = ctx.get("historical_note") or "None on record."
    days = ctx.get("days_since_last_anomaly")
    days_note = f" ({days} days since last anomaly)" if days is not None else ""

    return (
        f"Anomaly on {ctx['date']}{days_note}. Metric: {ctx['metric']}. "
        f"Direction: {ctx['direction']}, severity: {ctx['severity']} (z={ctx['z_score']}).\n"
        f"Actual: {ctx['actual_value']:,.0f} vs baseline {ctx['baseline_value']:,.0f} "
        f"({ctx['pct_change']:+.1f}%).\n"
        f"Decomposed by: {ctx['decomposed_by']}.\n"
        f"Top contributing segments:\n{drivers_text}\n"
        f"Historical note: {hist}\n\n"
        f"Write the insight."
    )


def narrate(ctx: dict) -> str:
    resp = client.messages.create(
        model=MODEL_NAME,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(ctx)}],
    )
    return resp.content[0].text
