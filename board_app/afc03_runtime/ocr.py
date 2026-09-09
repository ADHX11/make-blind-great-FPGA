"""Board OCR lifecycle. No trained weights or guessed PP-OCR preprocessing."""
from pathlib import Path

from blind_fpga_host.adapters import OpenCVCamera, TesseractOcr, camera_ocr
from .config import factory


class RknnSession:
    """One RKNNLite model on the RK3576. Factory injection is for unit tests."""
    def __init__(self, model_path, runtime_factory=None):
        path = Path(model_path).resolve(strict=True)
        if path.suffix != ".rknn":
            raise ValueError("板端只加载已转换的 .rknn 模型")
        if runtime_factory is None:
            from rknnlite.api import RKNNLite
            runtime_factory = RKNNLite
        self.runtime = runtime_factory()
        try:
            if self.runtime.load_rknn(str(path)) != 0:
                raise RuntimeError("RKNN load_rknn 失败：" + str(path))
            if self.runtime.init_runtime() != 0:
                raise RuntimeError("RKNN init_runtime 失败；核对模型、BSP、驱动和 Lite2 版本")
        except Exception:
            self.close()
            raise

    def infer(self, inputs, data_format):
        # Shapes, dtype, RGB/BGR and normalization belong to the versioned pipeline.
        outputs = self.runtime.inference(inputs=inputs, data_format=data_format)
        if outputs is None:
            raise RuntimeError("RKNN inference 未返回结果")
        return outputs

    def close(self):
        if self.runtime is not None:
            self.runtime.release()
            self.runtime = None


class RknnPpOcr:
    def __init__(self, cfg):
        if cfg["target"] != "rk3576":
            raise ValueError("RKNN target must be rk3576")
        self.det = self.rec = None
        self.pipeline = factory(cfg["pipeline_factory"])(cfg)
        if not callable(getattr(self.pipeline, "recognize", None)):
            raise ValueError("PP-OCR 工厂必须返回 recognize(image_path, det_infer, rec_infer) 对象")
        try:
            self.det = RknnSession(cfg["det_model"])
            self.rec = RknnSession(cfg["rec_model"])
        except Exception:
            self.close()
            raise

    def recognize(self, image_path):
        image_path = Path(image_path).resolve(strict=True)
        text = self.pipeline.recognize(image_path, self.det.infer, self.rec.infer)
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("PP-OCR 未返回非空文字；不要返回已翻译的盲文")
        return text

    def close(self):
        if self.rec is not None:
            self.rec.close()
        if self.det is not None:
            self.det.close()


def make_backend(cfg):
    if cfg["backend"] == "tesseract":
        return TesseractOcr(cfg["tesseract"], cfg["language"])
    return RknnPpOcr(cfg)


class CaptureOcr:
    """Create and release RKNN contexts in the same OCR worker thread."""
    def __init__(self, cfg):
        self.cfg = cfg

    def __call__(self):
        backend = make_backend(self.cfg["ocr"])
        try:
            return camera_ocr(OpenCVCamera(self.cfg["camera"]["index"]), backend)
        finally:
            close = getattr(backend, "close", None)
            if close is not None:
                close()
