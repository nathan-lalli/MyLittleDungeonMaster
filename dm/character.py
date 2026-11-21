"""Character sheet model and step-by-step creation for D&D 5e (simplified)."""
from __future__ import annotations

ABILITY_NAMES = ("str", "dex", "con", "int", "wis", "cha")
STANDARD_ARRAY = (15, 14, 13, 12, 10, 8)

CLASSES: dict[str, dict] = {
    "barbarian": {"hit_die": 12, "saves": ["str", "con"], "spellcasting": None,  "num_skills": 2, "subclass_level": 3,
                  "skills": ["Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"]},
    "bard":      {"hit_die": 8,  "saves": ["dex", "cha"], "spellcasting": "cha", "num_skills": 3, "subclass_level": 3,
                  "skills": ["any"]},
    "cleric":    {"hit_die": 8,  "saves": ["wis", "cha"], "spellcasting": "wis", "num_skills": 2, "subclass_level": 1,
                  "skills": ["History", "Insight", "Medicine", "Persuasion", "Religion"]},
    "druid":     {"hit_die": 8,  "saves": ["int", "wis"], "spellcasting": "wis", "num_skills": 2, "subclass_level": 2,
                  "skills": ["Arcana", "Animal Handling", "Insight", "Medicine", "Nature", "Perception", "Religion", "Survival"]},
    "fighter":   {"hit_die": 10, "saves": ["str", "con"], "spellcasting": None,  "num_skills": 2, "subclass_level": 3,
                  "skills": ["Acrobatics", "Animal Handling", "Athletics", "History", "Insight", "Intimidation", "Perception", "Survival"]},
    "monk":      {"hit_die": 8,  "saves": ["str", "dex"], "spellcasting": None,  "num_skills": 2, "subclass_level": 3,
                  "skills": ["Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"]},
    "paladin":   {"hit_die": 10, "saves": ["wis", "cha"], "spellcasting": "cha", "num_skills": 2, "subclass_level": 3,
                  "skills": ["Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"]},
    "ranger":    {"hit_die": 10, "saves": ["str", "dex"], "spellcasting": "wis", "num_skills": 3, "subclass_level": 3,
                  "skills": ["Animal Handling", "Athletics", "Insight", "Investigation", "Nature", "Perception", "Stealth", "Survival"]},
    "rogue":     {"hit_die": 8,  "saves": ["dex", "int"], "spellcasting": None,  "num_skills": 4, "subclass_level": 3,
                  "skills": ["Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation",
                             "Perception", "Performance", "Persuasion", "Sleight of Hand", "Stealth"]},
    "sorcerer":  {"hit_die": 6,  "saves": ["con", "cha"], "spellcasting": "cha", "num_skills": 2, "subclass_level": 1,
                  "skills": ["Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"]},
    "warlock":   {"hit_die": 8,  "saves": ["wis", "cha"], "spellcasting": "cha", "num_skills": 2, "subclass_level": 1,
                  "skills": ["Arcana", "Deception", "History", "Intimidation", "Investigation", "Nature", "Religion"]},
    "wizard":    {"hit_die": 6,  "saves": ["int", "wis"], "spellcasting": "int", "num_skills": 2, "subclass_level": 2,
                  "skills": ["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"]},
}

# Human-readable label for the subclass choice prompt
SUBCLASS_LABELS = {
    "cleric":   "Divine Domain",
    "sorcerer": "Sorcerous Origin",
    "warlock":  "Otherworldly Patron",
}

SUBCLASS_SUGGESTIONS = {
    "cleric":   ["Life", "Light", "Trickery", "Knowledge", "Nature", "Tempest", "War"],
    "sorcerer": ["Draconic Bloodline", "Wild Magic"],
    "warlock":  ["The Archfey", "The Fiend", "The Great Old One"],
}

RACES = ["Dragonborn", "Dwarf", "Elf", "Gnome", "Half-Elf", "Half-Orc", "Halfling", "Human", "Tiefling"]

BACKGROUNDS = [
    "Acolyte", "Charlatan", "Criminal", "Entertainer", "Folk Hero", "Guild Artisan",
    "Hermit", "Noble", "Outlander", "Sage", "Sailor", "Soldier", "Urchin",
]

