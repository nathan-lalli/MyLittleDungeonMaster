"""Config loading with defaults and ~ expansion."""
import copy
import os

import yaml

DEFAULTS = {
    "llm": {
        "base_url": "http://127.0.0.1:8080/v1",
        "model": "local",
        "temperature": 0.8,
        "top_p": 0.95,
        "max_tokens": 200,
        "timeout_s": 300,
        "system_suffix": "",
    },
    "stt": {
        "binary": "~/whisper.cpp/build/bin/whisper-cli",
        "model": "~/whisper.cpp/models/ggml-base.en.bin",
        "threads": 3,
        "remote_url": "",
    },
    "audio": {
        "sample_rate": 16000,
        "device": None,
        "vad_energy_threshold": 500,
        "silence_ms": 900,
        "max_utterance_s": 25,
        "push_to_talk": False,
    },
    "tts": {
        "enabled": True,
        "piper_cmd": ["piper", "--model", "~/voices/en_US-lessac-medium.onnx", "--output-raw"],
        "player_cmd": ["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
        "voices": {},
    },
    "memory": {
        "campaigns_dir": "data/campaigns",
        "keep_recent_messages": 8,
        "summarize_after": 14,
        "state_block_chars": 1200,
    },
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def expand(value):
    """Expand ~ in strings and lists of strings."""
    if isinstance(value, str):
        return os.path.expanduser(value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    return value


def load_config(path=None):
    user = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, user)
    for section in ("llm", "stt", "tts", "memory"):
        for k, v in cfg[section].items():
            cfg[section][k] = expand(v)
    return cfg
