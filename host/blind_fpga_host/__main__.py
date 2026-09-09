"""Run with python -m blind_fpga_host --simulate --text 'Hello FPGA 123'."""

import argparse
import json
import sys

from .adapters import OpenCVCamera, TesseractOcr, camera_ocr
from .braille_reference import show_cells
from .protocol import BOARD_TYPES, PC_TYPES, JsonLineCodec, encode, envelope
from .simulator import Keyword, MockBoard, State


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="PC host framework: explicit simulation only; hardware transport is pending")
    parser.add_argument("--simulate", action="store_true", help="在电脑上运行 MockBoard，未部署 FPGA 模型")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="模拟 OCR 返回的文字")
    source.add_argument("--image", help="用 Tesseract 识别现有图片")
    source.add_argument("--camera", type=int, help="摄像头编号；拍照后调用 Tesseract")
    parser.add_argument("--tesseract", default="tesseract", help="Tesseract 可执行程序路径")
    parser.add_argument("--ocr-lang", default="eng+chi_sim")
    args = parser.parse_args(argv)
    if not args.simulate:
        parser.error("硬件 UART/UTF-8/JSONL 适配器尚未实现；当前只能显式使用 --simulate")
    print("=== SIMULATION / 电脑仿真：没有 FPGA 推理、真实关键词识别或机械打印 ===")
    board = MockBoard()
    from_pc, from_board = JsonLineCodec(PC_TYPES), JsonLineCodec(BOARD_TYPES)

    def display(events):
        captured = False
        for event in events:
            for decoded in from_board.feed(encode(event, BOARD_TYPES)):
                print("MOCK BOARD -> PC", json.dumps(decoded, ensure_ascii=False))
                captured |= decoded["type"] == "capture_request"
        return captured

    def inject(keyword):
        print(f"[MOCK ONLY] 手工注入 {keyword.name}，不是麦克风/KWS 推理结果")
        return display(board.inject_keyword(keyword))

    def send(message):
        print("PC -> MOCK BOARD", json.dumps(message, ensure_ascii=False))
        for decoded in from_pc.feed(encode(message, PC_TYPES)):
            display(board.receive(decoded))

    inject(Keyword.START)
    if not inject(Keyword.COMPLETE):
        return 1
    try:
        backend = TesseractOcr(args.tesseract, args.ocr_lang)
        if args.image:
            text = backend.recognize(args.image)
        elif args.camera is not None:
            text = camera_ocr(OpenCVCamera(args.camera), backend)
        else:
            text = args.text if args.text is not None else "Hello FPGA 123"
        send(envelope(0, "text_result", text=text))
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        send(envelope(0, "ocr_failed", reason=str(exc)))
    if board.state != State.READY:
        print("SIMULATION FAILED：没有开始打印；请检查上面的明确错误。")
        return 1
    print("[PC REFERENCE ONLY] 六点单元：", show_cells(board.cells))
    print("[PC REFERENCE ONLY] 点阵掩码：", " ".join(f"{cell:02x}" for cell in board.cells))
    inject(Keyword.PRINT)
    print("[MOCK ONLY] 注入 finish_print；未发送电机或打点脉冲")
    display(board.finish_print())
    print("SIMULATION COMPLETE：仅验证消息和流程；提示语只输出文字，尚未播放音频。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
