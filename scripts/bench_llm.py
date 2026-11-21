"""Benchmark a running llama-server on THIS Pi: time-to-first-token and tokens/sec.

    python scripts/bench_llm.py --base-url http://127.0.0.1:8080/v1 --runs 3

Run it once per candidate model (swap the GGUF in llama-server) and record the results in README's table.
Chunk count is used as a proxy for tokens (llama-server streams roughly one token per SSE delta).
"""
import argparse
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dm.prompts import DM_SYSTEM  # noqa: E402

SCENARIO = ("WORLD NOTES:\nNPC: Mara - a nervous innkeeper\nPlace: The Gilded Stag - a roadside inn\n\n"
            "STORY SO FAR:\nThe party arrived at the inn during a storm and heard strange noises from the cellar.")


def run(base, max_tokens):
    msgs = [{"role": "system", "content": DM_SYSTEM + "\n\n" + SCENARIO},
            {"role": "user", "content": "I draw my sword and carefully walk down the cellar stairs."}]
    t0 = time.time()
    first, n = None, 0
    with requests.post(f"{base}/chat/completions", stream=True, timeout=600,
                       json={"model": "local", "messages": msgs, "stream": True, "max_tokens": max_tokens}) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:") or raw.endswith("[DONE]"):
                continue
            try:
                delta = json.loads(raw[5:])["choices"][0]["delta"].get("content")
            except (KeyError, IndexError, ValueError):
                continue
            if delta:
                n += 1
                first = first or time.time()
    end = time.time()
    if not first:
        return None
    return first - t0, n, (n - 1) / max(end - first, 1e-6)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=120)
    a = ap.parse_args()
    for i in range(a.runs):
        res = run(a.base_url.rstrip("/"), a.max_tokens)
        print(f"run {i + 1}: " + ("no output" if not res else f"TTFT {res[0]:.1f}s | {res[1]} tokens | {res[2]:.2f} tok/s"))
