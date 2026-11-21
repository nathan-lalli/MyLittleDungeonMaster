"""Game engine: routes player input, builds prompts, streams the DM reply to TTS, and keeps memory current."""
import re
import threading

from . import prompts
from .character import (CharacterCreator, character_summary, format_sheet, spell_info, spell_info_tts,
                        apply_damage, apply_heal, apply_long_rest, apply_short_rest, do_level_up)
from .dice import parse_roll
from .textutil import SentenceBatcher, split_sentences

_RECAP      = re.compile(r"\b(recap|what happened so far|previously on|remind me)\b", re.I)
_ROLL       = re.compile(r"\broll\b|^\s*(\d*\s*d\s*\d+)", re.I)
_CHARACTER  = re.compile(r"^(?:my character is|i am playing|i'm playing|add character)\s+(.+)", re.I)
_CHARACTER_CREATE = re.compile(r"^\s*(create|new|build|make)\s+(a\s+)?(new\s+)?character\b", re.I)
_CHAR_SHEET = re.compile(r"\b(character sheet|show (my |the )?character|my stats|show stats)\b", re.I)
_PARTY_SHOW = re.compile(r"\b(show (the )?party|party stats|who'?s in the party|show everyone)\b", re.I)
_SPELL_LIST = re.compile(r"\b(what spells|my spells|spell list|show spells)\b", re.I)
_HP_QUERY   = re.compile(r"\b(what'?s my|how many|check my|my) ?(current )?(hp|hit points?|health)\b", re.I)
_LONG_REST  = re.compile(r"\b(long rest|full rest|rest for the night|we rest|make camp)\b", re.I)
_SHORT_REST = re.compile(r"\bshort rest\b", re.I)
_DAMAGE     = re.compile(r"\btakes?\s+(\d+)\s*(?:points?\s+of\s+)?(?:damage|dmg)\b", re.I)
_HEAL       = re.compile(r"\b(?:heal|regain|restore)s?\s+(?:\w+\s+){0,3}(?:for\s+)?(\d+)\s*(?:hp|hit points?)\b", re.I)
_LEVEL_UP   = re.compile(r"\b(level up|leveled? up|gained? a level)\b", re.I)
_ADD_NOTE   = re.compile(r"^(?:add (?:a )?note|note)(?:\s+(?:for|to|about)\s+(\w+))?[:\s]\s*(.+)", re.I)
_HELP         = re.compile(r"^\s*(help|commands|what can i say|what can i do)\b", re.I)
_SET_SUBCLASS = re.compile(r"\b(?:set|my|change)\s+subclass\s+(?:to|is)\s+(.+)", re.I)
_CAST_SPELL   = re.compile(
    r"\b(?:cast|use|spend)\b(?:\s+\w+){0,4}\s+level\s*(\d+)"   # "cast a level 2 spell"
    r"|\blevel\s*(\d+)\s*(?:st|nd|rd|th)?\s*(?:spell\s+)?slot\b",  # "1st level slot"
    re.I
)


