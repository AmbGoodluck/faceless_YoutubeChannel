"""
Amadu Studios — Shared LLM Interface
Thin wrapper around the existing Claude API client.
All agents call gen_json() or call_claude() from here.
"""
from __future__ import annotations
import os, sys, json, re, time, requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config


def call_claude(system: str, user: str) -> str:
    body = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": config.CLAUDE_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content":
                      user + "\n\nReturn ONLY the JSON object — no prose, no markdown fences."}],
    }
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    delay = 5
    for attempt in range(7):
        try:
            r = requests.post(config.CLAUDE_ENDPOINT, headers=headers, json=body, timeout=180)
        except requests.RequestException as e:
            time.sleep(delay); delay = min(delay * 2, 120); continue
        if r.status_code in (429, 500, 502, 503, 529):
            time.sleep(int(r.headers.get("retry-after", delay))); delay = min(delay*2,120); continue
        r.raise_for_status()
        data = r.json()
        return "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
    raise RuntimeError("Claude API unavailable after 7 retries")


def _extract_json(raw: str) -> str:
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end+1] if start != -1 else raw


def gen_json(system: str, user: str, attempts: int = 3) -> dict:
    last = None
    for i in range(attempts):
        try:
            return json.loads(_extract_json(call_claude(system, user)))
        except (json.JSONDecodeError, KeyError) as e:
            last = e
            print(f"[llm] bad JSON (try {i+1}/{attempts}): {e}")
            time.sleep(3)
    raise RuntimeError(f"Claude returned unparseable JSON after {attempts} tries: {last}")
