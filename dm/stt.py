"""Speech-to-text: microphone capture with simple energy VAD + whisper.cpp CLI."""
import os
import re
import subprocess
import tempfile
import time
import wave

_NOISE = re.compile(r"^\s*[\[(].*[\])]\s*$")  # whisper emits "[BLANK_AUDIO]", "(silence)", "[Music]" ...


def record_utterance(cfg, log=print):
    """Record one utterance to a temp WAV and return its path (None if nothing was said).

    Energy-threshold VAD is crude but dependency-free. Tune audio.vad_energy_threshold for your mic/room.
    """
    import numpy as np  # imported lazily so text mode works without audio libs
    import sounddevice as sd

    sr = cfg["sample_rate"]
    block = int(sr * 0.05)
    silence_blocks = int(cfg["silence_ms"] / 50)
    max_blocks = int(cfg["max_utterance_s"] * 20)
    frames, started, quiet = [], False, 0

    if cfg["push_to_talk"]:
        input("Press Enter to start talking... ")
        log("Recording - press Enter to stop")
        import threading
        stop = threading.Event()
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
        with sd.InputStream(samplerate=sr, channels=1, dtype="int16", device=cfg["device"], blocksize=block) as s:
            while not stop.is_set() and len(frames) < max_blocks * 3:
                data, _ = s.read(block)
                frames.append(data.copy())
    else:
        with sd.InputStream(samplerate=sr, channels=1, dtype="int16", device=cfg["device"], blocksize=block) as s:
            t0 = time.time()
            while len(frames) < max_blocks:
                data, _ = s.read(block)
                energy = float(np.sqrt(np.mean(data.astype("float32") ** 2)))
                if energy > cfg["vad_energy_threshold"]:
                    started, quiet = True, 0
                elif started:
                    quiet += 1
                if started:
                    frames.append(data.copy())
                    if quiet >= silence_blocks:
                        break
                elif time.time() - t0 > 60:  # nothing heard for a minute; let the caller loop
                    return None
    if not frames:
        return None
    audio = np.concatenate(frames)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(audio.tobytes())
    return path


def transcribe(cfg, wav_path, names=None):
    """Run whisper.cpp on a 16 kHz mono WAV and return the text ('' if nothing usable).

    names: optional list of proper nouns (character names) to bias transcription.
    Passed via --prompt so whisper is less likely to mis-transcribe them.
    """
    cmd = [cfg["binary"], "-m", cfg["model"], "-f", wav_path, "-t", str(cfg["threads"]), "-nt", "-np"]
    if names:
        cmd += ["--prompt", "Character names: " + ", ".join(names)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True).stdout
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
    text = " ".join(out.split())
    return "" if _NOISE.match(text) else text
