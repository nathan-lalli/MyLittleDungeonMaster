# Dungeon Master on Raspberry Pi (baseline)

A voice-driven D&D-style Dungeon Master that runs fully offline on Raspberry Pi 4s.
You talk -> Whisper transcribes -> a small local LLM narrates -> Piper speaks, sentence by sentence.
Campaign state persists in SQLite so the DM remembers NPCs, places, quests, and what happened.

## Honest expectations (read first)

- A Pi 4 is CPU-only. Realistic LLM size is **~1B-3B parameters, 4-bit quantized**. Expect competent but simple narration, occasional continuity slips, and weak rules adjudication. This is why dice, state, and memory are handled in **code**, not by the model.
- Speed is the real constraint. Rule of thumb from the sources below: a Pi 5 is about 2x a Pi 4 for Whisper, and a model at 3-5 tok/s "technically works but feels painfully slow". **Measure on your own Pis** with `scripts/bench_llm.py` before committing to a model. I did not find published Pi 4 numbers for the specific models below, so any tok/s figure I give is an estimate.
- Expect roughly **5-15 s from end of your sentence to first spoken word** on a single Pi 4 (STT + prompt processing + first sentence + TTS). Sentence streaming hides the rest. Offloading roles to separate Pis (below) is the main lever.

## Architecture

```
mic -> [VAD] -> whisper.cpp (STT) -> Game engine -> llama-server (LLM, HTTP) -> sentence splitter -> Piper (TTS) -> speaker
                                        |   ^
                         dice (code) ---+   +--- SQLite memory: entities + facts + rolling summary + recent turns
                                        |
                                 background "scribe" (schema-constrained JSON) updates NPCs/places/quests/facts
```

Every prompt = short DM rules + WORLD NOTES (structured state, ~1200 chars) + STORY SO FAR (rolling summary) + last ~8 messages. That is how a 4k-context small model "remembers" a long campaign.

## Hardware

Per node you actually run models on:

| Item | Why |
|---|---|
| Pi 4 **8 GB** for the LLM node (4 GB works only for <=1.5B models) | RAM headroom for model + context |
| Active cooling (fan + heatsink case) | Sustained inference throttles an uncooled Pi 4 |
| Official-class 5.1 V / 3 A USB-C PSU | Undervoltage causes slowdowns and crashes |
| **USB 3 SSD** (boot from it) instead of microSD | Faster model loads, far better reliability |
| Gigabit switch + Ethernet to each Pi | Wi-Fi adds latency; needed for any multi-node setup |
| USB conference speakerphone (mic + speaker in one, with echo cancellation) | Biggest quality win for voice: avoids the DM hearing itself. A cheap USB mic + speaker works but you must not talk while it speaks |

Optional later: a Pi 5 (8 GB) as the LLM node. The benchmark source below measured the 8 GB Pi 5 handling all 25 models it tried, while the Pi 4 is limited to smaller ones.

## Topologies (you have several Pi 4s)

1. **Single node (start here):** everything on one Pi 8 GB. Use a <=1.5B LLM + `tiny.en`/`base.en` Whisper. Simplest; slowest.
2. **Two nodes (recommended):** *Voice Pi* (mic/speaker, Whisper, Piper, `dm` Python app) + *Brain Pi* (`llama-server` only). Set `llm.base_url: http://<brain-ip>:8080/v1`. Whisper/Piper and the LLM stop fighting for the same 4 cores.
3. **Stretch:** Distributed Llama (tensor-parallel across 2/4 Pis over Ethernet) to run larger Llama-architecture models. It requires node counts that are powers of two (1, 2, 4...), and its published Pi 4 8 GB results are for much larger models than you need; I could not extract clean 2- and 4-node figures from what I retrieved, so treat any speedup claim as unverified until you test it. It exposes its own API, so you would add a small client alongside `dm/llm.py`.

## Model shortlist (test in this order; none verified on a Pi 4 by me)

LLM (GGUF, Q4_K_M unless noted; set `-c 4096`):
1. **Qwen2.5-1.5B-Instruct** - baseline; listed in the Pi model roundups cited below.
2. **Gemma 3 1B** - tiny and structured; likely fastest decent option.
3. **Qwen3 1.7B** - strong for its size per the KDnuggets roundup; set `llm.system_suffix: "/no_think"` so it does not emit reasoning text (verify the switch works on your build).
4. **Llama 3.2 3B / Qwen2.5-3B** - best prose of the group but slow on a Pi 4; 8 GB only; judge by whether the wait feels acceptable.

