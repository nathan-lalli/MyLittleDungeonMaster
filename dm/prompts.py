"""Prompts. Kept SHORT on purpose: on a Pi 4, every prompt token costs seconds (prompt processing is slow)."""
import random

THEMES = [
    "haunted coastal village besieged by sea creatures",
    "underground dwarven city on the verge of civil war",
    "cursed jungle temple where explorers keep disappearing",
    "desert empire crumbling under a sorcerer-king's tyranny",
    "frozen northern frontier where ancient giants are waking",
    "city of thieves built inside a dead dragon's skeleton",
    "enchanted forest where the fey are stealing children",
    "volcanic island chain ruled by rival pirate lords",
    "plague-ravaged kingdom searching for a lost holy relic",
    "arcane academy in chaos after the headmaster's murder",
    "moonlit swamp hiding a sunken elven civilization",
    "mountain pass haunted by the ghosts of a lost army",
    "trade city where every merchant guild is secretly a cult",
    "forgotten lighthouse at the edge of a monster-filled sea",
    "noble estate locked in a deadly inheritance dispute",
]


def random_theme():
    return random.choice(THEMES)



DM_SYSTEM = """You are the Dungeon Master of a fantasy tabletop role-playing game, speaking aloud to the players.
Rules:
- Reply in 2 to 4 short sentences of plain spoken English. No markdown, lists, or stage directions.
- Describe what happens as a result of the player's action, then end by asking what they do next.
- Never decide what the player's character does, says, or feels.
- When the outcome is uncertain, ask the player to roll a die (for example "roll a d20") and wait.
- Stay consistent with the WORLD NOTES and STORY SO FAR below. Do not contradict them.
- Keep names consistent. Introduce at most one new named character or place per reply.
- PARTY block: each line is one player character with their current HP, max HP, AC, and class. Use this to inform your narration: reference a character's class abilities when relevant (a Cleric might pray, a Rogue might attempt stealth). If a character's current HP is below half their max HP, describe them as visibly wounded or struggling. At 0 HP they are unconscious and cannot act."""

START_PROMPT = """Create the opening of a new campaign. Theme: {theme}.
In 3 to 4 spoken sentences: set the scene, hint at a problem or hook, and ask the players what they do.
Mention one named place and one named non-player character."""

SUMMARY_PROMPT = """Update the story summary for a tabletop RPG campaign.
Previous summary:
{previous}

New events (player and Dungeon Master messages):
{events}

Write the updated summary in at most 120 words. Keep names, important decisions, items gained, and unresolved threads. Plain prose."""

SCRIBE_PROMPT = """You keep campaign notes. Read this exchange and list ONLY story elements that were explicitly stated.
Known names (do not duplicate): {known}

Player: {player}
Dungeon Master: {dm}

Return JSON with: npcs (name, description), locations (name, description), quests (name, status such as active, done, failed), facts (short sentences about lasting events, e.g. an item gained or an alliance made). Use empty lists if nothing new."""

_ENTITY = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
        "required": ["name", "description"],
    },
}
SCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "npcs": _ENTITY,
        "locations": _ENTITY,
        "quests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "status": {"type": "string"}},
                "required": ["name", "status"],
            },
        },
        "facts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["npcs", "locations", "quests", "facts"],
}
