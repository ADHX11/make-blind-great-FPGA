"""Nonblocking prerecorded WAV prompts. Does not implement continuous ASR/TTS."""
from pathlib import Path
import subprocess
import time

PROMPT_IDS = {"place_book", "capturing", "ready", "printing", "done", "error", "cancelled"}


class PromptPlayer:
    def __init__(self, cfg, log=print):
        self.cfg, self.log = cfg, log
        self.process = None
        self.deadline = 0

    def play(self, prompt_id, text):
        if prompt_id not in PROMPT_IDS:
            self.log("忽略未知提示音 ID：" + prompt_id)
            return
        self.log("PROMPT: " + text)
        if not self.cfg["enabled"]:
            return
        self.close()  # A newer state prompt supersedes an older prompt.
        path = Path(self.cfg["directory"]) / (prompt_id + ".wav")
        if not path.is_file():
            self.log("提示音未录制：" + str(path))
            return
        try:
            self.process = subprocess.Popen(
                [self.cfg["player"], str(path)], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.deadline = time.monotonic() + 30
        except OSError as exc:
            self.log("提示音播放失败：" + str(exc))

    def poll(self):
        if self.process is None:
            return
        result = self.process.poll()
        if result is not None:
            if result:
                self.log("提示音播放器返回错误：" + str(result))
            self.process = None
        elif time.monotonic() > self.deadline:
            self.log("提示音超过 30 秒，停止播放")
            self.close()

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process = None
