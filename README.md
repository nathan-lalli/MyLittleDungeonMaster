# MyLittleDungeonMaster

A voice-driven D&D 5e Dungeon Master that runs fully offline on Raspberry Pi 4s.
You talk → Whisper transcribes → a small local LLM narrates → Piper speaks, sentence by sentence.
Campaign state persists in SQLite. Full D&D 5e characters with HP, AC, spell slots, and level-up tracked in code — not by the model.

## Honest expectations (read first)

- A Pi 4 is CPU-only. Realistic LLM size is **~1B–3B parameters, 4-bit quantized**. Expect competent but simple narration, occasional continuity slips, and weak rules adjudication. This is why dice, HP, spells, and memory are handled in **code**, not by the model.
- Speed is the real constraint. Expect roughly **5–15 s from end of your sentence to first spoken word** on a single Pi 4 (STT + prompt processing + first sentence + TTS). Sentence streaming hides most of the rest.
- Offloading the LLM to a second Pi (see Topologies) is the main latency lever.

## Architecture

```
mic → [VAD] → whisper.cpp (STT) → Game engine → llama-server (LLM, HTTP) → sentence splitter → Piper (TTS) → speaker
                                       |   ^
                        dice (code) ───┘   └─── SQLite memory:
                        HP/spells (code)         entities + facts + rolling summary + recent turns
                                       |
                              background "scribe" (schema-constrained JSON) updates NPCs/places/quests/facts
```

Every DM prompt = short rules + **PARTY block** (HP/AC/class per character) + WORLD NOTES (structured state, ~1200 chars) + STORY SO FAR (rolling LLM summary) + last ~8 turns verbatim.

## Hardware

| Item | Why |
|---|---|
| Pi 4 **8 GB** for the LLM node (4 GB works for ≤1.5B only) | RAM headroom for model + context |
| Active cooling (fan + heatsink case) | Sustained inference throttles an uncooled Pi 4 |
| Official-class 5.1 V / 3 A USB-C PSU | Undervoltage causes slowdowns and crashes |
| **USB 3 SSD** (boot from it) instead of microSD | Faster model loads, far better reliability |
| Gigabit switch + Ethernet to each Pi | Wi-Fi adds latency |
| USB conference speakerphone (mic + speaker, with echo cancellation) | Biggest voice quality win |

## Topologies

1. **Single node (start here):** everything on one Pi 8 GB. Use a ≤1.5B LLM + `tiny.en`/`base.en` Whisper.
2. **Two nodes (recommended):** *Voice Pi* (mic/speaker, Whisper, Piper, `dm` app) + *Brain Pi* (`llama-server` only). Set `llm.base_url: http://<brain-ip>:8080/v1`. Whisper/Piper and the LLM stop competing for the same 4 cores.
3. **Stretch:** Distributed Llama (tensor-parallel across 2–4 Pis over Ethernet) to run larger models.

## Model shortlist

LLM (GGUF, Q4_K_M; set `-c 4096`):
1. **Qwen2.5-1.5B-Instruct** — baseline; well-tested on Pi.
2. **Gemma 3 1B** — tiny and fast; likely best latency on a single Pi 4.
3. **Qwen3 1.7B** — strong quality; set `llm.system_suffix: "/no_think"` to suppress reasoning text.
4. **Llama 3.2 3B / Qwen2.5-3B** — best prose but slow on Pi 4; 8 GB RAM required.

Whisper: `tiny.en` first (fastest), then `base.en` if accuracy is poor. Character names are passed as a `--prompt` hint to reduce mis-transcription.

TTS: **Piper**, `en_US-lessac-medium` (or `-low` for lower latency). Built for CPU-only boards.

## Setup & run

```bash
# Install dependencies
pip install -r requirements.txt

# Start the LLM server (Brain Pi or locally)
~/llama.cpp/build/bin/llama-server -m ~/models/YOUR.gguf -c 4096 --threads 4 --port 8080

# Benchmark models before committing to one
python scripts/bench_llm.py

# Text mode (no audio — good for first run / testing)
python -m dm.main --text --campaign mygroup --new "haunted coastal village"

# Voice mode
python -m dm.main --campaign mygroup

# List saved campaigns
python -m dm.main --list

# Start fresh (backs up existing campaign to .db.bak first)
python -m dm.main --campaign mygroup --new

# Run tests
python -m pytest
```

## Voice commands

| Command | What it does |
|---|---|
| `create a new character` | Full D&D 5e character creation (name → race → class → subclass → background → scores → skills → personality) |
| `character sheet [name]` | Full stat sheet to terminal; compact summary spoken |
| `show the party` | Compact HP/AC overview for all characters |
| `what spells do I have [name]` | Spell slots, cantrips, and prepared spells |
| `cast a level N spell [name]` | Use a spell slot (tracks usage; resets on long rest) |
| `[name] takes X damage` | Track damage |
| `heal X hp` / `regain X hit points` | Track healing |
| `long rest` | Restore all HP and spell slots for the whole party |
| `short rest [spend N dice]` | Restore some HP via hit dice |
| `level up [name]` | Gain a level (HP, proficiency, spell slots updated; prompts for subclass at the right level) |
| `set subclass to X [name]` | Assign a subclass after leveling up |
| `add note [for name]: text` | Attach a session note to a character |
| `roll XdY+Z` | Dice — advantage, disadvantage, and "two d8" phrasing all work |
| `recap` | Story so far (spoken + printed) |
| `help` | Full command list to terminal |
| `quit` / `exit` | End session |

