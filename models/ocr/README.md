# RK3576 板载 OCR 接入

目标是 PP-OCR 的“文字检测 + 文字行识别”，在 AFC03 的 RK3576 NPU 推理。原始中英文文字交给 PH1A90 转盲文。当前仓库没有模型权重、字符字典或完整 PP-OCR 图像前后处理，不能直接运行真实 OCR。

[官方 RKNN Toolkit2](https://github.com/airockchip/rknn-toolkit2) 支持 RK3576 的模型转换与部署；[官方 PP-OCR Det](https://github.com/airockchip/rknn_model_zoo/tree/main/examples/PPOCR/PPOCR-Det) 和 [PP-OCR Rec](https://github.com/airockchip/rknn_model_zoo/tree/main/examples/PPOCR/PPOCR-Rec) 可作为接入起点。应固定实际使用的提交/模型版本，不跟随主分支随意更换。

## 所需资产

1. 支持中文及英文的检测/识别模型、匹配字符字典与上游许可。
2. 用兼容版本 RKNN Toolkit2 转换，**target_platform=rk3576**，先确认精度，再决定是否量化及如何标定；不要拿 rk3588/rk3566 的 .rknn 顶替。
3. 记录模型形状、通道顺序、dtype、布局和归一化归属，避免 Toolkit 转换与运行前处理重复归一化。
4. 将模型放入本目录 weights/；默认文件名见 board_app/config/afc03.json。该目录已忽略，不自动提交大权重。
5. 完善 [manifest.example.json](manifest.example.json) 的版本、校验值与板测记录。目前它是人工交接模板，运行器不根据它自动验真模型。

## 前后处理工厂接口

新代码的 RknnSession 已封装 `RKNNLite.load_rknn → init_runtime → inference → release`，检测和识别分别有独立会话；加载/初始化/推理失败直接报错，不回退为假输出。

在运行配置中指定 `ocr.pipeline_factory = "your_ppocr:make_pipeline"`。模块由你接入的本地代码提供，工厂收 ocr 配置，返回实现以下方法的对象：

```python
def make_pipeline(ocr_config):
    return YourPpOcrPipeline(ocr_config)

# YourPpOcrPipeline.recognize(image_path, det_infer, rec_infer) -> 原始 str
# det_infer(inputs=[tensor], data_format=["nhwc"]) -> 输出张量列表
# rec_infer(inputs=[tensor], data_format=["nhwc"]) -> 输出张量列表
# nhwc 仅演示调用形式，实际布局必须与导出的模型匹配。
```

这个工厂不是已实现的 OCR 算法。它需要完成图像读取/方向与缩放 → 检测输入 → det_infer → 检测框后处理 → 阅读顺序排序与旋转裁剪 → 识别输入 → rec_infer → CTC/字典解码 → 原文拼接。先做单栏、摆正书页；多栏/曲面及超长行后续专门验证。

官方示例中的模型执行器有开发主机与板端调用差异，不能直接把两个示例脚本拼起来就认为完成板载端到端 OCR；移植时保留匹配的前后处理，以本仓库回调调用板端 Lite2。这里没有复制上游整套代码，也没有编造默认的检测阈值、张量形状或模型结果。

## 板测

先运行 `python3 board_app/run.py --ocr-image /path/to/page.png`，记录原图、识别文本、模型及 BSP/Runtime 版本、检测和识别耗时、峰值内存、中文/英文准确率。再接摄像头与 PH1A90。

CPU 上 Tesseract 只用于临时通路联调，必须注明 CPU OCR；不能用它的结果或速度证明 NPU 部署。2 GB 内存下先单帧、单 OCR 任务，避免同时启用多模型与大量高分辨率缓存；实际可用内存和效果以板测为准。
