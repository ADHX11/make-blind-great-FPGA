"""No camera, audio device, NPU, FPGA or network is accessed by these tests."""
from concurrent.futures import Future
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "board_app"))

from afc03_runtime.config import load_config, missing_integrations
from afc03_runtime.ocr import RknnSession
from afc03_runtime.prompts import PromptPlayer
from afc03_runtime.protocol import BOARD_TYPES, PC_TYPES, Codec, encode, message
from afc03_runtime.service import BoardService


class DeferredExecutor:
    def __init__(self):
        self.futures = []

    def submit(self, action):
        future = Future()
        self.futures.append(future)
        return future


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.executor = DeferredExecutor()
        self.sent, self.prompts, self.logs = [], [], []
        self.service = BoardService(lambda: None, self.sent.append,
                                    lambda *args: self.prompts.append(args), self.logs.append,
                                    executor=self.executor)
        self.seq = 0

    def event(self, kind, job="boot:1", **payload):
        event = message(self.seq, job, kind, **payload)
        self.seq += 1
        self.service.handle(event)
        return event

    def capture(self, job="boot:1"):
        self.event("status", job, state=2)
        self.event("capture_request", job)

    def test_text_stays_utf8_and_is_not_translated_on_rk(self):
        self.capture()
        text = "中文 English 123\n第二行。"
        self.executor.futures[0].set_result(text)
        self.service.poll()
        self.assertEqual(self.sent[0]["payload"], {"text": text})
        self.assertEqual(self.sent[0]["job"], "boot:1")
        self.service.poll()
        self.assertEqual(len(self.sent), 1)

    def test_cancel_discards_late_ocr(self):
        self.capture()
        self.event("status", state=0)
        self.executor.futures[0].set_result("old page")
        self.service.poll()
        self.assertEqual(self.sent, [])
        self.capture("boot:2")
        self.executor.futures[1].set_result("new page")
        self.service.poll()
        self.assertEqual(self.sent[0]["job"], "boot:2")

    def test_stop_is_processed_while_ocr_is_pending(self):
        self.capture()
        self.event("status", state=6)
        self.executor.futures[0].set_exception(RuntimeError("late native error"))
        self.service.poll()
        self.assertIsNone(self.service.active_job)
        self.assertEqual(self.sent, [])

    def test_old_ocr_cannot_enter_new_job_and_queue_is_bounded(self):
        self.capture()
        self.event("status", state=0)
        self.capture("boot:2")
        self.assertEqual(self.sent[0]["type"], "ocr_failed")
        self.assertEqual(self.sent[0]["job"], "boot:2")
        self.executor.futures[0].set_result("old page")
        self.service.poll()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(self.executor.futures), 1)

    def test_duplicate_or_misordered_capture_does_not_start_inference(self):
        self.event("capture_request")
        self.assertEqual(len(self.executor.futures), 0)
        self.capture()
        duplicate = self.event("capture_request")
        self.service.handle(duplicate)
        self.assertEqual(len(self.executor.futures), 1)

    def test_error_empty_and_oversize_return_failure_without_truncation(self):
        for result in ("  ", "中" * 8192, RuntimeError("no camera")):
            with self.subTest(result_type=type(result).__name__):
                self.setUp()
                self.capture()
                future = self.executor.futures[0]
                if isinstance(result, Exception):
                    future.set_exception(result)
                else:
                    future.set_result(result)
                self.service.poll()
                self.assertEqual([event["type"] for event in self.sent], ["ocr_failed"])

    def test_prompt_does_not_change_state_or_send_keyword(self):
        self.event("prompt", id="place_book", text="请放书")
        self.assertEqual(self.prompts, [("place_book", "请放书")])
        self.assertEqual(self.sent, [])
        self.assertIsNone(self.service.active_job)


