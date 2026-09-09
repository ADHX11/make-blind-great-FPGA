# make-blind-great-FPGA

基于 BrailleRAP 机构的语音交互盲文打印机，当前目标改为 **AFC03：RK3576J + 安路 PH1A90SEG324**。

目标流程：说“开始” → 提示放书 → 说“完成” → 板上拍照/OCR → FPGA 转盲文并排版 → 说“打印” → FPGA 控制机械打点。最终运行不依赖电脑，暂不做连续 ASR。

> 当前是可运行模拟和测试的开发框架，**不是可烧录的完整产品**。OCR 权重/前后处理、AMS 权重/算子、中文规则、板间驱动、板级顶层和机械控制还需接入。没有将电脑模拟改名为板上推理。

## 两颗芯片的分工

| 位置 | 产品目标 | 当前代码 |
| --- | --- | --- |
| RK3576J，ARM64 Linux + NPU | 摄像头服务、OCR 检测/识别、短录音播放、日志 | 新增板端服务、异步 OCR 调度、RKNNLite 生命周期和 PP-OCR 接入接口、WAV 播放器 |
| PH1A90，可编程逻辑 PL | AMS 多关键词推理、主流程、中英文盲文、页面排版、XY/打点、限位 | 保留可移植流程及基础英文 RTL；KWS/中文为禁用槽位，运动输出保持禁用 |
| PH1A90 图像通路 | 后续摄像头接入 PL，做预处理并向 RK 传帧 | 接口与开发阶段规划，未实现图像处理 IP |
| Windows 电脑 | 编写程序、模型准备、下载 FPGA、调试与模拟 | 继续可用，不要求安装双系统 |

摄像头先接 **RK 的 USB** 跑通板载 OCR；之后按厂家 BSP 接入 PL 图像通路。数字麦克风目标接 **PH1A90**，板载 MIC/音频口不能默认归 PL。OCR 在 RK NPU，AMS 在安路 PL，两者分别提供实测证据。

## 现在怎么测试

在 Windows PowerShell 中，从仓库根目录执行，Python 3.9+，模拟无需额外依赖：

```powershell
cd "D:\HuaweiMoveData\Users\fyx06\Desktop\BrailleRap-master\BrailleRap-master"
python board_app/run.py --simulate --text "Hello FPGA 123"
python board_app/run.py --check
python -m unittest discover -s board_app/tests -v
```

第一条演示 **RK 服务 + 模拟 PH1A90** 的 v2 消息和工作流。关键词和打印完成均为明确标注的手工模拟事件；参考盲文仍在电脑计算。输入中文会在当前模拟 PL 中被明确拒绝，不能据此声称中文转换完成。

第二条检查默认 AFC03 配置，并列出缺少的模型和桥接；检查成功不代表硬件准备完成。旧电脑模拟与 12 项回归测试保留在 [host](host/README.md)。

完整板端使用方法见 [board_app/README.md](board_app/README.md)，上板步骤见 [Linux 部署说明](docs/fpga/afc03_linux.md)。

## 工程目录

```text
board_app/                  新增 RK3576J Linux 服务与 AFC03 模拟入口
  config/afc03.json          当前默认目标、摄像头、OCR、提示音、板间桥接配置
  afc03_runtime/            事件服务、v2 协议、RKNN 接入、录音播放
  tests/                    无硬件回归测试
fpga/rtl/                   与具体板卡解耦的 PL 应用核心
fpga/boards/anlogic_afc03/   当前 AFC03 配置和待确认引脚表
fpga/boards/anlogic_dr1/     旧 DR1 方案留档，不是当前目标
fpga/sim/                   RTL 静态检查与行为测试台
host/                       原电脑模拟、英文参考和可复用摄像头/Tesseract 适配器
models/ocr/                 RK3576 PP-OCR 检测+识别模型接入说明
models/kws/                 PH1A90 AMS 模型交接清单
docs/fpga/                  架构、接口、部署顺序和验证记录
README_UPSTREAM.md          原 BrailleRAP 说明
MarlinBraille/              原 MKS/AVR 固件参考
printed_parts/、lasercut/   原机构文件
```

[架构与 FPGA 主体性](docs/fpga/architecture.md) · [通信/RTL 接口](docs/fpga/interfaces.md) · [开发路线](docs/fpga/roadmap.md) · [验证记录](docs/fpga/validation.md)

当前按安路自主命题组织功能。AFC03 是选题三的推荐平台，但仅实现 OCR + KWS + 盲文打印不能自动满足选题三的全部要求，详见架构说明。

## 上游与许可

本项目基于 [BrailleRAP](https://github.com/braillerap/BrailleRap)，保留机构、文档和原固件。原说明见 [README_UPSTREAM.md](README_UPSTREAM.md)，许可见 [LICENCE.txt](LICENCE.txt) 及各组件声明。新增框架代码尚未另行指定许可；不改变上游组件自身许可。
