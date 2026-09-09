import unittest

from blind_fpga_host.braille_reference import CAPITAL, LETTER, NUMBER, dot_mask, english_reference
from blind_fpga_host.protocol import MAX_FRAME_BYTES, PC_TYPES, JsonLineCodec, ProtocolError, encode, envelope
from blind_fpga_host.simulator import Keyword, MockBoard, State


class ProtocolTests(unittest.TestCase):
    def test_utf8_fragmented_at_every_byte(self):
        message = envelope(7, "text_result", text="汉字 English\n第二行")
        codec, actual = JsonLineCodec(PC_TYPES), []
        for byte in encode(message):
            actual.extend(codec.feed(bytes([byte])))
        self.assertEqual(actual, [message])
        self.assertEqual(codec.buffer, b"")

    def test_multiple_frames_and_partial_tail(self):
        a, b = envelope(1, "reset"), envelope(2, "text_result", text="Hi")
        codec = JsonLineCodec()
        self.assertEqual(codec.feed(encode(a) + encode(b)[:-1]), [a])
        self.assertEqual(codec.feed(b"\n"), [b])

    def test_malformed_and_wrong_direction(self):
        for raw in (b"\xff\n", b"not json\n", b"[]\n", b"\n"):
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                JsonLineCodec().feed(raw)
        with self.assertRaises(ProtocolError):
            JsonLineCodec(PC_TYPES).feed(encode(envelope(0, "status", state=0)))
        for seq in (True, -1, "1"):
            with self.assertRaises(ProtocolError):
                envelope(seq, "reset")
        for kind in ("inject_keyword", "finish_print"):
            with self.assertRaises(ProtocolError):
                envelope(0, kind)

    def test_size_measured_in_bytes_including_newline(self):
        overhead = len(encode(envelope(0, "text_result", text="")))
        largest = envelope(0, "text_result", text="a" * (MAX_FRAME_BYTES - overhead))
        self.assertEqual(len(encode(largest)), MAX_FRAME_BYTES)
        self.assertEqual(JsonLineCodec().feed(encode(largest)), [largest])
        with self.assertRaises(ProtocolError):
            encode(envelope(0, "text_result", text="a" * (MAX_FRAME_BYTES - overhead + 1)))
        with self.assertRaises(ProtocolError):
            JsonLineCodec().feed(b"x" * MAX_FRAME_BYTES)
        with self.assertRaises(ProtocolError):
            JsonLineCodec().feed(b"x" * MAX_FRAME_BYTES + b"\n")


class BrailleTests(unittest.TestCase):
    def test_uppercase_and_spaces(self):
        self.assertEqual(english_reference("A z"), [CAPITAL, dot_mask("1"), 0, dot_mask("1356")])
        self.assertEqual(english_reference("FPGA").count(CAPITAL), 4)

    def test_numeric_prefix_and_letter_mode(self):
        self.assertEqual(english_reference("12a"), [NUMBER, 1, 3, LETTER, 1])
        self.assertEqual(english_reference("1A"), [NUMBER, 1, LETTER, CAPITAL, 1])
        self.assertEqual(english_reference("1k"), [NUMBER, 1, dot_mask("13")])
        self.assertEqual(english_reference("1 2"), [NUMBER, 1, 0, NUMBER, 3])
        self.assertEqual(english_reference("0"), [NUMBER, dot_mask("245")])

    def test_unsupported_never_dropped(self):
        for text in ("你好", "a!", "a\nb", "a\tb", "é"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                english_reference(text)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.board = MockBoard()

    def wait_ocr(self):
        self.board.inject_keyword(Keyword.START)
        return self.board.inject_keyword(Keyword.COMPLETE)

    def ready(self):
        self.wait_ocr()
        self.board.receive(envelope(0, "text_result", text="Hello 123"))
        self.assertEqual(self.board.state, State.READY)

    def test_happy_path_event_order(self):
        events = self.wait_ocr()
        self.assertEqual([e["type"] for e in events], ["status", "prompt", "capture_request"])
        self.assertEqual(self.board.state, State.WAIT_OCR)
        self.board.receive(envelope(0, "text_result", text="Hello FPGA 123"))
        self.assertEqual(self.board.state, State.READY)
        self.assertTrue(self.board.cells)
        self.board.inject_keyword(Keyword.PRINT)
        self.assertEqual(self.board.state, State.PRINTING)
        self.board.finish_print()
        self.assertEqual(self.board.state, State.DONE)
        self.board.inject_keyword(Keyword.START)
        self.assertEqual(self.board.state, State.WAIT_BOOK)
        self.assertEqual(self.board.cells, [])

    def test_out_of_order_cannot_print(self):
        for key in (Keyword.COMPLETE, Keyword.PRINT):
            self.assertEqual(self.board.inject_keyword(key)[0]["type"], "error")
            self.assertEqual(self.board.state, State.IDLE)
        self.board.receive(envelope(0, "text_result", text="Hi"))
        self.assertEqual(self.board.state, State.IDLE)
        self.assertEqual(self.board.text, "")
        self.board.finish_print()
        self.assertEqual(self.board.state, State.IDLE)

    def test_cancel_clears_buffer(self):
        self.ready()
        self.board.inject_keyword(Keyword.CANCEL)
        self.assertEqual(self.board.state, State.IDLE)
        self.assertEqual((self.board.text, self.board.cells), ("", []))
        self.board.inject_keyword(Keyword.PRINT)
        self.assertEqual(self.board.state, State.IDLE)

    def test_stop_is_sticky_until_explicit_reset(self):
        self.ready()
        self.board.inject_keyword(Keyword.PRINT)
        self.board.inject_keyword(Keyword.STOP)
        self.assertEqual(self.board.state, State.ERROR)
        self.assertEqual((self.board.text, self.board.cells), ("", []))
        for keyword in Keyword:
            self.board.inject_keyword(keyword)
            self.assertEqual(self.board.state, State.ERROR)
        self.board.finish_print()
        self.assertEqual(self.board.state, State.ERROR)
        self.board.receive(envelope(0, "reset"))
        self.assertEqual(self.board.state, State.IDLE)

    def test_ocr_failure_empty_or_unsupported_never_ready(self):
        for message in (envelope(0, "text_result", text="  "),
                        envelope(0, "text_result", text="中文"),
                        envelope(0, "ocr_failed", reason="Camera unavailable")):
            with self.subTest(message=message):
                self.board = MockBoard()
                self.wait_ocr()
                events = self.board.receive(message)
                self.assertEqual(self.board.state, State.ERROR)
                self.assertEqual(self.board.cells, [])
                self.assertEqual(events[0]["type"], "error")


if __name__ == "__main__":
    unittest.main()