class Game:
    def __init__(self, cfg, llm, memory, speaker, log=print):
        self.cfg, self.llm, self.mem, self.speaker, self.log = cfg, llm, memory, speaker, log
        self.mcfg = cfg["memory"]
        self._scribe_thread = None
        self._creator: CharacterCreator | None = None

    # ---- public API -----------------------------------------------------------------
    def start_campaign(self, theme):
        self.mem.next_turn()
        self.mem.set_meta("theme", theme)
        self.mem.upsert_entity("premise", "premise", f"Theme: {theme}")
        reply = self._narrate([{"role": "user", "content": prompts.START_PROMPT.format(theme=theme)}], remember_player=None)
        self.mem.add_message("assistant", reply)
        self._scribe("(campaign start)", reply)
        return reply

    def handle(self, text):
        """Handle one player utterance. Returns the DM's spoken text (or a local response)."""
        text = text.strip()
        if not text:
            return ""
        # Route inputs to character creator when it's active
        if self._creator is not None:
            return self._advance_creation(text)
        if _RECAP.search(text):
            return self.recap()
        if _CHARACTER_CREATE.match(text):
            return self._begin_creation()
        m = _CHARACTER.match(text)
        if m:
            desc = m.group(1).strip().rstrip(".")
            name = re.split(r"[,.:]| the | a | an ", desc, maxsplit=1)[0].strip() or desc
            self.mem.upsert_entity("pc", name, desc)
            msg = f"Noted. {name} has joined the party."
            self._say(msg)
            return msg
        if _CHAR_SHEET.search(text):
            return self._cmd_char_sheet(text)
        if _PARTY_SHOW.search(text):
            return self._cmd_party()
        if _SPELL_LIST.search(text):
            return self._cmd_spells(text)
        m = _CAST_SPELL.search(text)
        if m:
            level = int(m.group(1) or m.group(2))
            return self._cmd_cast_spell(text, level)
        if _HP_QUERY.search(text):
            return self._cmd_hp(text)
        if _LONG_REST.search(text):
            return self._cmd_long_rest()
        if _SHORT_REST.search(text):
            return self._cmd_short_rest(text)
        if _HELP.match(text):
            return self._cmd_help()
        m = _DAMAGE.search(text)
        if m:
            return self._cmd_damage(text, int(m.group(1)))
        m = _HEAL.search(text)
        if m:
            return self._cmd_heal(text, int(m.group(1)))
        if _LEVEL_UP.search(text):
            return self._cmd_level_up(text)
        m = _SET_SUBCLASS.search(text)
        if m:
            return self._cmd_set_subclass(text, m.group(1).strip())
        m = _ADD_NOTE.match(text)
        if m:
            return self._cmd_add_note(m.group(1), m.group(2))
        roll = parse_roll(text) if _ROLL.search(text) else None
        if roll:
            self._say(roll.speak())
            self.log(f"[dice] {roll.describe()}")
            text = f"(I rolled {roll.describe()}) {text}"
        return self.take_turn(text)

    def take_turn(self, player_text):
        self.mem.next_turn()
        self.mem.add_message("user", player_text)
        reply = self._narrate(self._build_messages(), remember_player=player_text)
        self.mem.add_message("assistant", reply)
        self._maybe_summarize()
        self._scribe(player_text, reply)
        return reply

    def recap(self):
        summary = self.mem.latest_summary()
        recent = [m["content"] for m in self.mem.unsummarized() if m["role"] == "assistant"][-2:]
        text = " ".join(x for x in [summary] + recent if x) or "Nothing has happened yet."
        self._say(text)
        return text

    def wait_idle(self):
        if self._scribe_thread:
            self._scribe_thread.join()

    def _begin_creation(self):
        try:
            from . import lookup
            lookup_fn = lookup.lookup
        except ImportError:
            lookup_fn = None
        self._creator = CharacterCreator(lookup_fn=lookup_fn)
        question = self._creator.start()
        self._say(question)
        return question

    def _advance_creation(self, text):
        response, done = self._creator.advance(text)
        self._say(response)
        if done:
            char = self._creator.character
            if char:
                self.mem.save_character(char)
            self._creator = None
        return response

    # ---- character commands (no LLM call; quick confirmation) ----------------------------

    def _find_character(self, text: str):
        """Return the best matching character from the party, or None."""
        chars = self.mem.all_characters()
        if not chars:
            return None
        if len(chars) == 1:
            return chars[0]
        text_lower = text.lower()
        for c in chars:
            if c["name"].lower() in text_lower:
                return c
        return None

    def _cmd_char_sheet(self, text):
        char = self._find_character(text)
        if not char:
            chars = self.mem.all_characters()
            if not chars:
                msg = "No characters in the party yet. Say 'create a new character' to begin."
            else:
                names = ", ".join(c["name"] for c in chars)
                msg = f"Whose sheet? Say their name. Party: {names}"
            self._say(msg)
            return msg
        sheet = format_sheet(char)
        self.log(sheet)
        self.speaker.say(character_summary(char))
        return sheet

    def _cmd_party(self):
        chars = self.mem.all_characters()
        if not chars:
            msg = "No characters in the party yet."
            self._say(msg)
            return msg
        lines = ["Party:"]
        for c in chars:
            lines.append("  " + character_summary(c))
        msg = "\n".join(lines)
        self.log(msg)
        self.speaker.say(f"The party has {len(chars)} member(s): " +
                         ", ".join(c["name"] for c in chars) + ".")
        return msg

    def _cmd_spells(self, text):
        char = self._find_character(text)
        if not char:
            chars = self.mem.all_characters()
            if not chars:
                msg = "No characters in the party yet."
            else:
                names = ", ".join(c["name"] for c in chars)
                msg = f"Whose spells? Say their name. Party: {names}"
            self._say(msg)
            return msg
        info = spell_info(char)
        self.log(info)
        self.speaker.say(spell_info_tts(char))  # compact spoken summary, not the full sheet
        return info

    def _cmd_cast_spell(self, text, level: int):
        chars = self.mem.all_characters()
        if not chars:
            msg = "No characters in the party yet."
            self._say(msg)
            return msg
        char = self._find_character(text) or (chars[0] if len(chars) == 1 else None)
        if char is None:
            names = ", ".join(c["name"] for c in chars)
            msg = f"Which character cast the spell? Include their name: {names}"
            self._say(msg)
            return msg
        spells = dict(char.get("spells") or {})
        slots  = dict(spells.get("slots") or {})
        key    = str(level)
        slot   = slots.get(key)
        if not slot:
            msg = f"{char['name']} has no level {level} spell slots."
            self._say(msg)
            return msg
        total     = slot.get("total", 0)
        used      = slot.get("used", 0)
        remaining = total - used
        if remaining <= 0:
            msg = f"{char['name']} has no level {level} slots remaining (all {total} used)."
            self._say(msg)
            return msg
        slots[key]    = dict(slot, used=used + 1)
        spells["slots"] = slots
        updated = dict(char, spells=spells)
        self.mem.save_character(updated)
        new_rem = total - (used + 1)
        msg = f"{char['name']} uses a level {level} spell slot. {new_rem} of {total} remaining."
        self._say(msg)
        return msg

    def _cmd_hp(self, text):
        chars = self.mem.all_characters()
        if not chars:
            msg = "No characters in the party yet."
            self._say(msg)
            return msg
        char = self._find_character(text)
        targets = [char] if char else chars
        parts = []
        for c in targets:
            hp = c.get("hp", {})
            parts.append(f"{c['name']}: {hp.get('current','?')}/{hp.get('max','?')} HP")
        msg = "  ".join(parts)
        self._say(msg)
        return msg

    def _cmd_long_rest(self):
        chars = self.mem.all_characters()
        if not chars:
            msg = "No characters in the party yet."
            self._say(msg)
            return msg
        lines = ["The party takes a long rest."]
        for c in chars:
            updated, note = apply_long_rest(c)
            self.mem.save_character(updated)
            lines.append(f"  {note}")
        msg = "\n".join(lines)
        self._say(msg)
        return msg

    def _cmd_damage(self, text, amount):
        char = self._find_character(text)
        if not char:
            chars = self.mem.all_characters()
            if not chars:
                msg = "No characters in the party yet."
            else:
                names = ", ".join(c["name"] for c in chars)
                msg = f"Include a character name: {names}"
            self._say(msg)
            return msg
        updated, msg = apply_damage(char, amount)
        self.mem.save_character(updated)
        self._say(msg)
        return msg

    def _cmd_heal(self, text, amount):
        char = self._find_character(text)
        if not char:
            chars = self.mem.all_characters()
            if not chars:
                msg = "No characters in the party yet."
            else:
                names = ", ".join(c["name"] for c in chars)
                msg = f"Include a character name: {names}"
            self._say(msg)
            return msg
        updated, msg = apply_heal(char, amount)
        self.mem.save_character(updated)
        self._say(msg)
        return msg

    def _cmd_level_up(self, text):
        char = self._find_character(text)
        if not char:
            chars = self.mem.all_characters()
            if not chars:
                msg = "No characters in the party yet."
            else:
                names = ", ".join(c["name"] for c in chars)
                msg = f"Include a character name to level up: {names}"
            self._say(msg)
            return msg
        updated, msg = do_level_up(char)
        self.mem.save_character(updated)
        self._say(msg)
        return msg

    def _cmd_set_subclass(self, text, subclass_name):
        char = self._find_character(text)
        if not char:
            chars = self.mem.all_characters()
            if not chars:
                msg = "No characters in the party yet."
                self._say(msg)
                return msg
            if len(chars) == 1:
                char = chars[0]
            else:
                names = ", ".join(c["name"] for c in chars)
                msg = f"Which character? Include their name: {names}"
                self._say(msg)
                return msg
        if char.get("subclass") and char["subclass"].strip():
            msg = f"{char['name']} already has a subclass: {char['subclass']}."
            self._say(msg)
            return msg
        updated = dict(char, subclass=subclass_name.strip().title())
        self.mem.save_character(updated)
        msg = f"{updated['name']}'s subclass set to {updated['subclass']}."
        self._say(msg)
        return msg

    def _cmd_short_rest(self, text):
        chars = self.mem.all_characters()
        if not chars:
            msg = "No characters in the party yet."
            self._say(msg)
            return msg
        m = re.search(r"\b(\d+)\s*(?:hit\s+)?dic(?:e|s)?\b", text, re.I)
        num_dice = int(m.group(1)) if m else 1
        # Named character → that one; single character → them; multiple unnamed → whole party
        target = self._find_character(text) if len(chars) > 1 else chars[0]
        targets = [target] if target else chars
        lines = [f"The party takes a short rest." if len(targets) > 1 else "Short rest."]
        for c in targets:
            updated, note = apply_short_rest(c, num_dice)
            self.mem.save_character(updated)
            lines.append(f"  {note}")
        msg = "\n".join(lines)
        self._say(msg)
        return msg

    def _cmd_help(self):
        text = (
            "Available commands:\n"
            "  create a new character           — full character creation with Open5e lookup\n"
            "  character sheet [name]           — full stat sheet\n"
            "  show the party                   — compact party overview\n"
            "  what spells do I have [name]     — spellcasting info\n"
            "  cast level N spell [name]        — use a spell slot (tracks usage)\n"
            "  what's my HP                     — current hit points\n"
            "  [name] takes X damage            — track damage  (e.g. 'Mira takes 7 damage')\n"
            "  heal X hp / regain X hit points  — track healing\n"
            "  long rest                        — restore all HP for the whole party\n"
            "  short rest [spend N dice]        — restore some HP\n"
            "  level up [name]                  — gain a level\n"
            "  set subclass to X [name]         — assign a subclass after leveling up\n"
            "  add note [for name]: text        — session note on a character\n"
            "  roll XdY+Z                       — roll dice (advantage/disadvantage work too)\n"
            "  recap                            — story so far\n"
            "  quit / exit                      — end the session\n"
        )
        self.log(text)
        self.speaker.say("Here are the available commands. Check the terminal for the full list.")
        return text

    def _cmd_add_note(self, char_name, note_text):
        chars = self.mem.all_characters()
        if not chars:
            msg = "No characters in the party yet."
            self._say(msg)
            return msg
        target = None
        if char_name:
            for c in chars:
                if c["name"].lower() == char_name.lower():
                    target = c
                    break
        if target is None and len(chars) == 1:
            target = chars[0]
        if target is None:
            names = ", ".join(c["name"] for c in chars)
            msg = f"Note which character? Options: {names}"
            self._say(msg)
            return msg
        existing = target.get("notes", "").strip()
        updated = dict(target, notes=f"{existing}\n{note_text}".strip() if existing else note_text)
        self.mem.save_character(updated)
        msg = f"Note added to {target['name']}."
        self._say(msg)
        return msg

    # ---- internals ------------------------------------------------------------------------
    def _say(self, text):
        self.log(f"DM: {text}")
        self.speaker.say(text)

    def _build_messages(self):
        notes = self.mem.state_block(self.mcfg["state_block_chars"]) or "(none yet)"
        summary = self.mem.latest_summary() or "(the story has just begun)"
        chars = self.mem.all_characters()
        if chars:
            party = "\n".join(character_summary(c) for c in chars)
            notes = f"PARTY:\n{party}\n\n{notes}"
        system = f"{prompts.DM_SYSTEM}\n\nWORLD NOTES:\n{notes}\n\nSTORY SO FAR:\n{summary}"
        recent = self.mem.unsummarized()[-self.mcfg["keep_recent_messages"]:]
        return [{"role": "system", "content": system}] + [{"role": m["role"], "content": m["content"]} for m in recent]

    def _narrate(self, messages, remember_player):
        """Stream the reply, speaking each sentence as soon as it completes (hides most generation latency)."""
        if messages and messages[0]["role"] != "system":
            messages = [{"role": "system", "content": prompts.DM_SYSTEM}] + messages
        buf, full, batcher = "", [], SentenceBatcher()
        print("DM: ", end="", flush=True)
        for chunk in self.llm.stream(messages):
            print(chunk, end="", flush=True)
            full.append(chunk)
            buf += chunk
            sentences, buf = split_sentences(buf)
            for s in sentences:
                out = batcher.add(s)
                if out:
                    self.speaker.say(out)
        print()
        for tail in (buf.strip(), None):
            if tail:
                out = batcher.add(tail)
                if out:
                    self.speaker.say(out)
        last = batcher.flush()
        if last:
            self.speaker.say(last)
        return "".join(full).strip()

    def _maybe_summarize(self):
        msgs = self.mem.unsummarized()
        if len(msgs) <= self.mcfg["summarize_after"]:
            return
        old = msgs[: -self.mcfg["keep_recent_messages"]]
        events = "\n".join(f"{'Player' if m['role'] == 'user' else 'DM'}: {m['content']}" for m in old)
        prompt = prompts.SUMMARY_PROMPT.format(previous=self.mem.latest_summary() or "(none)", events=events)
        try:
            text = self.llm.complete([{"role": "user", "content": prompt}], max_tokens=220, temperature=0.3)
        except Exception as e:  # network/LLM failure must never kill the game
            self.log(f"[summary skipped: {e}]")
            return
        if text:
            self.mem.add_summary(old[-1]["id"], text)
            self.mem.mark_summarized(old[-1]["id"])

    def _scribe(self, player_text, dm_text):
        """Extract NPCs/locations/quests/facts in the background while the players think."""
        def work():
            known = ", ".join(e["name"] for e in self.mem.entities()) or "none"
            prompt = prompts.SCRIBE_PROMPT.format(known=known, player=player_text, dm=dm_text)
            data = self.llm.extract_json([{"role": "user", "content": prompt}], prompts.SCRIBE_SCHEMA, max_tokens=300)
            if isinstance(data, dict):
                self.apply_scribe(data)

        prev = self._scribe_thread
        if prev and prev.is_alive():
            prev.join(timeout=0)  # don't block; daemon thread will finish eventually
        self._scribe_thread = threading.Thread(target=work, daemon=True)
        self._scribe_thread.start()

    def apply_scribe(self, data):
        for kind, key in (("npc", "npcs"), ("location", "locations")):
            for item in data.get(key, []) or []:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    self.mem.upsert_entity(kind, item["name"], str(item.get("description", "")))
        for q in data.get("quests", []) or []:
            if isinstance(q, dict) and isinstance(q.get("name"), str):
                self.mem.upsert_entity("quest", q["name"], status=str(q.get("status", "")))
        for f in data.get("facts", []) or []:
            if isinstance(f, str):
                self.mem.add_fact(f)
