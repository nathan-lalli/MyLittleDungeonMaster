import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dm.character import (  # noqa: E402
    CharacterCreator, apply_damage, apply_heal, apply_long_rest,
    apply_short_rest, do_level_up, format_sheet, spell_info, spell_info_tts,
)
from dm.config import load_config  # noqa: E402
from dm.dice import parse_roll  # noqa: E402
from dm.game import Game  # noqa: E402
from dm.memory import Memory  # noqa: E402
from dm.textutil import SentenceBatcher, split_sentences  # noqa: E402
from dm.tts import NullSpeaker  # noqa: E402


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def stream(self, messages, **kw):
        self.calls += 1
        for tok in ["The door ", "creaks open. ", "Mara gasps! ", "What do you do?"]:
            yield tok

    def complete(self, messages, **kw):
        return "The party met Mara at the inn."

    def extract_json(self, messages, schema, **kw):
        return {"npcs": [{"name": "Mara", "description": "nervous innkeeper"}],
                "locations": [{"name": "Gilded Stag", "description": "roadside inn"}],
                "quests": [{"name": "Cellar noises", "status": "active"}], "facts": ["The party owes Mara a favor."]}


def make_game(tmp_path):
    cfg = load_config(None)
    return Game(cfg, FakeLLM(), Memory(str(tmp_path / "c.db")), NullSpeaker(), log=lambda *_: None)


def test_split_sentences_streaming():
    s, rest = split_sentences("Hello there. How are you? I am")
    assert s == ["Hello there.", "How are you?"] and rest == "I am"


def test_batcher_merges_short():
    b = SentenceBatcher(min_chars=20)
    assert b.add("Hi.") is None
    assert b.add("This is a longer sentence.") is not None


def test_dice_basic_and_modifier():
    r = parse_roll("roll 2d6+3", random.Random(1))
    assert len(r.rolls) == 2 and r.total == sum(r.rolls) + 3


def test_dice_advantage_and_stt_variants():
    r = parse_roll("I roll a d 20 with advantage", random.Random(2))
    assert r.expr == "d20" and "advantage" in r.note
    assert parse_roll("roll two d8", random.Random(3)).expr == "2d8"
    assert parse_roll("I open the door") is None


