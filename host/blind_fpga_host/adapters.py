"""Optional PC camera/OCR adapters; dependencies are never auto-downloaded."""

from pathlib import Path
import subprocess
import tempfile
from typing import Protocol


class OcrBackend(Protocol):
    def recognize(self, image_path: Path) -> str: ...


class TesseractOcr:
    def __init__(self, executable="tesseract", language="eng+chi_sim"):
        self.executable = executable
        self.language = language

    def recognize(self, image_path):
        image_path = Path(image_path).resolve(strict=True)
        try:
            result = subprocess.run(
                [self.executable, str(image_path), "stdout", "-l", self.language],
                capture_output=True, timeout=90, check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("找不到 Tesseract；请安装程序和所需语言包，或指定 --tesseract 路径") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Tesseract OCR 超时（90 秒）") from exc
        if result.returncode:
            raise RuntimeError("Tesseract OCR 失败：" + result.stderr.decode("utf-8", errors="replace").strip())
        return result.stdout.decode("utf-8").strip()


class OpenCVCamera:
    def __init__(self, index=0):
        self.index = index

    def capture(self, destination):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("摄像头模式需要安装 opencv-python") from exc
        camera = cv2.VideoCapture(self.index)
        try:
            if not camera.isOpened():
                raise RuntimeError(f"无法打开摄像头 {self.index}")
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("摄像头未返回有效图像")
            if not cv2.imwrite(str(destination), frame):
                raise RuntimeError("无法保存拍摄图像")
        finally:
            camera.release()


def camera_ocr(camera, backend):
    with tempfile.TemporaryDirectory(prefix="blind_fpga_") as directory:
        path = Path(directory) / "capture.png"
        camera.capture(path)
        return backend.recognize(path)
