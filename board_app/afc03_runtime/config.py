import importlib
import json
from pathlib import Path


def factory(spec):
    """Load an explicitly configured local integration, never download code."""
    if not isinstance(spec, str) or spec.count(":") != 1:
        raise ValueError("接入工厂尚未配置：需要 module:function")
    module, name = spec.split(":")
    result = getattr(importlib.import_module(module), name)
    if not callable(result):
        raise ValueError("接入工厂必须可调用")
    return result


def load_config(path):
    path = Path(path).resolve(strict=True)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1 or cfg.get("platform") != "afc03":
        raise ValueError("仅接受 AFC03 schema_version=1 配置")
    if cfg.get("rk_device") != "rk3576" or cfg.get("fpga_device") != "PH1A90SEG324":
        raise ValueError("本配置目标必须为 RK3576J + PH1A90SEG324")
    if cfg["transport"]["control_protocol"] != "afc03-jsonl-v2":
        raise ValueError("AFC03 需要带任务标识的 v2 控制协议")
    if cfg["ocr"]["target"] != "rk3576":
        raise ValueError("OCR 转换目标必须为 rk3576，不能复用其他芯片的模型")
    if cfg["ocr"]["backend"] not in ("rknn", "tesseract"):
        raise ValueError("OCR backend 必须为 rknn 或 tesseract；模拟不修改产品配置")
    if cfg["camera"]["route"] != "rk_usb_bringup":
        raise ValueError("当前采集器只实现 RK USB 摄像头；PL 帧接收器仍需接入")
    if type(cfg["camera"]["index"]) is not int or cfg["camera"]["index"] < 0:
        raise ValueError("camera.index 必须为非负整数")
    # Freeze relative paths against the config, independent of the working directory.
    cfg["board_profile"] = str((path.parent / cfg["board_profile"]).resolve())
    for key in ("det_model", "rec_model", "charset"):
        cfg["ocr"][key] = str((path.parent / cfg["ocr"][key]).resolve())
    cfg["prompts"]["directory"] = str((path.parent / cfg["prompts"]["directory"]).resolve())
    profile = json.loads(Path(cfg["board_profile"]).read_text(encoding="utf-8"))
    if profile.get("device") != cfg["fpga_device"] or profile.get("platform") != "afc03":
        raise ValueError("板级配置与 AFC03 目标不一致")
    return cfg


def missing_integrations(cfg, include_transport=True):
    issues = []
    if include_transport and not cfg["transport"]["factory"]:
        issues.append("RK↔PH1A90 实际驱动/桥接工厂未接入")
    if cfg["ocr"]["backend"] == "rknn":
        if not cfg["ocr"]["pipeline_factory"]:
            issues.append("PP-OCR 前后处理、裁剪/排序和 CTC 解码工厂未接入")
        for key in ("det_model", "rec_model", "charset"):
            if not Path(cfg["ocr"][key]).is_file():
                issues.append("缺少 OCR 文件：" + cfg["ocr"][key])
    return issues