class ProtocolTests(unittest.TestCase):
    def test_fragmented_chinese_and_job_roundtrip(self):
        event = message(5, "boot-uuid:32", "text_result", text="盲文\nHello")
        codec = Codec(PC_TYPES)
        decoded = []
        for byte in encode(event, PC_TYPES):
            decoded.extend(codec.feed(bytes([byte])))
        self.assertEqual(decoded, [event])

    def test_wrong_version_job_direction_and_injected_keyword_rejected(self):
        event = message(0, "boot:1", "capture_request")
        for patch in ({"v": 1}, {"job": ""}, {"job": "x" * 65}, {"type": "keyword"}):
            with self.assertRaises(ValueError):
                encode(dict(event, **patch), BOARD_TYPES)
        with self.assertRaises(ValueError):
            encode(event, PC_TYPES)
        with self.assertRaises(ValueError):
            Codec(BOARD_TYPES).feed(b"x" * 8192)


class ConfigurationTests(unittest.TestCase):
    def test_default_selects_afc03_and_reports_missing_hardware(self):
        cfg = load_config(ROOT / "board_app/config/afc03.json")
        self.assertEqual(cfg["fpga_device"], "PH1A90SEG324")
        self.assertTrue(Path(cfg["board_profile"]).is_absolute())
        self.assertEqual(cfg["ocr"]["backend"], "rknn")
        self.assertGreaterEqual(len(missing_integrations(cfg)), 2)

    def test_wrong_npu_target_and_unimplemented_camera_route_fail(self):
        for group, key, value in (("ocr", "target", "rk3588"),
                                  ("camera", "route", "pl_pcie"),
                                  ("camera", "index", -1)):
            with self.subTest(group=group, key=key):
                cfg = load_config(ROOT / "board_app/config/afc03.json")
                cfg[group][key] = value
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "config.json"
                    path.write_text(json.dumps(cfg), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_config(path)

    def test_missing_models_do_not_fall_back_to_simulated_ocr(self):
        result = subprocess.run([sys.executable, str(ROOT / "board_app/run.py"),
                                 "--ocr-image", "not-a-real-image.png"],
                                capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("OCR 尚未接入", result.stderr)
        self.assertNotIn("SIMULATION COMPLETE", result.stdout)

    def test_demo_runs_outside_repo_without_board_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(ROOT / "board_app/run.py"),
                                     "--simulate", "--text", "Hello FPGA 123"], cwd=directory,
                                    capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SIMULATION COMPLETE", result.stdout)
        self.assertIn('"v": 2', result.stdout)

    def test_unknown_prompt_cannot_select_arbitrary_file(self):
        logs = []
        player = PromptPlayer({"enabled": True, "directory": ".", "player": "missing"}, logs.append)
        player.play("../../private", "ignore")
        self.assertIsNone(player.process)
        self.assertIn("未知", logs[0])


class RknnLifecycleTests(unittest.TestCase):
    def test_native_failure_releases_context_and_never_returns_mock_output(self):
        class FakeRuntime:
            def __init__(self, load_result=0, init_result=0):
                self.load_result, self.init_result = load_result, init_result
                self.released = 0

            def load_rknn(self, path):
                return self.load_result

            def init_runtime(self):
                return self.init_result

            def inference(self, **kwargs):
                return None

            def release(self):
                self.released += 1

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test-only.rknn"
            path.write_bytes(b"not a trained model")
            for load, init in ((1, 0), (0, 1)):
                runtime = FakeRuntime(load, init)
                with self.assertRaises(RuntimeError):
                    RknnSession(path, runtime_factory=lambda: runtime)
                self.assertEqual(runtime.released, 1)
            runtime = FakeRuntime()
            session = RknnSession(path, runtime_factory=lambda: runtime)
            with self.assertRaises(RuntimeError):
                session.infer(["test tensor"], ["nhwc"])
            session.close()
            session.close()
            self.assertEqual(runtime.released, 1)


if __name__ == "__main__":
    unittest.main()