def test_full_turn_updates_memory(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    g.handle("I walk into the inn")
    g.wait_idle()
    names = {e["name"] for e in g.mem.entities()}
    assert {"Mara", "Gilded Stag", "Cellar noises"} <= names
    block = g.mem.state_block()
    assert "Mara" in block and "owes Mara" in block


def test_persistence_across_restart(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    g.handle("hello")
    g.wait_idle()
    mem2 = Memory(str(tmp_path / "c.db"))
    assert mem2.turn == g.mem.turn and len(mem2.unsummarized()) == len(g.mem.unsummarized())


def test_summarization_folds_old_messages(tmp_path):
    g = make_game(tmp_path)
    g.mcfg["summarize_after"], g.mcfg["keep_recent_messages"] = 4, 2
    g.start_campaign("test")
    for i in range(4):
        g.handle(f"action {i}")
    g.wait_idle()
    assert g.mem.latest_summary()
    assert len(g.mem.unsummarized()) <= 4


def test_dice_command_and_character(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    g.handle("my character is Thorin, a dwarf fighter")
    assert any(e["name"] == "Thorin" for e in g.mem.entities("pc"))
    g.handle("roll a d20")
    assert "I rolled" in g.mem.unsummarized()[-2]["content"]


# ---------------------------------------------------------------------------
# Character stat functions
# ---------------------------------------------------------------------------

def _make_char(**overrides):
    base = {
        "name": "Thorin",
        "race": "Dwarf",
        "class": "fighter",
        "subclass": "Champion",
        "level": 1,
        "hp": {"max": 12, "current": 12},
        "ac": 16,
        "speed": 30,
        "ability_scores": {"str": 16, "dex": 12, "con": 15, "int": 10, "wis": 13, "cha": 8},
        "proficiency_bonus": 2,
        "saving_throws": ["str", "con"],
        "skill_proficiencies": ["Athletics"],
        "background": "Soldier",
        "personality": {},
        "features": {},
        "spells": {},
        "notes": "",
    }
    base.update(overrides)
    return base


def test_apply_damage_reduces_hp():
    char = _make_char()
    updated, msg = apply_damage(char, 3)
    assert updated["hp"]["current"] == 9
    assert "9/12" in msg


def test_apply_damage_cannot_go_below_zero():
    char = _make_char(hp={"max": 12, "current": 2})
    updated, msg = apply_damage(char, 10)
    assert updated["hp"]["current"] == 0


def test_apply_heal_restores_hp():
    char = _make_char(hp={"max": 12, "current": 5})
    updated, msg = apply_heal(char, 4)
    assert updated["hp"]["current"] == 9
    assert "9/12" in msg


def test_apply_heal_caps_at_max():
    char = _make_char(hp={"max": 12, "current": 10})
    updated, msg = apply_heal(char, 20)
    assert updated["hp"]["current"] == 12


def test_apply_long_rest_restores_full_hp():
    char = _make_char(hp={"max": 12, "current": 3})
    updated, msg = apply_long_rest(char)
    assert updated["hp"]["current"] == 12
    assert "Thorin" in msg


def test_apply_short_rest_restores_partial_hp():
    char = _make_char(hp={"max": 20, "current": 5})
    updated, msg = apply_short_rest(char, 1)
    assert updated["hp"]["current"] > 5
    assert updated["hp"]["current"] <= 20
    assert "d10" in msg  # fighter hit die


def test_apply_short_rest_multiple_dice():
    char = _make_char(hp={"max": 20, "current": 1})
    updated, msg = apply_short_rest(char, 3)
    # 3 dice worth of healing (capped at max)
    assert updated["hp"]["current"] > 1


def test_do_level_up():
    char = _make_char()
    updated, msg = do_level_up(char)
    assert updated["level"] == 2
    assert updated["hp"]["max"] > 12
    assert "level 2" in msg.lower()
    assert updated["proficiency_bonus"] >= 2


def test_format_sheet_contains_key_fields():
    char = _make_char()
    sheet = format_sheet(char)
    assert "Thorin" in sheet
    assert "fighter" in sheet.lower()
    assert "HP" in sheet
    assert "AC" in sheet


def test_spell_info_no_spells():
    char = _make_char()
    info = spell_info(char)
    assert "not a spellcaster" in info.lower() or "no spells" in info.lower() or "fighter" in info.lower()


def test_spell_info_with_spells():
    char = _make_char(
        **{
            "class": "cleric",
            "spells": {
                "slots": {"1": {"total": 2, "used": 0}},
                "cantrips": ["Guidance", "Sacred Flame"],
                "prepared": ["Cure Wounds", "Bless"],
            },
        }
    )
    info = spell_info(char)
    assert "Cure Wounds" in info or "Guidance" in info


# ---------------------------------------------------------------------------
# Memory character persistence
# ---------------------------------------------------------------------------

def test_memory_save_and_retrieve_character(tmp_path):
    mem = Memory(str(tmp_path / "c.db"))
    mem.next_turn()
    char = _make_char()
    mem.save_character(char)
    retrieved = mem.get_character("Thorin")
    assert retrieved is not None
    assert retrieved["name"] == "Thorin"
    assert retrieved["hp"]["max"] == 12


def test_memory_all_characters(tmp_path):
    mem = Memory(str(tmp_path / "c.db"))
    mem.next_turn()
    mem.save_character(_make_char(name="Thorin"))
    mem.save_character(_make_char(name="Lyra", **{"class": "cleric"}))
    all_chars = mem.all_characters()
    names = {c["name"] for c in all_chars}
    assert names == {"Thorin", "Lyra"}


def test_save_character_no_entity_injection(tmp_path):
    """save_character must NOT call upsert_entity — that caused double party injection."""
    mem = Memory(str(tmp_path / "c.db"))
    mem.next_turn()
    mem.save_character(_make_char())
    pc_entities = mem.entities("pc")
    assert not any(e["name"] == "Thorin" for e in pc_entities)


def test_list_campaigns_no_ddl_side_effect(tmp_path):
    """list_campaigns should work on a fresh (schema-less) path without crashing."""
    campaigns = Memory.list_campaigns(str(tmp_path))
    assert campaigns == []


# ---------------------------------------------------------------------------
# Game engine — character commands
# ---------------------------------------------------------------------------

def test_game_damage_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_char()
    g.mem.save_character(char)
    g.handle("Thorin takes 5 damage")
    updated = g.mem.get_character("Thorin")
    assert updated["hp"]["current"] == 7


def test_game_heal_command_requires_hp_unit(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_char(hp={"max": 12, "current": 5})
    g.mem.save_character(char)
    g.handle("regain 3 hp")
    updated = g.mem.get_character("Thorin")
    assert updated["hp"]["current"] == 8


def test_game_long_rest_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_char(hp={"max": 12, "current": 3})
    g.mem.save_character(char)
    g.handle("long rest")
    updated = g.mem.get_character("Thorin")
    assert updated["hp"]["current"] == 12


def test_game_short_rest_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_char(hp={"max": 20, "current": 5})
    g.mem.save_character(char)
    g.handle("short rest")
    updated = g.mem.get_character("Thorin")
    assert updated["hp"]["current"] > 5


def test_game_level_up_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_char()
    g.mem.save_character(char)
    g.handle("level up")
    updated = g.mem.get_character("Thorin")
    assert updated["level"] == 2


def test_game_party_show_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    g.mem.save_character(_make_char())
    result = g.handle("show the party")
    assert "Thorin" in result


def test_game_character_sheet_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    g.mem.save_character(_make_char())
    result = g.handle("character sheet")
    assert "Thorin" in result
    assert "HP" in result


def test_game_help_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    result = g.handle("help")
    assert "long rest" in result.lower()
    assert "damage" in result.lower()


def test_game_add_note_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    g.mem.save_character(_make_char())
    g.handle("add note for Thorin: hates spiders")
    updated = g.mem.get_character("Thorin")
    assert "hates spiders" in updated["notes"]


# ---------------------------------------------------------------------------
# CharacterCreator state machine
# ---------------------------------------------------------------------------

def test_character_creator_cancel():
    creator = CharacterCreator(lookup_fn=None)
    creator.start()
    msg, done = creator.advance("cancel")
    assert done
    assert creator.character is None


def test_character_creator_happy_path():
    creator = CharacterCreator(lookup_fn=None)
    prompt = creator.start()
    assert "name" in prompt.lower()

    msg, done = creator.advance("Lyra")
    assert not done and "race" in msg.lower()

    msg, done = creator.advance("Half-Elf")
    assert not done and "class" in msg.lower()

    msg, done = creator.advance("Cleric")
    assert not done  # subclass/background step

    msg, done = creator.advance("Life")
    assert not done and "background" in msg.lower()

    msg, done = creator.advance("Acolyte")
    assert not done and ("scores" in msg.lower() or "str" in msg.lower())

    msg, done = creator.advance("8 12 13 10 15 14")
    assert not done and "skill" in msg.lower()

    msg, done = creator.advance("Insight, Religion")
    assert not done  # personality steps

    # Skip all 4 personality sub-steps
    creator.advance("")
    creator.advance("")
    creator.advance("")
    msg, done = creator.advance("")
    assert done

    char = creator.character
    assert char is not None
    assert char["name"] == "Lyra"
    assert char["race"] == "Half-Elf"
    assert char["class"] == "cleric"
    assert char["hp"]["max"] > 0
    assert char["level"] == 1


def test_character_creator_skills_multiword(tmp_path):
    """Comma-delimited input must correctly parse multi-word skills."""
    creator = CharacterCreator(lookup_fn=None)
    creator.start()
    creator.advance("Rogue")          # name
    creator.advance("Human")          # race
    creator.advance("Rogue")          # class
    creator.advance("Thief")          # subclass
    creator.advance("Criminal")       # background
    creator.advance("8 14 12 13 10 10")  # scores
    # Rogue needs 4 skills; use comma-delimited multi-word skills
    msg, done = creator.advance("Stealth, Sleight of Hand, Deception, Perception")
    assert not done
    # advance through personality
    creator.advance("")
    creator.advance("")
    creator.advance("")
    creator.advance("")
    char = creator.character
    assert char is not None
    assert "Sleight Of Hand" in char.get("skill_proficiencies", []) or \
           "Sleight of Hand" in char.get("skill_proficiencies", [])


def test_barbarian_ac_uses_con(tmp_path):
    """Barbarian Unarmored Defense = 10 + DEX mod + CON mod, not 11 + DEX only."""
    creator = CharacterCreator(lookup_fn=None)
    creator.start()
    creator.advance("Grom")           # name
    creator.advance("Half-Orc")       # race
    creator.advance("Barbarian")      # class
    creator.advance("")               # subclass (skip)
    creator.advance("Outlander")      # background
    # STR 15, DEX 14 (+2), CON 16 (+3), INT 8, WIS 10, CHA 12
    creator.advance("15 14 16 8 10 12")
    # Barbarian needs 2 skills from its allowed list
    creator.advance("Perception, Athletics")
    creator.advance("")
    creator.advance("")
    creator.advance("")
    creator.advance("")
    char = creator.character
    assert char is not None
    # 10 + 2 (DEX) + 3 (CON) = 15
    assert char["ac"] == 15


# ---------------------------------------------------------------------------
# Barbarian AC unit test (pure function path)
# ---------------------------------------------------------------------------

def test_barbarian_unarmored_defense():
    """apply_long_rest preserves the barbarian's AC after a rest."""
    char = _make_char(**{"class": "barbarian", "ac": 15})
    updated, _ = apply_long_rest(char)
    assert updated["ac"] == 15  # AC is not modified by rest


# ---------------------------------------------------------------------------
# Spell slot tracking
# ---------------------------------------------------------------------------

def _make_cleric(**overrides):
    base = _make_char(**{
        "class": "cleric",
        "spells": {
            "slots": {"1": {"total": 2, "used": 0}},
            "cantrips": ["Guidance"],
            "prepared": ["Cure Wounds"],
        },
    })
    base.update(overrides)
    return base


def test_spell_slots_seeded_during_character_creation():
    """Slots set by _do_scores must survive _finish() unchanged."""
    creator = CharacterCreator(lookup_fn=None)
    creator.start()
    creator.advance("Lyra")       # name
    creator.advance("Human")      # race
    creator.advance("Cleric")     # class → subclass_level 1 → goes to subclass step
    creator.advance("Life")       # subclass
    creator.advance("Acolyte")    # background
    creator.advance("8 12 13 10 15 14")   # scores — seeds spell slots
    creator.advance("Insight, Religion")  # 2 skills for cleric
    creator.advance("skip")       # trait
    creator.advance("skip")       # ideal
    creator.advance("skip")       # bond
    creator.advance("skip")       # flaw
    char = creator.character
    assert char is not None
    slots = char.get("spells", {}).get("slots", {})
    assert "1" in slots, "Level 1 spell slots should be seeded"
    assert slots["1"]["total"] > 0


def test_long_rest_resets_used_spell_slots():
    char = _make_cleric(hp={"max": 10, "current": 3})
    char["spells"]["slots"]["1"]["used"] = 2
    updated, msg = apply_long_rest(char)
    assert updated["spells"]["slots"]["1"]["used"] == 0
    assert updated["hp"]["current"] == 10
    assert "refreshed" in msg.lower()


def test_long_rest_no_slots_still_restores_hp():
    char = _make_char(hp={"max": 12, "current": 5})  # fighter, no slots
    updated, msg = apply_long_rest(char)
    assert updated["hp"]["current"] == 12


def test_level_up_advances_spell_slots():
    char = _make_cleric()
    char["level"] = 2
    # At level 3, full casters gain L2 slots
    char["level"] = 2
    updated, msg = do_level_up(char)
    assert updated["level"] == 3
    slots = updated.get("spells", {}).get("slots", {})
    assert "2" in slots, "Level 3 cleric should have L2 spell slots"


def test_cast_spell_decrements_slot(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_cleric()
    g.mem.save_character(char)
    result = g.handle("cast a level 1 spell")
    updated = g.mem.get_character("Thorin")
    assert updated["spells"]["slots"]["1"]["used"] == 1
    assert "1 of 2" in result


def test_cast_spell_no_slots_remaining(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_cleric()
    char["spells"]["slots"]["1"]["used"] = 2  # all used
    g.mem.save_character(char)
    result = g.handle("cast a level 1 spell")
    updated = g.mem.get_character("Thorin")
    assert updated["spells"]["slots"]["1"]["used"] == 2  # unchanged
    assert "no level 1 slots" in result.lower()


def test_spell_info_tts_compact():
    char = _make_cleric()
    tts = spell_info_tts(char)
    assert "first-level" in tts.lower()
    assert "/" not in tts   # no "2/4" slash notation in spoken output
    assert "Thorin" in tts


def test_set_subclass_command(tmp_path):
    g = make_game(tmp_path)
    g.start_campaign("test")
    char = _make_char(subclass="")  # fighter with no subclass
    g.mem.save_character(char)
    g.handle("set subclass to Champion")
    updated = g.mem.get_character("Thorin")
    assert updated["subclass"] == "Champion"


def test_monk_ac_uses_wis():
    """Monk Unarmored Defense = 10 + DEX mod + WIS mod."""
    creator = CharacterCreator(lookup_fn=None)
    creator.start()
    creator.advance("Kai")          # name
    creator.advance("Human")        # race
    creator.advance("Monk")         # class (subclass_level=3 → goes to background)
    creator.advance("Hermit")       # background
    # STR 10, DEX 16 (+3), CON 12, INT 10, WIS 15 (+2), CHA 8
    creator.advance("10 16 12 10 15 8")
    # Monk needs 2 skills from its list
    creator.advance("Acrobatics, Insight")
    creator.advance("skip")
    creator.advance("skip")
    creator.advance("skip")
    creator.advance("skip")
    char = creator.character
    assert char is not None
    # 10 + DEX(+3) + WIS(+2) = 15
    assert char["ac"] == 15


def test_zero_hp_flag():
    """Character at 0 HP should show [DOWN] not [WOUNDED]."""
    from dm.character import character_summary
    char = _make_char(hp={"max": 12, "current": 0})
    summary = character_summary(char)
    assert "[DOWN]" in summary
    assert "[WOUNDED]" not in summary


def test_half_hp_flag():
    char = _make_char(hp={"max": 12, "current": 5})
    from dm.character import character_summary
    summary = character_summary(char)
    assert "[WOUNDED]" in summary
