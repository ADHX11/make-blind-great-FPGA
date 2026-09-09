# 电脑端回归与早期联调（旧入口）

这个目录保留 **电脑仿真**，用于回归“开始 → 放书完成 → 拍照/OCR → 待打印 → 打印完成”的流程。它没有部署 FPGA 模型，也不会驱动真实打印机。当前 AFC03 产品方案已改为板载 RK3576J 承担摄像头/OCR 和提示音，PH1A90 承担关键词、盲文和控制；新入口见 [board_app](../board_app/README.md)。

## 先运行，不需要摄像头和开发板

在本目录使用 Python 3.9 或更新版本执行：

```powershell
python -m blind_fpga_host --simulate --text "Hello FPGA 123"
python -m unittest discover -s tests -v
```

程序显示 `SIMULATION`，通过 MockBoard 自动依次手工注入 START、COMPLETE、PRINT 和 finish_print。**这些注入不是语音识别结果，不会作为正式通信命令发送。** 返回的提示语目前只输出文字，尚未播放录音或调用 TTS。

仿真中的盲文转换是电脑上的英文参考模型：支持 ASCII 大小写字母、数字和空格。点阵 `bit0` 对应点 1，`bit5` 对应点 6；每个大写字母加点 6，数字串前加点 3456，数字后紧接 a–j/A–J 时插入点 56。它不构成完整 UEB 翻译器，不支持缩写、标点、中文或换行。遇到不支持的字符会明确失败并进入 ERROR，绝不会悄悄删除。RTL 的换行是独立事件，尚未在这个参考模型中实现。

## 可选：接入真实电脑摄像头/OCR

摄像头适配器延迟导入 OpenCV。仅运行上述纯仿真命令时，无须安装第三方库。摄像头模式先安装：

```powershell
python -m pip install -r requirements-camera.txt
```

然后自行安装 Tesseract 程序及 `eng`、`chi_sim` 语言包；适配器不会下载软件或模型。将程序放入 PATH 或通过 `--tesseract` 指定它的可执行文件路径。

安装与语言包说明见 [Tesseract 官方文档](https://tesseract-ocr.github.io/tessdoc/Installation.html)，命令格式见 [官方用法](https://github.com/tesseract-ocr/tessdoc/blob/main/Command-Line-Usage.md)。

```powershell
python -m blind_fpga_host --simulate --image "D:\book.png" --ocr-lang eng
python -m blind_fpga_host --simulate --camera 0 --ocr-lang eng
```

默认 OCR 语言是 `eng+chi_sim`，可识别结果通过 `text_result` 返回。中文、多行和标点虽然能通过 JSONL 传输，但会被当前英文参考模型明确拒绝，所以此阶段建议用单行英文和数字检查完整流程。后续添加中文转换模块、排版模块后再放开这些输入。适配器现阶段只有单帧拍照，没有书页矫正或识别质量评估。摄像头/OCR 出错会产生 `ocr_failed`，不会继续打印。

## 文件职责

| 文件 | 当前作用 |
| --- | --- |
| `blind_fpga_host/__main__.py` | 运行仿真，收到拍照事件后获取文字，显示事件和结果 |
| `adapters.py` | OpenCV 拍照适配器、OCR 接口、Tesseract 子进程适配器 |
| `protocol.py` | 拟定的 JSONL v1 编解码及长度/字段/方向检查 |
| `simulator.py` | 电脑运行的 MockBoard 和流程状态机，用于联调契约 |
| `braille_reference.py` | 受限英文参考模型，供测试和比对 |
| `tests/test_host.py` | 分片通信、中文传输、错误、状态顺序及点阵测试 |

## 拟定通信契约

每帧是 UTF-8 JSON 加 LF，最大 8192 字节（包含 LF），格式为 `{"v":1,"seq":0,"type":"text_result","payload":{"text":"Hello"}}`。`seq` 是各发送端独立生成的非负整数，此版仅用于日志关联，没有确认、重传、重复帧过滤或流控机制。

| 方向 | type | payload |
| --- | --- | --- |
| PC → 板卡 | `text_result` | `{"text":"OCR 文字"}` |
| PC → 板卡 | `ocr_failed` | `{"reason":"错误原因"}` |
| PC → 板卡 | `reset` | `{}` |
| 板卡 → PC | `capture_request` | `{}` |
| 板卡 → PC | `prompt` | `{"id":"place_book","text":"提示内容"}` |
| 板卡 → PC | `status` | `{"state":0}` |
| 板卡 → PC | `error` | `{"reason":"错误原因"}` |

状态号：IDLE=0、WAIT_BOOK=1、WAIT_OCR=2、READY=3、PRINTING=4、DONE=5、ERROR=6。测试注入关键词号：START=1、COMPLETE=2、PRINT=3、CANCEL=4、STOP=5。

`START` 只在 IDLE/DONE 有效；`COMPLETE` 只在 WAIT_BOOK 有效并触发拍照；收到有效、非空且能完整转换的文字后进入 READY；`PRINT` 只在 READY 有效。CANCEL 清空任务并回到 IDLE；STOP 清空任务并锁定 ERROR，ERROR 必须显式 reset，CANCEL 不能解除。打印引擎完成信号才可以进入 DONE。非法顺序返回错误且保持原状态。

**真实 UART、UTF-8/JSON 解析器和板卡驱动尚未实现。** 此协议只是未来适配层的设计，不表示当前 RTL 可以直接收 JSON。真实适配器必须先完成文本校验、转换和整个任务的缓冲，再向控制状态机发出 `text_complete`。禁止把 `inject_keyword` 和 `finish_print` 接入生产通信接口；真实关键词应来自 FPGA 推理事件，打印完成应来自硬件控制引擎。暂时没有 `--serial` 功能；未显式传入 `--simulate` 会报错。

## AFC03 当前入口

目标板已改为 RK3576J + PH1A90。上述 host 模拟和 v1 协议保留作回归；产品运行位置已转到板载 RK Linux。请优先从仓库根目录执行 `python board_app/run.py --simulate`，使用 [板端服务说明](../board_app/README.md)。此目录的摄像头/Tesseract 适配器同时被新板端程序复用，因此部署时保留 host 目录。
