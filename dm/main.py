"""CLI entry point.  python -m dm.main --campaign my-game [--text] [--new "dark gothic mystery"]"""
import argparse
import os
import re
import sys

from .config import load_config
from .game import Game
from .llm import LLMClient
from .memory import Memory, slugify
from .prompts import random_theme
from .tts import make_speaker

_QUIT = re.compile(r"^\s*(quit|exit|end (the )?session|stop the game|goodnight)\b", re.I)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Local AI Dungeon Master")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--campaign", default="default", help="campaign name (one SQLite file each)")
    ap.add_argument("--new", metavar="THEME", nargs="?", const="",
                    help="start a fresh campaign; omit THEME for a random one (resets that campaign)")
    ap.add_argument("--list", action="store_true", help="list saved campaigns and exit")
    ap.add_argument("--text", action="store_true", help="type instead of talking (also disables TTS)")
    ap.add_argument("--no-tts", action="store_true", help="listen by voice but print instead of speaking")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    if args.list:
        campaigns = Memory.list_campaigns(cfg["memory"]["campaigns_dir"])
        if not campaigns:
            print("No saved campaigns found.")
        else:
            print(f"{'Campaign':<24} {'Turns':>5}  {'Last played':<12}  Theme")
            print("-" * 72)
            for c in campaigns:
                print(f"{c['name']:<24} {c['turn']:>5}  {c['last_played']:<12}  {c['theme']}")
        return
    path = os.path.join(cfg["memory"]["campaigns_dir"], slugify(args.campaign) + ".db")
    mem = Memory(path)
    speaker = make_speaker(cfg["tts"], enabled=not (args.text or args.no_tts))
    game = Game(cfg, LLMClient(cfg["llm"]), mem, speaker)

    if args.new is not None:
        theme = args.new or random_theme()
        print(f"[theme: {theme}]")
        if os.path.exists(path):
            import shutil
            bak = path + ".bak"
            shutil.copy2(path, bak)
            print(f"[backed up to {os.path.basename(bak)}]")
        mem.reset()
        game.start_campaign(theme)
    elif mem.turn == 0:
        theme = random_theme()
        print(f"[theme: {theme}]")
        game.start_campaign(theme)
    else:
        game.recap()
    speaker.wait()

    if not args.text:
        from .stt import record_utterance, transcribe

    print(f"[campaign: {args.campaign} | {path}]  say 'quit' to end the session.")
    try:
        while True:
            if args.text:
                try:
                    heard = input("\nYou: ")
                except EOFError:
                    break
            else:
                print("\n[listening...]")
                try:
                    wav = record_utterance(cfg["audio"])
                    if not wav:
                        continue
                    names = [c["name"] for c in mem.all_characters()] or None
                    heard = transcribe(cfg["stt"], wav, names=names)
                    if not heard:
                        continue
                except Exception as e:
                    print(f"[stt error] {e}", file=sys.stderr)
                    continue
                print(f"You: {heard}")
            if _QUIT.match(heard):
                speaker.say("Until next time, adventurers.")
                break
            try:
                game.handle(heard)
            except Exception as e:  # keep the session alive on LLM/network hiccups
                print(f"[error] {e}", file=sys.stderr)
            speaker.wait()  # don't listen while speaking (no echo cancellation in the baseline)
    except KeyboardInterrupt:
        pass
    finally:
        speaker.stop()
        game.wait_idle()
        print("\nCampaign saved.")


if __name__ == "__main__":
    main()
