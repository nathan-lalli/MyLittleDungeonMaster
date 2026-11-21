"""Streaming text helpers: split LLM output into speakable sentences as it arrives."""
import re

_SENT = re.compile(r"(.+?[.!?][\"')\]]*)\s+", re.S)
_MARKDOWN = re.compile(r"[*_#`>]+")


def split_sentences(buffer):
    """Return (complete_sentences, remainder). A sentence is complete only once whitespace follows it."""
    sentences, last_end = [], 0
    for m in _SENT.finditer(buffer):
        sentences.append(m.group(1).strip())
        last_end = m.end()
    return sentences, buffer[last_end:]


def clean_for_speech(text):
    return _MARKDOWN.sub("", text).replace("\n", " ").strip()


class SentenceBatcher:
    """Merge very short sentences so TTS gets natural-length chunks (fewer pauses between Piper calls)."""

    def __init__(self, min_chars=40):
        self.min_chars = min_chars
        self.pending = ""

    def add(self, sentence):
        self.pending = f"{self.pending} {sentence}".strip()
        if len(self.pending) >= self.min_chars:
            out, self.pending = self.pending, ""
            return out
        return None

    def flush(self):
        out, self.pending = self.pending, ""
        return out or None