## Character system

Characters are created step-by-step via voice and stored as JSON in SQLite alongside campaign state.

**What's tracked per character:**
- Race, class, subclass, background, level
- HP (current/max), AC, speed, proficiency bonus
- All 6 ability scores and modifiers
- Saving throw proficiencies, skill proficiencies
- Spell slots with usage tracking (full casters levels 1–10, half casters levels 1–10)
- Cantrips, prepared spells, domain/subclass notes
- Personality traits, bonds, ideals, flaws
- Session notes

**Rules implemented in code:**
- Barbarian Unarmored Defense: AC = 10 + DEX + CON
- Monk Unarmored Defense: AC = 10 + DEX + WIS
- Race speed: Dwarves, Halflings, Gnomes move 25 ft
- HP on level-up: hit die average + CON modifier
- Proficiency bonus progression
- Spell slot tables (full and half casters)
- Subclass unlocks at the correct level per class

**Open5e lookup:** when creating a cleric, wizard, warlock, etc., the app queries `api.open5e.com` for class and subclass info to show the player current SRD descriptions.

## File layout

```
dm/main.py        CLI entry point, voice loop, campaign management
dm/game.py        Turn routing, all voice command handlers, prompt assembly
dm/character.py   Character model: stats, creation state machine, HP/spell functions
dm/memory.py      SQLite persistence: entities, facts, summary, messages, characters
dm/llm.py         OpenAI-compatible streaming client (llama.cpp, Ollama, anything)
dm/stt.py         Mic capture + energy VAD + whisper.cpp CLI
dm/tts.py         Piper → aplay worker thread, sentence streaming
dm/lookup.py      Open5e REST API client for SRD lookups
dm/prompts.py     All prompts, random themes, scribe JSON schema
dm/dice.py        Dice parser (tolerates STT spacing and word forms)
dm/textutil.py    Sentence splitter and batcher for TTS streaming
dm/config.py      Config loading with defaults and ~ expansion
scripts/          setup_pi.sh, llama-server.service, bench_llm.py
tests/test_core.py  48 tests (no Pi, no audio required)
config.yaml       Your local overrides (not committed if it has secrets)
```

## What is tested vs not

**Tested (48 tests, fake LLM, no Pi needed):**
memory persistence, campaign reload, summarization trigger, dice parsing, sentence streaming, character creation flow (happy path, cancel, skill validation, multi-word skills), stat functions (damage, heal, long/short rest, level-up), spell slot seeding/usage/reset, Barbarian and Monk AC, race speed, `[WOUNDED]`/`[DOWN]` HP flags, all game commands (damage, heal, rest, level-up, set subclass, cast spell, party, character sheet, help, notes).

**Not tested (requires hardware):**
audio capture, whisper.cpp / Piper invocation, llama.cpp JSON-schema output, `setup_pi.sh`.

## Roadmap

- **✅ Phase 0:** text mode, LLM + memory loop, benchmark scripts
- **✅ Phase 1 (done):** full D&D 5e character system (creation, HP, spells, level-up), multi-campaign persistence, voice command set, Open5e lookup, Whisper name biasing
- **Phase 2:** voice on one Pi; tune VAD threshold; barge-in (interrupt DM mid-sentence); push-to-talk fallback
- **Phase 3:** split Voice/Brain Pis; campaign "bible" (factions, secrets, 3-act outline) as structured entities; embedding-based recall of old events
- **Phase 4:** multiple player voices (speaker ID), per-character NPC voices via `tts.voices`, ambient sound effects

## Sources

- Which AI Models Can Run on a Raspberry Pi 4 or 5? — https://simeononsecurity.com/articles/ai-models-raspberry-pi-4-5/
- 7 Tiny AI Models for Raspberry Pi (KDnuggets) — https://www.kdnuggets.com/7-tiny-ai-models-for-raspberry-pi
- LLM performance on Raspberry Pi 5 (llama.cpp vs Ollama) — https://stratospherelinuxips.readthedocs.io/en/develop/_sources/immune/research_rpi_llm_performance.md.txt
- Can You Run LLMs Locally Without a GPU? (It's FOSS) — https://itsfoss.com/testing-local-llms-without-gpu
- whisper.cpp real-time discussion #166 — https://github.com/ggml-org/whisper.cpp/discussions/166
- openHAB Whisper STT (Pi 4 vs Pi 5 timing) — https://www.openhab.org/addons/voice/WhisperSTT
- Piper TTS — https://github.com/rhasspy/piper
- Open5e SRD API — https://api.open5e.com
- Distributed Llama — https://github.com/b4rtaz/distributed-llama