# Base AC at level 1 (chain mail for heavily-armoured martials, leather/none for others)
_BASE_AC = {
    "barbarian": 10, "bard": 11, "cleric": 13, "druid": 11, "fighter": 16,
    "monk": 10, "paladin": 16, "ranger": 13, "rogue": 11, "sorcerer": 10,
    "warlock": 11, "wizard": 10,
}
# Classes that add DEX modifier to their starting AC
_DEX_AC = {"bard", "druid", "monk", "ranger", "rogue", "sorcerer", "warlock", "wizard"}
# Barbarian Unarmored Defense adds both DEX and CON — handled as a special case in _do_scores

# Races with non-standard movement speed
_RACE_SPEED = {"Dwarf": 25, "Halfling": 25, "Gnome": 25}

# Spell slots by class type and character level (levels 1–10).
# "full" = cleric, druid, bard, sorcerer, wizard
# "half" = paladin, ranger (rounded down; they get slots from level 2)
_FULL_CASTER_SLOTS: dict[int, dict[str, dict]] = {
    1:  {"1": {"total": 2, "used": 0}},
    2:  {"1": {"total": 3, "used": 0}},
    3:  {"1": {"total": 4, "used": 0}, "2": {"total": 2, "used": 0}},
    4:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}},
    5:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 2, "used": 0}},
    6:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 3, "used": 0}},
    7:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 3, "used": 0}, "4": {"total": 1, "used": 0}},
    8:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 3, "used": 0}, "4": {"total": 2, "used": 0}},
    9:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 3, "used": 0}, "4": {"total": 3, "used": 0}, "5": {"total": 1, "used": 0}},
    10: {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 3, "used": 0}, "4": {"total": 3, "used": 0}, "5": {"total": 2, "used": 0}},
}
_HALF_CASTER_SLOTS: dict[int, dict[str, dict]] = {
    1:  {},
    2:  {"1": {"total": 2, "used": 0}},
    3:  {"1": {"total": 3, "used": 0}},
    4:  {"1": {"total": 3, "used": 0}},
    5:  {"1": {"total": 4, "used": 0}, "2": {"total": 2, "used": 0}},
    6:  {"1": {"total": 4, "used": 0}, "2": {"total": 2, "used": 0}},
    7:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}},
    8:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}},
    9:  {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 2, "used": 0}},
    10: {"1": {"total": 4, "used": 0}, "2": {"total": 3, "used": 0}, "3": {"total": 2, "used": 0}},
}
_FULL_CASTERS = {"cleric", "druid", "bard", "sorcerer", "wizard"}
_HALF_CASTERS = {"paladin", "ranger"}


def _new_spell_slots(cls: str, level: int) -> dict:
    """Return a fresh spell-slot dict (deep-copied) for the given class and level."""
    if cls in _FULL_CASTERS:
        return {k: dict(v) for k, v in _FULL_CASTER_SLOTS.get(min(level, 10), {}).items()}
    if cls in _HALF_CASTERS:
        return {k: dict(v) for k, v in _HALF_CASTER_SLOTS.get(min(level, 10), {}).items()}
    return {}


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int = 1) -> int:
    return (level - 1) // 4 + 2


