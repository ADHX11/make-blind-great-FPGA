# AFC03 的 RK3576J 服务

本目录面向板上的 ARM64 Linux。电脑仍可运行无依赖模拟。Python 3.9+；启动器从同一仓库的 host 目录复用摄像头/Tesseract 适配器，部署时保留这两个目录。

## 本机验证

从仓库根目录：

```powershell
python board_app/run.py --simulate --text "Hello FPGA 123"
python board_app/run.py --check
python -m unittest discover -s board_app/tests -v
```

--simulate 显式创建模拟 PH1A90，手工注入关键词、模拟 OCR 文本和打印完成；不加载 RKNN、不采集外设。--text 只允许用于模拟。模拟 PL 目前仅接受基础英文、数字和空格。

## 板端接入

默认 [config/afc03.json](config/afc03.json) 指向 AFC03 和 RK3576 NPU。所有文件路径相对配置文件解析，不依赖当前终端目录。

1. 准备厂家 BSP、Python/摄像头/声卡，见 [Linux 步骤](../docs/fpga/afc03_linux.md)。
2. 依照 [OCR 清单](../models/ocr/README.md) 放入检测/识别 .rknn 及字典，接入与模型严格匹配的 PP-OCR 前后处理工厂。
3. 实现 transport.factory 对应的厂家板间驱动适配对象，接口见 [通信约定](../docs/fpga/interfaces.md)。
4. 录制 [提示音](assets/prompts/README.md)，验证声卡后将 prompts.enabled 设为 true。
5. 先独立测试图像，再连接 PL 事件循环：

```bash
python3 board_app/run.py --ocr-image /path/to/book-page.png
python3 board_app/run.py --run
```

默认配置缺少模型和工厂，以上真实模式会报告 NOT READY，绝不自动回退为模拟输出。--run 限定 ARM64 Linux；不代表仅凭架构检测就验证了真实板卡。

临时 CPU OCR 联调：复制配置为同目录下 afc03.local.json，将 ocr.backend 改为 tesseract；在板上安装 Tesseract 及语言包。日志应标明 CPU 模式，不能称为 NPU 推理。摄像头仍由 RK 服务使用，不转回电脑承担产品功能。

## 程序职责

- service.py：接收 PL 状态与拍照事件；后台运行单个 OCR 作业；回传原始文字或错误；取消后丢弃迟到结果。
- protocol.py：v2 JSONL，包含 session 唯一的 job；长度上限 8192 字节；与旧 host v1 不直接兼容。
- ocr.py：RKNNLite 检测/识别会话及 PP-OCR 工厂接口；本文件没有假定特定模型归一化/张量布局。
- prompts.py：根据受限提示 ID 播放本地 WAV；播放不占用主事件循环。
- cli.py：明确区分模拟、配置检查、单图 OCR 和真实运行。

真实服务不会生成关键词、盲文点阵或打印完成事件。它只在 FPGA 处于 WAIT_OCR 且任务匹配时响应拍照。

## 尚未完成的产品功能

厂家桥接及其 RTL、分片分页/ACK/超时、心跳与重连、页面排序、可视界面、相机稳定曝光、提示音回声处理等仍待实现。OCR 使用单工作线程，取消会丢弃结果但不会强杀正在进行的原生 NPU 调用；新任务遇到旧任务仍执行时返回忙错误。退出可能等待该调用结束，因此真实 PL 必须有独立故障处理，不能依赖 Python 线程实现急停。

启动服务目前需要手工命令；在完成异常/重连验收前，不默认安装后台自启服务。
