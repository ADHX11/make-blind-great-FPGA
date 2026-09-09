"""PC mock for the planned board contract; no inference or hardware I/O."""

from enum import IntEnum

from .braille_reference import english_reference
from .protocol import PC_TYPES, envelope, validate


class Keyword(IntEnum):
    START = 1
    COMPLETE = 2
    PRINT = 3
    CANCEL = 4
    STOP = 5


class State(IntEnum):
    IDLE = 0
    WAIT_BOOK = 1
    WAIT_OCR = 2
    READY = 3
    PRINTING = 4
    DONE = 5
    ERROR = 6


class MockBoard:
    def __init__(self):
        self.state = State.IDLE
        self.text = ""
        self.cells = []
        self.seq = 0

    def _message(self, kind, **payload):
        result = envelope(self.seq, kind, **payload)
        self.seq += 1
        return result

    def _state(self, state):
        self.state = state
        return self._message("status", state=int(state))

    def _clear(self):
        self.text = ""
        self.cells = []

    def _error(self, reason, fatal=False):
        events = [self._message("error", reason=reason)]
        if fatal:
            self._clear()
            events.append(self._state(State.ERROR))
        return events

    def _prompt(self, prompt_id, text):
        return self._message("prompt", id=prompt_id, text=text)

    def inject_keyword(self, keyword):
        """Test-only event injection. MUST NOT become a production wire command."""
        keyword = Keyword(keyword)
        if keyword == Keyword.STOP:
            return self._error("停止：需要显式 reset 后重新开始", fatal=True)
        if self.state == State.ERROR:
            return self._error("ERROR 状态需要显式 reset")
        if keyword == Keyword.CANCEL:
            self._clear()
            return [self._state(State.IDLE), self._prompt("cancelled", "任务已取消")]
        if keyword == Keyword.START and self.state in (State.IDLE, State.DONE):
            self._clear()
            return [self._state(State.WAIT_BOOK), self._prompt("place_book", "开机，请把书籍放置在摄像头下")]
        if keyword == Keyword.COMPLETE and self.state == State.WAIT_BOOK:
            return [self._state(State.WAIT_OCR), self._prompt("capturing", "正在拍照识别"), self._message("capture_request")]
        if keyword == Keyword.PRINT and self.state == State.READY:
            return [self._state(State.PRINTING), self._prompt("printing", "开始打印")]
        return self._error(f"{self.state.name} 状态不接受关键词 {keyword.name}")

    def receive(self, message):
        validate(message, PC_TYPES)
        kind, payload = message["type"], message["payload"]
        if kind == "reset":
            self._clear()
            return [self._state(State.IDLE)]
        if self.state != State.WAIT_OCR:
            return self._error(f"{self.state.name} 状态不接受 {kind}")
        if kind == "ocr_failed":
            return self._error(payload["reason"], fatal=True)
        text = payload["text"]
        if not text.strip():
            return self._error("OCR 未返回有效文字", fatal=True)
        try:
            cells = english_reference(text)
        except ValueError as exc:
            return self._error(str(exc), fatal=True)
        self.text, self.cells = text, cells
        return [self._state(State.READY), self._prompt("ready", "文字已就绪，请说打印")]

    def finish_print(self):
        """Test-only stand-in for the physical printing engine's done signal."""
        if self.state != State.PRINTING:
            return self._error("打印完成事件只能在 PRINTING 状态触发")
        return [self._state(State.DONE), self._prompt("done", "打印完成")]
