"""RK-side event service; the FPGA owns state, KWS, Braille and motion.

OCR work is asynchronous so cancel/stop events can invalidate late results.
The hardware bridge must independently reject stale results and enforce faults.
"""
from concurrent.futures import ThreadPoolExecutor

from .protocol import BOARD_TYPES, PC_TYPES, encode, message


class BoardService:
    def __init__(self, capture_ocr, send, prompt, log=print, executor=None):
        self.capture_ocr, self.send, self.prompt, self.log = capture_ocr, send, prompt, log
        self.executor = executor if executor is not None else ThreadPoolExecutor(max_workers=1)
        self.owns_executor = executor is None
        self.last_seq = -1
        self.seq = 0
        self.active_job = None
        self.started_job = None
        self.pending = None

    def handle(self, event):
        encode(event, BOARD_TYPES)  # Validate direction and frame length at the boundary.
        if event["seq"] <= self.last_seq:
            self.log("DROP duplicate/out-of-order FPGA event")
            return
        self.last_seq = event["seq"]
        kind, job, payload = event["type"], event["job"], event["payload"]
        if kind == "status":
            self.active_job = job if payload["state"] == 2 else None
        elif kind == "prompt":
            self.prompt(payload["id"], payload["text"])
        elif kind == "error":
            self.log("FPGA ERROR: " + payload["reason"])
        elif kind == "capture_request":
            if job != self.active_job or job == self.started_job:
                self.log("DROP capture outside WAIT_OCR or duplicate capture")
                return
            self.started_job = job
            if self.pending is not None:
                self._reply(job, "ocr_failed", reason="上一次 OCR 尚未退出，请等待后重新开始")
                return
            self.pending = (job, self.executor.submit(self.capture_ocr))

    def _reply(self, job, kind, **payload):
        event = message(self.seq, job, kind, **payload)
        encode(event, PC_TYPES)
        self.seq += 1
        self.send(event)

    def poll(self):
        if self.pending is None or not self.pending[1].done():
            return
        job, future = self.pending
        self.pending = None
        if job != self.active_job:
            self.log("DROP stale OCR result: " + job)
            return
        try:
            text = future.result()
            if not isinstance(text, str) or not text.strip():
                raise ValueError("OCR 未返回有效文字")
            # Preserve Chinese, punctuation and newlines. PL decides support;
            # never convert to pinyin, strip characters, or calculate Braille here.
            event = message(self.seq, job, "text_result", text=text)
            encode(event, PC_TYPES)
        except Exception as exc:
            reason = (type(exc).__name__ + ": " + str(exc))[:300]
            self._reply(job, "ocr_failed", reason=reason)
            return
        self.seq += 1
        self.send(event)

    def close(self):
        self.active_job = None
        if self.owns_executor:
            # Running native inference is not forcibly killed by Python.
            # Driver/PL watchdogs must stop the machine independently.
            self.executor.shutdown(wait=True)
