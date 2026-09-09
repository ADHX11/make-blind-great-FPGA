# 框架验证记录

## AFC03 改版：2026-09-09

当前默认平台已改为 RK3576J + PH1A90SEG324；新增 board_app 板端服务与 v2 协议。以下结果来自本机测试，未使用开发板或真实外设。

| 检查 | 结果 |
| --- | --- |
| 新 AFC03 单元测试 | 15 项通过；最终在用户 Python 3.9.0 验证，首轮也在 Python 3.12 通过 |
| 旧 host 回归测试 | 12 项通过，Python 3.12 |
| 新模拟入口 | Hello FPGA 123 到达模拟 DONE；测试还验证从仓库外目录启动 |
| 任务隔离 | 取消/停止后旧 OCR 丢弃；新任务不接收旧结果；同时最多一个 OCR 作业 |
| UTF-8 与错误处理 | 原始中英文/换行原样传输；空文本、超长文本、异常返回 ocr_failed，不截断文字 |
| 模型缺失与目标配置 | 缺模型/前后处理不会回退为假 OCR；错误 RK 目标和未实现 PL 相机路由被拒绝 |
| RKNN 会话生命周期 | 用测试替身验证加载/初始化失败后释放；不代表 NPU 实测 |
| 默认配置检查 | AFC03 型号正确，明确列出缺少模型与板间/OCR 工厂 |
| Markdown / JSON | 14 份说明的本地链接无缺失，5 份 JSON 可解析 |
| RTL 静态语义/展开 | 0 条诊断；应用 RTL 功能未因换板重写，仅更新目标说明 |
| RTL 行为仿真 | 工具缺失，仍为 NOT RUN |
| 安路综合/时序/下载、摄像头/NPU/音频、AMS/中文、实物打印 | 未运行或尚未实现，不宣称已完成 |

从仓库根目录复现新增测试：

```powershell
python -m unittest discover -s board_app/tests -v
python board_app/run.py --simulate --text "Hello FPGA 123"
python board_app/run.py --check
```

模拟只使用显式测试事件；真实 --run 仍需厂商 BSP、桥接模块和完整 OCR 接入。下方保留改版前基础框架的验证记录。

## 基础框架历史记录

日期：2026-09-09。环境：Windows，Python 3.12，pyslang 11.0.0。这里记录本次实际完成的验证，供区分电脑模拟、RTL 静态检查和未来板测。

| 检查 | 本次结果 | 能说明什么 |
| --- | --- | --- |
| PC 单元测试 | 12 项通过 | 消息分片/UTF-8/长度/错误方向、流程顺序、取消/停止、有限英文点阵 |
| Hello FPGA 123 演示 | 正常到达 DONE | 电脑 MockBoard 流程与消息联调成功，不代表实物打印 |
| 中文输入负向测试 | ERROR、非零退出 | 当前不支持中文时明确拒绝，未悄悄删除文字或错误打印 |
| 全部 RTL + 集成测试台的 pyslang 检查 | 0 条诊断 | SystemVerilog 语法、语义及模块展开可检查通过 |
| Icarus 行为仿真 | 未运行；工具缺失，运行器明确报 NOT RUN | 尚不能据此声称波形或测试台行为通过 |
| 原 README 保留 | 与 HEAD 中原 README 文本相同 | 原项目来源说明保留 |
| 新配置 JSON 与文档本地链接 | 已检查 | 配置可解析，项目说明可导航 |
| 安路综合、布局布线、时序、引脚 | 未运行 | 还没有可下载 bitstream 和资源/频率实测 |
| 摄像头、Tesseract、音频、模型、实体打印 | 未实测 | 需要依赖、实际外设、模型与板级工程接入 |

## 复现 PC 测试

从仓库根目录：

```powershell
cd host
python -m unittest discover -s tests -v
python -m blind_fpga_host --simulate --text "Hello FPGA 123"
python -m blind_fpga_host --simulate --text "中文测试"
```

最后一条预期失败，不能把该退出码当作回归。正常英文示例得到 20 个六点单元：

```text
20 13 11 07 07 15 00 20 0b 20 0f 20 1b 20 01 00 3c 01 03 09
```

## RTL 静态检查

从仓库根目录执行；可在自己的虚拟环境安装可选验证工具：

```powershell
python -m pip install pyslang==11.0.0
python fpga/sim/check_syntax.py
```

这不会运行时钟周期或厂家综合。缺少 pyslang 时脚本返回未运行和非零状态。

## RTL 行为仿真

安装 Icarus Verilog 并将 `iverilog`、`vvp` 放到 PATH 后，从仓库根目录执行：

```powershell
python fpga/sim/run.py
```

测试台覆盖计划：工作流、错误优先级、大写/数字/字母标志、LF 事件、背压稳定、文本排空、空白任务拒绝、取消清空、停止锁定、禁用物理输出与未实现模型槽位。当前仅完成对测试台本身的静态检查；要实际运行并看到 PASS 才能记录行为仿真通过。
