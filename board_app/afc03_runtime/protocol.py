"""AFC03 adapter-side v2 contract; no PCIe, UART or RTL decoder is implied."""
import json
import re

from blind_fpga_host.protocol import BOARD_TYPES, PC_TYPES, ProtocolError
from blind_fpga_host.protocol import validate as validate_v1

MAX_FRAME_BYTES = 8192


def validate(message, allowed_types=None):
    if not isinstance(message, dict) or set(message) != {"v", "seq", "job", "type", "payload"}:
        raise ProtocolError("AFC03 envelope needs v, seq, job, type, payload")
    if type(message["v"]) is not int or message["v"] != 2:
        raise ProtocolError("AFC03 service requires v2; v1 has no job correlation")
    job = message["job"]
    if not isinstance(job, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", job):
        raise ProtocolError("job must be a session-unique 1..64 character identifier")
    validate_v1({"v": 1, "seq": message["seq"], "type": message["type"],
                 "payload": message["payload"]}, allowed_types)
    return message


def message(seq, job, kind, **payload):
    return validate({"v": 2, "seq": seq, "job": job, "type": kind, "payload": payload})


def encode(event, allowed_types=None):
    validate(event, allowed_types)
    frame = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(frame) > MAX_FRAME_BYTES:
        raise ProtocolError("AFC03 control frame exceeds 8192 bytes; paginate before sending")
    return frame


class Codec:
    def __init__(self, allowed_types):
        self.allowed_types = allowed_types
        self.buffer = bytearray()

    def feed(self, fragment):
        self.buffer.extend(fragment)
        result = []
        while b"\n" in self.buffer:
            end = self.buffer.index(b"\n") + 1
            if end > MAX_FRAME_BYTES:
                self.buffer.clear()
                raise ProtocolError("Oversized AFC03 frame")
            line = bytes(self.buffer[:end - 1])
            del self.buffer[:end]
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise ProtocolError("Malformed AFC03 JSONL") from exc
            result.append(validate(event, self.allowed_types))
        if len(self.buffer) >= MAX_FRAME_BYTES:
            self.buffer.clear()
            raise ProtocolError("Unterminated AFC03 frame")
        return result
