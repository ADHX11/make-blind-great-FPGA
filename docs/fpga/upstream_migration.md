# 原 BrailleRAP 到 FPGA 的迁移边界

## 已有资产

`MarlinBraille` 含完整 Marlin C/C++ 固件：G-code 解析、运动规划、步进中断等，`Version.h` 标记版本 1.1.8。它针对 MKS/AVR 环境，不是可直接综合的 Verilog。`NatBrailleTools` 是上游已标注过时的 Java 工具，没有本项目所需的中文分词、读音消歧、OCR 或 AMS 模型。

保留 `printed_parts`、`lasercut`、原文档及原固件，作为机构与机械流程依据。新 FPGA 框架目前没有覆盖或修改原固件。

## 机械流程需要保留的含义

| 原始实现 | FPGA 迁移处理 |
| --- | --- |
| `Configuration.h` 的 X_HOME_DIR=-1、Y_HOME_DIR=+1、PAPER_LOADING_HOME_Y | X 回零和 Y 找纸边/上纸分开实现；不能直接写成完全对称的 XY 回零 |
| `Marlin_main.cpp` 的 homeaxis_paperload()，Y 正向仍检查 YMIN | 依据实际传感器和走纸机构复现；加最大步数和超时 |
| `planner.cpp`、`stepper.cpp` 运动缓冲和加减速/中断发脉冲 | 改为运动 FIFO、坐标转步数、硬件 STEP/DIR 时序及加减速逻辑 |
| `M3 S1` 等电磁铁控制 | 改为等待运动完成后才能启动的有限时长打点状态机 |
| Java 输出 G-code 与退纸序列 | 提取机械语义，改为可配置的 PL 排版和退纸，避免固定页面尺寸 |

源文件入口：[Configuration.h](../../MarlinBraille/Configuration.h)、[Marlin_main.cpp](../../MarlinBraille/Marlin_main.cpp)、[planner.cpp](../../MarlinBraille/planner.cpp)、[stepper.cpp](../../MarlinBraille/stepper.cpp)、[endstops.cpp](../../MarlinBraille/endstops.cpp)。

## 参数仅供校准起点

| 参数 | 原源码值 | 使用限制 |
| --- | --- | --- |
| X / Y 步数每毫米 | 160 / 87 | 与细分、带轮和走纸机构相关，实机重新标定 |
| 点间距 | 2.3 × 2.3 mm | 原 Java 工具值，需要与实际采用盲文规范和纸面质量核对 |
| 字符横向间距 / 行距 | 6.1 / 10 mm | 作为机械布局参考，不宣称标准符合性 |
| 电磁铁打开 / 关闭等待 | 25 / 25 ms | 来自 Configuration_adv.h 的实际 M3 路径；按电磁铁与电源校准 |

`Configuration.h` 虽定义了 `BRAILLERAP_ELECTROMAGNET_DELAY=50`，本次审查未找到其调用；不可据此声称有效脉冲宽度就是 50 ms。原 BED/E0 MOSFET 输出名称也不是安路 PL 管脚号。

## 新增待实现模块

页面缓冲、六点排版、运动 FIFO、X 回零、Y 上纸、加減速、两轴时序、打点与冷却等待、限位、故障超时、断点/退纸策略。只有这些接通并在实物上完成单点→单格→单行→整页验证，才进入真正打印阶段。

原代码中的字符表有工具特定编码约定，不直接当作完整英语或中文盲文规范。新增英文 RTL 使用显式受限映射，中文保留独立实现位置。

## 原始说明

已将原根说明逐字保存在 [README_UPSTREAM.md](../../README_UPSTREAM.md)。CERN-OHL-P-2.0、Marlin 源文件许可和其他组件声明仍保留在原路径。
