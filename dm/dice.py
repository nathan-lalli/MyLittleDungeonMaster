"""Dice are rolled in code, never by the LLM (small models cannot be trusted with randomness)."""
import random
import re
from dataclasses import dataclass

_DICE = re.compile(r"(?P<n>\d+)?\s*d\s*(?P<s>\d+)\s*(?P<mod>[+-]\s*\d+)?", re.I)
_ADV = re.compile(r"\b(with advantage|advantage)\b", re.I)
_DIS = re.compile(r"\b(with disadvantage|disadvantage)\b", re.I)

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


@dataclass
class RollResult:
    expr: str
    rolls: list
    modifier: int
    total: int
    note: str = ""

    def describe(self):
        mod = f" {self.modifier:+d}" if self.modifier else ""
        extra = f" ({self.note})" if self.note else ""
        return f"{self.expr}: {self.rolls}{mod} = {self.total}{extra}"

    def speak(self):
        return f"You rolled {self.total}."


def parse_roll(text, rng=random):
    """Return a RollResult if `text` contains a dice expression, else None.

    Handles: "roll 2d6+3", "d20", "roll a d20 with advantage", "roll two d8".
    Speech-to-text often writes 'D 20' or 'd-20'; the regex tolerates spaces.
    """
    t = text.lower().replace("d-", "d").replace("dee ", "d")
    for word, num in _NUMBER_WORDS.items():
        t = re.sub(rf"\b{word}\s+(?=d\s*\d)", f"{num}", t)
    m = _DICE.search(t)
    if not m:
        return None
    n = int(m.group("n") or 1)
    sides = int(m.group("s"))
    if not (1 <= n <= 50 and 2 <= sides <= 1000):
        return None
    mod = int(m.group("mod").replace(" ", "")) if m.group("mod") else 0

    adv, dis = bool(_ADV.search(t)), bool(_DIS.search(t))
    if (adv ^ dis) and n == 1 and sides == 20:
        a, b = rng.randint(1, sides), rng.randint(1, sides)
        keep = max(a, b) if adv else min(a, b)
        return RollResult(f"d20", [keep], mod, keep + mod, f"{'advantage' if adv else 'disadvantage'}: {a},{b}")

    rolls = [rng.randint(1, sides) for _ in range(n)]
    expr = f"{n}d{sides}"
    return RollResult(expr, rolls, mod, sum(rolls) + mod)