Whisper (whisper.cpp): `tiny.en` first (10x faster than real time on an RK3588 in one benchmark; the openHAB docs say Pi 4 is about 2x slower than Pi 5 and only tiny runs in under 5 s there), then `base.en` if accuracy is poor. D&D proper nouns ("Thorin", "Waterdeep") will be mis-transcribed; a later phase adds a name-biasing initial prompt from memory.

TTS: **Piper**, `en_US-lessac-medium` (or a `-low` voice if latency matters). Piper is built for CPU-only boards like the Pi 4 and runs in real time there.

## Run it

```bash
# on each Pi (ROLE=brain | voice | all)
ROLE=all ./scripts/setup_pi.sh
# put a GGUF in ~/models, then:
~/llama.cpp/build/bin/llama-server -m ~/models/YOUR.gguf -c 4096 --threads 4 --port 8080
python scripts/bench_llm.py              # record tok/s and TTFT per model
python -m dm.main --text --campaign test --new "haunted coastal village"   # no audio needed
python -m dm.main --campaign test        # voice mode
```

Spoken commands: "roll a d20 with advantage", "2d6+3", "recap", "my character is Thorin, a dwarf fighter", "quit".
Run tests with `python -m pytest`.

## Layout

```
dm/llm.py      OpenAI-compatible streaming client (llama.cpp, Ollama, anything)
dm/stt.py      mic capture + energy VAD + whisper.cpp CLI
dm/tts.py      Piper -> aplay worker thread, with stop() for barge-in
dm/memory.py   SQLite: entities, facts, rolling summary, messages
dm/game.py     turn loop, prompt assembly, summarizer, background scribe
dm/dice.py     dice in code, tolerant of speech-to-text spacing
dm/prompts.py  all prompts + scribe JSON schema
scripts/       setup_pi.sh, llama-server.service, bench_llm.py
```

## What is tested vs not

Tested here (no Pi, fake LLM): memory persistence, summarization, dice parsing, sentence streaming, scribe merge, turn loop. **Not tested:** audio capture, whisper.cpp / Piper invocation, llama.cpp JSON-schema output on your build, `setup_pi.sh`. Flag names (`whisper-cli`, Piper `--output-raw`, `response_format`) follow current docs as I know them; if one differs on your build, the fix is in `config.yaml` or one line in `stt.py`/`llm.py`.

## Roadmap

- **Phase 0 (this):** text mode -> verify LLM + memory loop, benchmark models.
- **Phase 1:** voice on one Pi; tune VAD threshold; pick model by latency.
- **Phase 2:** split Voice/Brain Pis; barge-in (interrupt DM with `speaker.stop()`); push-to-talk fallback.
- **Phase 3:** campaign "bible" generated at start (factions, secrets, 3-act outline) stored as entities so the DM stays on plot; embedding-based recall of old events (small embedding model, `sqlite` vector search); name-biasing prompt for Whisper.
- **Phase 4:** multiple player voices (speaker ID), NPC voices via `tts.voices`, ambient sound effects, optional rules lookup (SRD) as retrieval.

## Sources

- Which AI Models Can Run on a Raspberry Pi 4 or 5? - https://simeononsecurity.com/articles/ai-models-raspberry-pi-4-5/
- 7 Tiny AI Models for Raspberry Pi (KDnuggets) - https://www.kdnuggets.com/7-tiny-ai-models-for-raspberry-pi
- Research on LLM performance on Raspberry Pi 5 (llama.cpp vs Ollama, BitNet) - https://stratospherelinuxips.readthedocs.io/en/develop/_sources/immune/research_rpi_llm_performance.md.txt
- Can You Run LLMs Locally Without a GPU? (It's FOSS; tokens/sec feel threshold) - https://itsfoss.com/testing-local-llms-without-gpu
- whisper.cpp real-time discussion #166 - https://github.com/ggml-org/whisper.cpp/discussions/166
- openHAB Whisper STT (Pi 4 vs Pi 5 timing) - https://www.openhab.org/addons/voice/WhisperSTT
- Turing Pi: whisper.cpp + Piper benchmarks (RK3588, not a Pi) - https://turingpi.com/whisper-cpp-piper-tts-arm64-turing-pi-rk3588/
- Piper on Pi 4 real-time (tts.ai listing) - https://tts.ai/voices/piper/
- Distributed Llama - https://github.com/b4rtaz/distributed-llama
