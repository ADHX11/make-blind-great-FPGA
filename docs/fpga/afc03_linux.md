# AFC03 板载 Linux 部署顺序

Windows 电脑继续用于编辑、下载和调试。这里部署的 Linux 在 **AFC03 的 RK3576J** 上；不要求电脑先装 Linux 双系统。PH1A90 仍需单独使用安路工具生成并下载 FPGA 配置。

## 1. 准备对应板卡的厂家资料

取得实物版本对应的 BSP 镜像/刷写说明、烧录工具、原理图、RK NPU 驱动与 Runtime 版本、PH1A90 点灯工程，以及 MIPI/PCIe 板间通信例程。指南平台 3 的资料地址是资料入口，不等于已经核对了某个 Linux 镜像。

不要把普通 PC 的 x86 Ubuntu 安装镜像写到板卡。按厂家说明刷写该板 ARM64 镜像；此操作可能覆盖板上 eMMC，先保留厂家恢复镜像与自己的数据。当前仓库没有执行任何刷写。

## 2. 单独验证两颗芯片

RK 使用厂家说明的显示器/键盘或调试串口登录；网络启用后可用 Windows PowerShell 的 SSH。串口此处是调试登录方法，不代表产品必须用串口传图。

在板上查看：

```bash
uname -m
cat /etc/os-release
python3 --version
```

确认 ARM64、BSP 系统和 Python 版本。再独立编译下载厂家 PH1A90 点灯例程。两侧都可运行后，再做板间联调。

## 3. 放入项目并运行无硬件模拟

将仓库复制/同步到板上自己的目录，保留 board_app、host、models、fpga 和 docs。下面从仓库根目录执行：

```bash
python3 board_app/run.py --simulate --text "Hello FPGA 123"
python3 board_app/run.py --check
python3 -m unittest discover -s board_app/tests -v
```

此时在板上运行模拟依旧不代表 PH1A90 推理成功。

## 4. 摄像头、声卡与模型依赖

先用厂家相机/音频测试程序验证 USB 摄像头和扬声器。OpenCV 必须能读取目标设备；单次拍摄适配器当前取一帧，实际曝光稳定性、对焦和失败重试还需联调。板载音频接口的归属按原理图确认，AMS 麦克风路径目标在 PL。

按 BSP 提供的方式安装 Python OpenCV 和 ALSA 工具；若 BSP 是 Debian/Ubuntu 且支持这些包，可在板上使用：

```bash
sudo apt update
sudo apt install python3-venv python3-opencv alsa-utils
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

NPU 使用与 BSP 驱动、ARM64 和 Python 版本兼容的 RKNN Toolkit Lite2/Runtime，不盲目安装最新版本。优先在厂家参考例程上验证，再向当前虚拟环境安装对应 wheel。开发电脑的模型转换用 RKNN Toolkit2，板上推理用 Lite2/Runtime；需要 Linux 转换环境时再配置兼容的 WSL2/虚拟机或厂家推荐环境，不需要为此改电脑分区。

模型和前后处理接入步骤见 [OCR 模型清单](../../models/ocr/README.md)。核对检测和识别都转换为 rk3576，且字符字典相同版本。真实 OCR 命令：

```bash
python3 board_app/run.py --ocr-image /path/to/book-page.png
```

默认工程会明确报告模型/接入工厂缺失；当前未提供可直接运行的 PP-OCR 整套部署包。

## 5. 接 PH1A90 事件

运行厂家板间回环例程，确认控制及帧传输方向、驱动/缓冲机制，再实现 [桥接工厂](interfaces.md)。第一阶段摄像头接 RK USB，不把整帧塞进 JSONL。按 [PH1A90 板级步骤](../../fpga/boards/anlogic_afc03/README.md) 连接实际应用核心。

填好配置并验证全部依赖后运行：

```bash
python3 board_app/run.py --run
```

服务等待 PL 拍照/提示事件，不会自己伪造关键词启动打印。先用调试/受限测试信号联调文字和点阵，再替换为真实 AMS 输出；演示时明确区分两阶段。

## 6. 完成产品验收

仍需 AMS 定点模型、中文转换、页面缓冲、机械回零/驱动、急停、掉线/超时、提示音回声与整页容量验证。自启服务、性能优化和最终视频在完整链路稳定后再配置。步骤和证据要求见 [开发路线](roadmap.md)。

软件路径依据：[RKNN Toolkit2 官方说明](https://github.com/airockchip/rknn-toolkit2)、[RKNN Model Zoo](https://github.com/airockchip/rknn_model_zoo)。板卡具体操作始终以 AFC03 对应版本 BSP 为准。
