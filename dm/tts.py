"""Text-to-speech via Piper CLI piped to aplay. Runs in a worker thread so the LLM keeps generating while speech plays."""
import queue
import subprocess
import threading

from .textutil import clean_for_speech


class NullSpeaker:
    """Text-only mode / no audio hardware."""

    def say(self, text, voice=None):
        pass

    def wait(self):
        pass

    def stop(self):
        pass


class PiperSpeaker:
    def __init__(self, cfg):
        self.piper_cmd = cfg["piper_cmd"]
        self.player_cmd = cfg["player_cmd"]
        self.voices = cfg.get("voices", {})
        self._q = queue.Queue()
        self._current = None
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def say(self, text, voice=None):
        text = clean_for_speech(text)
        if text:
            self._q.put((text, voice))

    def wait(self):
        self._q.join()

    def stop(self):
        """Barge-in: drop queued speech and kill the current utterance."""
        try:
            while True:
                self._q.get_nowait()
                self._q.task_done()
        except queue.Empty:
            pass
        if self._current:
            for p in self._current:
                try:
                    p.kill()
                except OSError:
                    pass

    def _run(self):
        while True:
            text, voice = self._q.get()
            try:
                cmd = list(self.piper_cmd)
                if voice and voice in self.voices:  # swap the model path for an NPC voice
                    cmd[cmd.index("--model") + 1] = self.voices[voice]
                p1 = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                p2 = subprocess.Popen(self.player_cmd, stdin=p1.stdout, stderr=subprocess.DEVNULL)
                self._current = (p1, p2)
                p1.stdout.close()
                p1.stdin.write((text + "\n").encode("utf-8"))
                p1.stdin.close()
                p2.wait()
                p1.wait()
            except (OSError, ValueError) as e:
                print(f"[tts error] {e}")
            finally:
                self._current = None
                self._q.task_done()


def make_speaker(cfg, enabled=True):
    if enabled and cfg.get("enabled", True):
        return PiperSpeaker(cfg)
    return NullSpeaker()
