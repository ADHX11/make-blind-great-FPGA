"""Proposed JSONL v1 adapter protocol; not an implemented FPGA UART parser."""

import json

MAX_FRAME_BYTES = 8192  # Includes the terminating LF.
PC_TYPES = {"text_result", "ocr_failed", "reset"}
BOARD_TYPES = {"capture_request", "prompt", "status", "error"}
STATES = ("IDLE", "WAIT_BOOK", "WAIT_OCR", "READY", "PRINTING", "DONE", "ERROR")


class ProtocolError(ValueError):
    pass


def validate(message, allowed_types=None):
    if not isinstance(message, dict) or set(message) != {"v", "seq", "type", "payload"}:
        raise ProtocolError("Envelope must contain exactly v, seq, type, payload")
    if type(message["v"]) is not int or message["v"] != 1:
        raise ProtocolError("Unsupported protocol version")
    if type(message["seq"]) is not int or message["seq"] < 0:
        raise ProtocolError("seq must be a nonnegative integer")
    kind, payload = message["type"], message["payload"]
    if not isinstance(kind, str) or kind not in (PC_TYPES | BOARD_TYPES):
        raise ProtocolError("Unknown wire message type (mock actions are not wire messages)")
    if allowed_types is not None and kind not in allowed_types:
        raise ProtocolError("Message has the wrong direction")
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be an object")
    fields = {
        "text_result": {"text"}, "ocr_failed": {"reason"}, "reset": set(),
        "capture_request": set(), "prompt": {"id", "text"},
        "status": {"state"}, "error": {"reason"},
    }
    if set(payload) != fields[kind]:
        raise ProtocolError(f"Unexpected payload fields for {kind}")
    if kind == "status":
        if type(payload["state"]) is not int or payload["state"] not in range(7):
            raise ProtocolError("state must be an integer from 0 to 6")
    elif any(not isinstance(value, str) for value in payload.values()):
        raise ProtocolError("Text payload values must be strings")
    return message


def envelope(seq, kind, **payload):
    return validate({"v": 1, "seq": seq, "type": kind, "payload": payload})


def encode(message, allowed_types=None):
    validate(message, allowed_types)
    try:
        frame = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    except (UnicodeError, ValueError) as exc:
        raise ProtocolError("Message cannot be encoded as UTF-8 JSON") from exc
    if len(frame) > MAX_FRAME_BYTES:
        raise ProtocolError("Frame exceeds 8192 bytes including LF")
    return frame


class JsonLineCodec:
    """Reassemble byte fragments before UTF-8 decoding; a seq is diagnostic only."""

    def __init__(self, allowed_types=None):
        self.allowed_types = allowed_types
        self.buffer = bytearray()

    def feed(self, fragment):
        self.buffer.extend(fragment)
        messages = []
        while b"\n" in self.buffer:
            end = self.buffer.index(b"\n") + 1
            if end > MAX_FRAME_BYTES:
                self.buffer.clear()
                raise ProtocolError("Frame exceeds 8192 bytes including LF")
            line = bytes(self.buffer[:end - 1])
            del self.buffer[:end]
            try:
                parsed = json.loads(line.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise ProtocolError("Malformed UTF-8 JSONL frame") from exc
            messages.append(validate(parsed, self.allowed_types))
        if len(self.buffer) >= MAX_FRAME_BYTES:
            self.buffer.clear()
            raise ProtocolError("Unterminated frame exceeds the frame limit")
        return messages