def max_hp(class_name: str, con_score: int, level: int = 1) -> int:
    hit_die = CLASSES.get(class_name, {}).get("hit_die", 8)
    con_mod = ability_modifier(con_score)
    return hit_die + con_mod + (level - 1) * (hit_die // 2 + 1 + con_mod)


def character_summary(char: dict) -> str:
    """Compact one-liner injected into the DM context prompt each turn.

    Intentionally omits raw ability scores — that detail is only needed on the
    full character sheet, not in every system prompt on a 4k-context Pi.
    """
    name = char.get("name", "?")
    race = char.get("race", "?")
    cls  = char.get("class", "?").title()
    sub  = char.get("subclass", "")
    lvl  = char.get("level", 1)
    hp   = char.get("hp", {})
    ac   = char.get("ac", "?")
    spd  = char.get("speed", 30)

    sub_str = f" ({sub})" if sub else ""
    hp_str  = f"{hp.get('current', '?')}/{hp.get('max', '?')}"
    cur_hp, max_hp_ = hp.get("current", 1), hp.get("max", 1)
    if cur_hp == 0:
        hp_flag = " [DOWN]"
    elif max_hp_ and cur_hp <= max_hp_ // 2:
        hp_flag = " [WOUNDED]"
    else:
        hp_flag = ""

    return f"{name}: Lvl {lvl} {race} {cls}{sub_str} | HP {hp_str}{hp_flag} | AC {ac} | Speed {spd}ft"


def format_sheet(char: dict) -> str:
    """Full readable character sheet for terminal display."""
    name   = char.get("name", "?")
    race   = char.get("race", "?")
    cls    = char.get("class", "?").title()
    sub    = char.get("subclass", "")
    lvl    = char.get("level", 1)
    bg     = char.get("background", "?")
    hp     = char.get("hp", {})
    ac     = char.get("ac", "?")
    speed  = char.get("speed", 30)
    prof   = char.get("proficiency_bonus", proficiency_bonus(lvl))
    scores = char.get("ability_scores", {})
    saves  = char.get("saving_throws", [])
    skills = char.get("skill_proficiencies", [])

    sub_str = f" ({sub})" if sub else ""
    hp_str  = f"{hp.get('current', '?')}/{hp.get('max', '?')}"
    sep = "-" * 52

    lines = [
        sep,
        f" {name} — Level {lvl} {race} {cls}{sub_str}",
        sep,
        f" Background: {bg}  |  AC: {ac}  |  HP: {hp_str}  |  Speed: {speed}ft  |  Prof: +{prof}",
    ]

    save_strs = []
    for ab in saves:
        m = ability_modifier(scores.get(ab, 10)) + prof
        save_strs.append(f"{ab.upper()} ({'+'if m>=0 else ''}{m})")
    if save_strs:
        lines.append(f" Saving throws: {', '.join(save_strs)}")
    if skills:
        lines.append(f" Skills: {', '.join(skills)}")

    lines.append("")
    lines.append(" Ability Scores:")
    score_parts = []
    for ab in ABILITY_NAMES:
        s = scores.get(ab, 10)
        m = ability_modifier(s)
        score_parts.append(f"{ab.upper()} {s:2d} ({'+'if m>=0 else ''}{m})")
    lines.append("   " + "    ".join(score_parts[:3]))
    lines.append("   " + "    ".join(score_parts[3:]))

    sp_ab = CLASSES.get(char.get("class", ""), {}).get("spellcasting")
    if sp_ab:
        sp_mod = ability_modifier(scores.get(sp_ab, 10))
        dc = 8 + prof + sp_mod
        atk = prof + sp_mod
        lines.append(f"\n Spellcasting: {sp_ab.upper()}  |  Spell save DC {dc}  |  Spell attack +{atk}")
        spells = char.get("spells", {}) or {}
        if spells.get("cantrips"):
            lines.append(f"   Cantrips: {', '.join(spells['cantrips'])}")
        if spells.get("prepared"):
            lines.append(f"   Prepared: {', '.join(spells['prepared'])}")
        if spells.get("slots"):
            slot_parts = []
            for lvl_key in sorted(spells["slots"], key=lambda x: int(x)):
                s = spells["slots"][lvl_key]
                rem = s.get("total", 0) - s.get("used", 0)
                slot_parts.append(f"L{lvl_key}: {rem}/{s.get('total', 0)}")
            lines.append(f"   Slots: {', '.join(slot_parts)}")
        notes = spells.get("domain_notes", "").strip()
        if notes:
            lines.append(f"   {notes[:200]}")

    p = char.get("personality", {})
    p_lines = [(k.title(), p.get(k, "").strip()) for k in ("trait", "ideal", "bond", "flaw")]
    p_lines = [(k, v) for k, v in p_lines if v]
    if p_lines:
        lines.append("")
        for k, v in p_lines:
            lines.append(f" {k}: {v}")

    feats = char.get("features", {})
    for k in ("race", "subclass", "background"):
        v = feats.get(k, "").strip()
        if v:
            lines.append(f"\n {k.title()} features: {v[:200]}")

    notes_text = char.get("notes", "").strip()
    lines.append(f"\n Notes: {notes_text if notes_text else '(none)'}")
    lines.append(sep)
    return "\n".join(lines)


def spell_info(char: dict) -> str:
    """Spellcasting summary for display."""
    cls = char.get("class", "")
    sp_ab = CLASSES.get(cls, {}).get("spellcasting")
    name = char.get("name", "?")
    if not sp_ab:
        return f"{name} is not a spellcaster."

    scores = char.get("ability_scores", {})
    lvl  = char.get("level", 1)
    prof = char.get("proficiency_bonus", proficiency_bonus(lvl))
    sp_score = scores.get(sp_ab, 10)
    sp_mod   = ability_modifier(sp_score)
    dc  = 8 + prof + sp_mod
    atk = prof + sp_mod
    sub = char.get("subclass", "")
    sub_str = f" ({sub})" if sub else ""

    lines = [
        f"{name}'s Spells — {cls.title()}{sub_str}",
        f"Spellcasting ability: {sp_ab.upper()} {sp_score} (modifier {'+'if sp_mod>=0 else ''}{sp_mod})",
        f"Spell save DC: {dc}  |  Spell attack bonus: +{atk}",
    ]
    spells = char.get("spells", {}) or {}
    cantrips = spells.get("cantrips", [])
    prepared = spells.get("prepared", [])
    slots    = spells.get("slots", {})
    notes    = spells.get("domain_notes", "").strip()
    if cantrips:
        lines.append(f"Cantrips: {', '.join(cantrips)}")
    if prepared:
        lines.append(f"Prepared: {', '.join(prepared)}")
    if slots:
        slot_parts = []
        for lvl_key in sorted(slots, key=lambda x: int(x)):
            s = slots[lvl_key]
            remaining = s.get("total", 0) - s.get("used", 0)
            slot_parts.append(f"L{lvl_key}: {remaining}/{s.get('total', 0)}")
        lines.append(f"Slots: {', '.join(slot_parts)}")
    if notes:
        lines.append(f"Domain/subclass notes: {notes[:300]}")
    if not (cantrips or prepared or slots or notes):
        lines.append("(No spell list stored — spells are looked up during character creation)")
    return "\n".join(lines)


def spell_info_tts(char: dict) -> str:
    """Short, speakable spell summary for TTS — no markdown, no colons, no slash notation."""
    cls  = char.get("class", "")
    sp_ab = CLASSES.get(cls, {}).get("spellcasting")
    name = char.get("name", "?")
    if not sp_ab:
        return f"{name} is not a spellcaster."
    spells   = char.get("spells", {}) or {}
    slots    = spells.get("slots") or {}
    cantrips = spells.get("cantrips", [])
    prepared = spells.get("prepared", [])
    _ORD = {"1": "first", "2": "second", "3": "third", "4": "fourth", "5": "fifth",
            "6": "sixth", "7": "seventh", "8": "eighth", "9": "ninth"}
    parts = []
    for key in sorted(slots, key=lambda x: int(x)):
        s = slots[key]
        remaining = s.get("total", 0) - s.get("used", 0)
        total     = s.get("total", 0)
        ord_str   = _ORD.get(key, f"level {key}")
        parts.append(f"{remaining} of {total} {ord_str}-level slots")
    if cantrips:
        n = len(cantrips)
        parts.append(f"{n} cantrip{'s' if n != 1 else ''}")
    if prepared:
        n = len(prepared)
        parts.append(f"{n} spell{'s' if n != 1 else ''} prepared")
    if not parts:
        return f"{name} has no spells loaded yet."
    return f"{name} has " + ", ".join(parts) + "."


def apply_damage(char: dict, amount: int) -> tuple[dict, str]:
    hp = char.get("hp", {"max": 0, "current": 0})
    new_hp = max(0, hp.get("current", 0) - amount)
    updated = dict(char, hp=dict(hp, current=new_hp))
    name = char.get("name", "them")
    if new_hp == 0:
        msg = f"{name} takes {amount} damage and falls to 0 HP!"
    else:
        msg = f"{name} takes {amount} damage. HP: {new_hp}/{hp.get('max', '?')}"
    return updated, msg


def apply_heal(char: dict, amount: int) -> tuple[dict, str]:
    hp = char.get("hp", {"max": 0, "current": 0})
    max_val  = hp.get("max", 0)
    new_hp   = min(max_val, hp.get("current", 0) + amount)
    updated  = dict(char, hp=dict(hp, current=new_hp))
    msg = f"{char.get('name', 'them')} heals {amount} HP. HP: {new_hp}/{max_val}"
    return updated, msg


def apply_long_rest(char: dict) -> tuple[dict, str]:
    hp = char.get("hp", {"max": 0, "current": 0})
    max_val = hp.get("max", 0)
    # Reset used spell slot counts
    spells = char.get("spells") or {}
    slots  = spells.get("slots") or {}
    if slots:
        reset_slots = {k: dict(v, used=0) for k, v in slots.items()}
        spells = dict(spells, slots=reset_slots)
    updated = dict(char, hp=dict(hp, current=max_val), spells=spells)
    msg = f"{char.get('name', 'them')}: HP restored to {max_val}/{max_val}. Spell slots refreshed."
    return updated, msg


def apply_short_rest(char: dict, num_dice: int = 1) -> tuple[dict, str]:
    cls     = char.get("class", "fighter")
    hit_die = CLASSES.get(cls, {}).get("hit_die", 8)
    con_mod = ability_modifier(char.get("ability_scores", {}).get("con", 10))
    hp_gain = max(1, hit_die // 2 + 1 + con_mod) * num_dice
    hp      = char.get("hp", {"max": 0, "current": 0})
    max_val = hp.get("max", 0)
    new_hp  = min(max_val, hp.get("current", 0) + hp_gain)
    actual  = new_hp - hp.get("current", 0)
    updated = dict(char, hp=dict(hp, current=new_hp))
    name    = char.get("name", "them")
    die_str = f"{num_dice} hit {'die' if num_dice == 1 else 'dice'} (d{hit_die})"
    msg     = f"{name} spends {die_str}, regaining {actual} HP. HP: {new_hp}/{max_val}"
    return updated, msg


def do_level_up(char: dict) -> tuple[dict, str]:
    new_lvl  = char.get("level", 1) + 1
    cls      = char.get("class", "fighter")
    hit_die  = CLASSES.get(cls, {}).get("hit_die", 8)
    con_mod  = ability_modifier(char.get("ability_scores", {}).get("con", 10))
    hp_gain  = max(1, hit_die // 2 + 1 + con_mod)
    hp       = char.get("hp", {"max": 0, "current": 0})
    new_max  = hp.get("max", 0) + hp_gain
    new_cur  = hp.get("current", 0) + hp_gain
    new_prof = proficiency_bonus(new_lvl)
    updated  = dict(char, level=new_lvl, hp=dict(hp, max=new_max, current=new_cur),
                    proficiency_bonus=new_prof)

    # Update spell slots to match the new level
    new_slots = _new_spell_slots(cls, new_lvl)
    if new_slots:
        spells = dict(updated.get("spells") or {})
        spells["slots"] = new_slots
        updated = dict(updated, spells=spells)

    name = char.get("name", "them")
    msg = (f"{name} reached level {new_lvl}! "
           f"+{hp_gain} HP (now {new_cur}/{new_max}). "
           f"Proficiency bonus: +{new_prof}.")

    # Prompt for subclass if this is the level it's chosen and none is set yet
    sub_level = CLASSES.get(cls, {}).get("subclass_level", 3)
    if new_lvl == sub_level and not char.get("subclass"):
        suggestions = SUBCLASS_SUGGESTIONS.get(cls, [])
        label = SUBCLASS_LABELS.get(cls, "subclass")
        hint = f" Options: {', '.join(suggestions)}." if suggestions else ""
        msg += f"\n[Choose a {label}!{hint} Say: set subclass to <name>]"

    return updated, msg


class CharacterCreator:
    """
    Step-by-step D&D 5e character builder implemented as a state machine.

    Usage in a game loop:
        creator = CharacterCreator(lookup_fn=lookup.lookup)
        say(creator.start())
        while creator.active:
            response, done = creator.advance(player_input())
            say(response)
        char = creator.character   # None if cancelled
    """

    def __init__(self, lookup_fn=None):
        self._lookup = lookup_fn
        self._step = "name"
        self._d: dict = {}
        self._char: dict | None = None

    @property
    def active(self) -> bool:
        return self._step != "_done"

    @property
    def character(self) -> dict | None:
        return self._char

    def start(self) -> str:
        return (
            "Let's build your character. Say 'cancel' at any step to stop.\n\n"
            "What is your character's name?"
        )

    def advance(self, answer: str) -> tuple[str, bool]:
        """Process the player's answer. Returns (message, is_done)."""
        answer = answer.strip()
        if answer.lower() == "cancel":
            self._step = "_done"
            return "Character creation cancelled.", True
        handler = getattr(self, f"_do_{self._step}", None)
        if handler is None:
            return "Something went wrong with character creation.", True
        return handler(answer)

    # ---- step handlers -------------------------------------------------------

    def _do_name(self, answer: str):
        if not answer:
            return "Please enter a name.", False
        self._d["name"] = answer.title()
        opts = ", ".join(RACES) + " — or type any other race"
        self._step = "race"
        return f"What race is {self._d['name']}?\nOptions: {opts}", False

    def _do_race(self, answer: str):
        self._d["race"] = answer.strip().title()
        msg = self._fetch("race", self._d["race"])
        self._step = "class"
        return f"{msg}What class?\nOptions: {', '.join(c.title() for c in CLASSES)}", False

    def _do_class(self, answer: str):
        cls = answer.strip().lower()
        if cls not in CLASSES:
            for key in CLASSES:
                if cls.startswith(key[:4]) or key.startswith(cls[:4]):
                    cls = key
                    break
            else:
                return f"Unknown class. Options: {', '.join(c.title() for c in CLASSES)}", False
        self._d["class"] = cls
        cls_info = CLASSES[cls]
        msg = self._fetch("class", cls)

        if cls_info["subclass_level"] == 1:
            label = SUBCLASS_LABELS.get(cls, "Subclass")
            subs = SUBCLASS_SUGGESTIONS.get(cls, [])
            opts = ", ".join(subs) + " — or type any other" if subs else "type your subclass"
            self._step = "subclass"
            return f"{msg}{cls.title()}s choose their {label} at 1st level.\nOptions: {opts}", False

        sub_lvl = cls_info["subclass_level"]
        label = SUBCLASS_LABELS.get(cls, "subclass")
        self._step = "background"
        return (
            f"{msg}{cls.title()}s choose their {label} at level {sub_lvl}.\n\n"
            f"What background?\nOptions: {', '.join(BACKGROUNDS)} — or custom"
        ), False

    def _do_subclass(self, answer: str):
        self._d["subclass"] = answer.strip().title()
        msg = self._fetch("subclass", f"{self._d['class']} {self._d['subclass']}")
        self._step = "background"
        return f"{msg}What background?\nOptions: {', '.join(BACKGROUNDS)} — or custom", False

    def _do_background(self, answer: str):
        self._d["background"] = answer.strip().title()
        msg = self._fetch("background", self._d["background"])
        array_str = " ".join(str(n) for n in STANDARD_ARRAY)
        self._step = "scores"
        return (
            f"{msg}Assign the standard array ({array_str}) to your ability scores.\n"
            "Enter six space-separated numbers for: STR DEX CON INT WIS CHA\n"
            "Example: 8 12 13 10 15 14"
        ), False

    def _do_scores(self, answer: str):
        scores = self._parse_scores(answer)
        if scores is None:
            return "Enter exactly 6 numbers between 1 and 20 for STR DEX CON INT WIS CHA.", False

        warn = ""
        if sorted(scores.values(), reverse=True) != list(STANDARD_ARRAY):
            warn = f"(Note: standard array is {list(STANDARD_ARRAY)} — using your values)\n"
        self._d["ability_scores"] = scores

        cls = self._d["class"]
        cls_info = CLASSES[cls]
        level = 1
        dex_mod = ability_modifier(scores["dex"])
        con_mod = ability_modifier(scores["con"])
        wis_mod = ability_modifier(scores["wis"])
        if cls == "barbarian":
            ac = 10 + dex_mod + con_mod  # Unarmored Defense: 10 + DEX + CON
        elif cls == "monk":
            ac = 10 + dex_mod + wis_mod  # Unarmored Defense: 10 + DEX + WIS
        else:
            ac = _BASE_AC.get(cls, 10) + (dex_mod if cls in _DEX_AC else 0)
        hp_max = max_hp(cls, scores["con"], level)
        prof = proficiency_bonus(level)

        race  = self._d.get("race", "")
        speed = _RACE_SPEED.get(race, 30)
        slots = _new_spell_slots(cls, level)
        self._d.update({
            "level": level,
            "hp": {"max": hp_max, "current": hp_max},
            "ac": ac,
            "speed": speed,
            "proficiency_bonus": prof,
            "saving_throws": cls_info["saves"],
        })
        # Seed spell slots for spellcasting classes
        if slots:
            self._d.setdefault("spells", {})["slots"] = slots

        mods_str = "  ".join(
            f"{ab.upper()} {scores[ab]}({'+'if ability_modifier(scores[ab])>=0 else ''}{ability_modifier(scores[ab])})"
            for ab in ABILITY_NAMES
        )

        cls_skills = cls_info["skills"]
        n = cls_info["num_skills"]
        if cls_skills == ["any"]:
            skill_q = f"Choose {n} skill proficiencies (any skills)"
        else:
            skill_q = f"Choose {n} skill proficiencie(s) from: {', '.join(cls_skills)}"

        self._step = "skills"
        return (
            f"{warn}Scores set: {mods_str}\n"
            f"HP: {hp_max}  AC: {ac}  Proficiency: +{prof}\n\n"
            + skill_q
        ), False

    def _do_skills(self, answer: str):
        # Split on commas (supports multi-word skills like "Sleight of Hand")
        raw_chosen = [s.strip() for s in answer.split(",") if s.strip()]
        cls_info   = CLASSES.get(self._d.get("class", ""), {})
        allowed    = cls_info.get("skills", ["any"])
        num_needed = cls_info.get("num_skills", 2)

        if len(raw_chosen) != num_needed:
            return f"Choose exactly {num_needed} skill(s), separated by commas. Got {len(raw_chosen)}.", False

        if allowed == ["any"]:
            chosen = [s.title() for s in raw_chosen]
        else:
            # Build a case-insensitive lookup to canonical spelling
            canonical = {s.lower(): s for s in allowed}
            bad = [s for s in raw_chosen if s.lower() not in canonical]
            if bad:
                return (f"'{', '.join(bad)}' not in class skill list.\n"
                        f"Choose from: {', '.join(allowed)}"), False
            chosen = [canonical[s.lower()] for s in raw_chosen]

        self._d["skill_proficiencies"] = chosen
        self._step = "trait"
        return (
            "Almost done — a few personality details. Say 'skip' to leave any blank.\n\n"
            "Personality trait (a habit or quirk):"
        ), False

    def _do_trait(self, answer: str):
        self._d.setdefault("personality", {})["trait"] = "" if answer.lower() == "skip" else answer
        self._step = "ideal"
        return "Ideal (a belief or principle):", False

    def _do_ideal(self, answer: str):
        self._d["personality"]["ideal"] = "" if answer.lower() == "skip" else answer
        self._step = "bond"
        return "Bond (a person, place, or thing they're devoted to):", False

    def _do_bond(self, answer: str):
        self._d["personality"]["bond"] = "" if answer.lower() == "skip" else answer
        self._step = "flaw"
        return "Flaw (a weakness or bad habit):", False

    def _do_flaw(self, answer: str):
        self._d["personality"]["flaw"] = "" if answer.lower() == "skip" else answer
        return self._finish()

    # ---- helpers -------------------------------------------------------

    def _finish(self) -> tuple[str, bool]:
        char = {k: v for k, v in self._d.items() if not k.startswith("_")}
        char.setdefault("subclass", "")
        char.setdefault("personality", {})
        char.setdefault("skill_proficiencies", [])
        char["features"] = {
            k: self._d.get(f"_feat_{k}", "")
            for k in ("race", "class", "subclass", "background")
        }
        cls = char.get("class", "")
        # Preserve any spell slots seeded by _do_scores; just add domain notes on top
        existing_spells = char.get("spells") or {}
        if CLASSES.get(cls, {}).get("spellcasting"):
            char["spells"] = dict(existing_spells, domain_notes=self._d.get("_feat_subclass", ""))
        else:
            char["spells"] = {}
        char["notes"] = ""
        self._char = char
        self._step = "_done"

        name = char["name"]
        cls_disp = cls.title()
        sub_disp = f" ({char['subclass']})" if char.get("subclass") else ""
        return f"{name} the {char['race']} {cls_disp}{sub_disp} is ready. They join the party!", True

    def _fetch(self, entity_type: str, name: str) -> str:
        """Call the lookup function and return a brief description string to show the player."""
        if not self._lookup:
            return ""
        print(f"[looking up {entity_type}: {name}...]", flush=True)
        result = self._lookup(entity_type, name)
        if not result:
            return ""
        desc = result.get("desc") or result.get("document__title") or ""
        if not desc:
            return ""
        preview = str(desc).replace("\r\n", " ").replace("\n", " ").strip()[:220]
        self._d[f"_feat_{entity_type}"] = preview
        return f"{result.get('name', name)}: {preview}...\n\n"

    @staticmethod
    def _parse_scores(raw: str) -> dict | None:
        parts = raw.split()
        if len(parts) != 6:
            return None
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return None
        if not all(1 <= n <= 20 for n in nums):
            return None
        return dict(zip(ABILITY_NAMES, nums))
