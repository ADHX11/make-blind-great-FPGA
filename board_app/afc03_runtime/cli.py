import argparse
import json
from pathlib import Path
import platform
import sys

from .config import factory, load_config, missing_integrations
from .ocr import CaptureOcr, make_backend
from .prompts import PromptPlayer
from .protocol import BOARD_TYPES, PC_TYPES, Codec, encode, message
from .service import BoardService

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/afc03.json"


def simulate(text):
    # Reference state/Braille implementations are imported ONLY for explicit simulation.
    from blind_fpga_host.braille_reference import show_cells
    from blind_fpga_host.simulator import Keyword, MockBoard, State

    print("=== AFC03 SIMULATION：本机模拟 RK 服务 + PH1A90；无 NPU/KWS/机械打印 ===")
    board = MockBoard()
    rx, tx = Codec(BOARD_TYPES), Codec(PC_TYPES)
    job = "simulated-session:1"

    def dispatch(events):
        for old in events:
            event = message(old["seq"], job, old["type"], **old["payload"])
            print("MOCK PL -> RK", json.dumps(event, ensure_ascii=False))
            for decoded in rx.feed(encode(event, BOARD_TYPES)):
                service.handle(decoded)

    def send(event):
        print("RK -> MOCK PL", json.dumps(event, ensure_ascii=False))
        for decoded in tx.feed(encode(event, PC_TYPES)):
            dispatch(board.receive({"v": 1, "seq": decoded["seq"],
                                    "type": decoded["type"], "payload": decoded["payload"]}))

    service = BoardService(lambda: text, send, lambda ident, phrase: print("PROMPT TEXT ONLY:", phrase))
    try:
        for keyword in (Keyword.START, Keyword.COMPLETE):
            print("[MOCK ONLY] 注入关键词：", keyword.name)
            dispatch(board.inject_keyword(keyword))
        service.pending[1].result(timeout=5)
        service.poll()
        if board.state != State.READY:
            print("SIMULATION FAILED：当前英文参考模型拒绝中文/标点/换行等未支持内容。")
            return 1
        print("[SIM REFERENCE ONLY] 六点单元：", show_cells(board.cells))
        print("[SIM REFERENCE ONLY] 掩码：", " ".join(f"{cell:02x}" for cell in board.cells))
        print("[MOCK ONLY] 注入 PRINT 和运动完成事件")
        dispatch(board.inject_keyword(Keyword.PRINT))
        dispatch(board.finish_print())
        print("SIMULATION COMPLETE：板端服务协议和流程演示完成，未访问摄像头/麦克风。")
        return 0
    finally:
        service.close()


def run_board(cfg):
    if platform.system() != "Linux" or platform.machine().lower() not in ("aarch64", "arm64"):
        raise RuntimeError("--run 用于 AFC03 的 ARM64 Linux；电脑请用 --simulate")
    issues = missing_integrations(cfg)
    if issues:
        raise RuntimeError("硬件模式尚未接通：\n- " + "\n- ".join(issues))
    bridge = factory(cfg["transport"]["factory"])(cfg["transport"])
    player = PromptPlayer(cfg["prompts"])
    service = BoardService(CaptureOcr(cfg), bridge.send, player.play)
    try:
        print("RK 服务启动；等待 PH1A90 事件。没有自动生成关键词或打印完成事件。")
        while True:
            event = bridge.receive(timeout=0.05)
            if event is not None:
                service.handle(event)
            service.poll()
            player.poll()
    finally:
        # Close the link before waiting for native OCR, so a bridge can signal link loss.
        try:
            bridge.close()
        finally:
            player.close()
            service.close()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="AFC03 RK3576J Linux service framework")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--simulate", action="store_true")
    mode.add_argument("--check", action="store_true", help="检查配置及待接入项，不表示已经可上板")
    mode.add_argument("--ocr-image", metavar="PATH", help="只测试真实 OCR，不触发打印")
    mode.add_argument("--run", action="store_true", help="需要厂家 BSP、真实桥接和 OCR 接入")
    parser.add_argument("--text", default=None, help="仅 --simulate 可注入模拟 OCR 文字")
    args = parser.parse_args(argv)
    if args.text is not None and not args.simulate:
        parser.error("--text 只用于显式模拟")
    try:
        cfg = load_config(args.config)
        if args.simulate:
            return simulate(args.text if args.text is not None else "Hello FPGA 123")
        if args.check:
            print("配置有效：AFC03 / RK3576J + PH1A90SEG324")
            print("OCR:", cfg["ocr"]["backend"], "| KWS/盲文/运动目标: PH1A90 PL")
            for issue in missing_integrations(cfg):
                print("PENDING:", issue)
            print("配置检查不是部署验证；引脚、bitstream、KWS 和物理打印还需独立验收。")
            return 0
        if args.ocr_image:
            issues = missing_integrations(cfg, include_transport=False)
            if issues:
                raise RuntimeError("OCR 尚未接入：\n- " + "\n- ".join(issues))
            backend = make_backend(cfg["ocr"])
            try:
                print(backend.recognize(Path(args.ocr_image)))
            finally:
                close = getattr(backend, "close", None)
                if close is not None:
                    close()
            return 0
        run_board(cfg)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, ImportError, AttributeError, KeyError) as exc:
        print("NOT READY / ERROR: " + str(exc), file=sys.stderr)
        return 2
