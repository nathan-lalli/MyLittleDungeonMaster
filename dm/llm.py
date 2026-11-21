"""Client for llama.cpp's `llama-server` (OpenAI-compatible HTTP API).

Using HTTP keeps the LLM swappable and lets it live on a different Pi than the voice node.
Ollama, or any other OpenAI-compatible server, also works by changing llm.base_url.
"""
import json
import threading

import requests


class LLMClient:
    def __init__(self, cfg):
        self.base = cfg["base_url"].rstrip("/")
        self.model = cfg["model"]
        self.temperature = cfg["temperature"]
        self.top_p = cfg["top_p"]
        self.max_tokens = cfg["max_tokens"]
        self.timeout = cfg["timeout_s"]
        self.suffix = cfg.get("system_suffix", "")
        # One Pi = one generation at a time. The lock keeps the background "scribe" from colliding with the DM.
        self._lock = threading.Lock()

    def _payload(self, messages, stream, **kw):
        if self.suffix and messages and messages[0]["role"] == "system":
            messages = [dict(messages[0], content=messages[0]["content"] + "\n" + self.suffix)] + messages[1:]
        p = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": kw.pop("temperature", self.temperature),
            "top_p": self.top_p,
            "max_tokens": kw.pop("max_tokens", self.max_tokens),
        }
        p.update(kw)
        return p

    def stream(self, messages, **kw):
        """Yield text chunks as they are generated."""
        with self._lock:
            r = requests.post(
                f"{self.base}/chat/completions",
                json=self._payload(messages, True, **kw),
                stream=True,
                timeout=self.timeout,
            )
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue
                if delta:
                    yield delta

    def complete(self, messages, **kw):
        with self._lock:
            r = requests.post(
                f"{self.base}/chat/completions",
                json=self._payload(messages, False, **kw),
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()

    def extract_json(self, messages, schema, **kw):
        """Ask for schema-constrained JSON. Returns dict or None (callers must tolerate None).

        Uses llama-server's response_format/json_schema support (grammar-constrained decoding), which matters
        a lot for 1-3B models that otherwise produce malformed JSON. VERIFY on your llama.cpp build.
        """
        try:
            text = self.complete(
                messages,
                temperature=0.2,
                response_format={"type": "json_schema", "json_schema": {"name": "extract", "schema": schema, "strict": True}},
                **kw,
            )
            return json.loads(text)
        except (requests.RequestException, ValueError, KeyError):
            return None
