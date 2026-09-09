# AFC03 控制协议 v2 与 PL 应用接口

新增板端程序使用带任务标识的 **v2**。旧 host 程序的 v1 仍用于回归，不能直接连接 v2 服务。两者都只是软件适配层协议，尚未实现厂家驱动、RTL JSON 解析或字节到字符的桥接。

## 控制消息

UTF-8 JSONL，每帧以 LF 结束，最多 8192 字节（含 LF）。字段严格校验：

```json
{"v":2,"seq":0,"job":"bridge-boot-uuid:1","type":"text_result","payload":{"text":"Hello FPGA 123"}}
```

| 方向 | type | payload |
| --- | --- | --- |
| RK → PL 桥接 | text_result | text：OCR 原始文字，含中文/换行时不得删改 |
| RK → PL 桥接 | ocr_failed | reason：失败说明 |
| RK → PL 桥接 | reset | 空对象；供明确维护操作，服务不会自动发送 |
| PL 桥接 → RK | capture_request | 空对象 |
| PL 桥接 → RK | prompt | id、text；提示 ID 见后表 |
| PL 桥接 → RK | status | state：0–6 |
| PL 桥接 → RK | error | reason |

job 由真实桥接在新一轮任务时分配，包含本次启动/连接的唯一标识与递增任务号；同一服务连接内不得复用。初始化 IDLE 也使用有效标识。seq 为每方向整条连接上递增的序号，不能每个任务归零；目前 RK 会丢弃重复或逆序事件。

PL 桥接必须先发送当前任务的 status=WAIT_OCR，再发 capture_request。重复拍照请求只处理一次。取消/停止/其他离开 WAIT_OCR 的状态会使 OCR 结果失效；新任务须用新 job。RK 收到结果后还需桥接再次检查状态和 job，因为取消可能刚发生而状态事件尚在链路中。

当前没有自动重连、ACK、分片分页、序号缺口恢复或心跳。实际驱动需保障消息顺序与完整交付；断开/PL 复位必须废弃旧会话并安全停止，不能在旧服务内直接复用序号和任务。全页超长文本明确报 ocr_failed，不能静默截断成“成功的一页”。

## 厂家桥接工厂

在 board_app/config/afc03.json 配置 transport.factory 为本地 module:function。工厂接收 transport 配置并返回对象：

```python
def make_bridge(config):
    # 使用本板 BSP 实现，当前仓库未提供实际对象。
    return BoardBridge(config)

# BoardBridge.receive(timeout=0.05) -> 一个已解码的 v2 dict，超时返回 None
# BoardBridge.send(event)          -> 发送 RK 响应，校验长度/方向后提交
# BoardBridge.close()              -> 释放通道并触发约定的链路退出处理
```

receive 必须按 timeout 有界返回，断链抛出异常；send 也需要有界超时。字节流适配可复用 afc03_runtime.protocol.Codec / encode。此 Python 工厂只适配真实驱动，不允许用 MockBoard 作为 --run 的“硬件桥接”。

RTL 侧须完成时钟域转换、事件缓冲、UTF-8 解码、文本容量与 job 校验、ready/valid 对接。当前核心没有 job 端口，任务管理先由桥接模块承担，并与 PL 的 job_clear/状态同步。若采用二进制硬件帧，在桥接中明确定义与 v2 的映射；不要求用 FPGA 直接解析通用 JSON。

## 帧通道独立于控制通道

MIPI/PCIe 的帧描述至少包含 frame_id、任务关联、时间戳、宽高、行跨度、像素/压缩格式、有效字节数和缓冲生命周期。必须验证 DMA 缓存一致性、所有权及帧完成后才能 OCR。这里只列需求，没有杜撰 BAR 地址、设备节点或硬件寄存器。

第一阶段 USB 摄像头由 RK 拍照，尚不需要帧通道。切换 PL 摄像头后，应把 CaptureOcr 中的图像来源替换为真实帧接收器，仍由 RK 执行 OCR。使用 MIPI 传图时，返向控制需另行确认；不能假设 MIPI 自动携带双向 JSONL。

## RTL 核心端口

顶层：`blind_printer_core`。所有应用接口在同一 `clk` 域工作。`rst_n` 为低有效复位；板级层负责可靠复位释放与跨时钟/异步输入同步。

| 端口 | 方向 | 约定 |
| --- | --- | --- |
| keyword_valid / keyword_id[2:0] / keyword_ready | 入/出 | valid 与 ready 同时为 1 时采样关键词事件。上游负责去重，不能将一个识别事件无限保持 valid |
| text_valid / text_ascii[7:0] / text_ready | 入/出 | 在 WAIT_OCR 接受字符；valid 等待时保持字符稳定 |
| text_complete | 入 | 最后一个字符握手完成后发一个周期；核心等在途单元输出排空后才进入 READY |
| text_error | 入 | 无有效文字、无法解码、缓冲溢出、OCR 或文本错误 |
| cell_valid / cell_bits[5:0] / cell_newline / cell_ready | 出/入 | 输出 ready/valid 流；cell_newline=1 时为布局事件，不能打印其 cell_bits；bit0=点1…bit5=点6 |
| capture_req | 出 | 请求 RK 拍照的一周期事件 |
| prompt_valid / prompt_id[2:0] | 出 | 一周期提示事件，适配层映射到 RK 消息 |
| start_print | 出 | 进入 PRINTING 时的一周期启动事件 |
| print_done / print_error | 入 | 真正运动控制器的完成/故障；不能用文本发送完成代替 |
| job_clear | 出 | 清空外部文本/点阵/运动任务缓冲的一周期事件 |
| estop | 入 | 急停状态，高有效；适配实体急停与独立断电路径 |
| state / error_latched | 出 | 状态与锁定错误 |
| unsupported / unsupported_ascii | 出 | 不支持字符事件及字节值，用于诊断 |
| x_step / x_dir / y_step / y_dir / punch_enable / motion_enable | 出 | 框架恒为 0；未实现实体打印 |

核心拒绝空任务和仅包含空格/LF 的任务，但尚不检查整页容量。桥接层仍须校验全部文本、对容量作检查，并把全部输出单元保存到页面缓冲；有错误则置 `text_error` 并丢弃部分结果。排空仅指 ready/valid 消费完成，必须确保真正写入缓冲，不能接恒 ready 后丢弃点阵。核心不会自行保存整页。

`motion_enable=0` 表示逻辑禁能；如果实际驱动器是低有效 EN，引脚必须由板级适配层转换，不能直连常零来当作禁能。

## 状态与提示映射

| 状态 ID | 名称 | 允许的正常推进 |
| --- | --- | --- |
| 0 | IDLE | START → WAIT_BOOK |
| 1 | WAIT_BOOK | COMPLETE → WAIT_OCR，发拍照事件 |
| 2 | WAIT_OCR | 文本成功并排空 → READY |
| 3 | READY | PRINT → PRINTING |
| 4 | PRINTING | print_done → DONE |
| 5 | DONE | START → WAIT_BOOK |
| 6 | ERROR | 仅明确复位后回 IDLE |

STOP、estop、text_error、print_error 优先于 CANCEL 和正常推进。CANCEL 在非 ERROR 状态清空并回 IDLE。ERROR 状态不会被语音“开始”或“取消”解除。

| RTL prompt_id | JSON prompt.id | 提示 |
| --- | --- | --- |
| 1 | place_book | 开机，请把书籍放置在摄像头下 |
| 2 | capturing | 正在拍照识别 |
| 3 | ready | 文字已就绪，请说打印 |
| 4 | printing | 开始打印 |
| 5 | done | 打印完成 |
| 6 | error | 出错，请检查并复位 |
| 7 | cancelled | 任务已取消 |

旧 PC 模拟错误路径目前发 `error/status` 日志，未单独播放 error 提示。RTL 对不合时序的普通关键词保持状态；模拟器另加非致命诊断，便于调试。两者不承诺所有事件日志逐字一致。

## 兼容性说明

旧 host/blind_fpga_host/protocol.py 的 v1 保持原样，seq 仅用于日志，没有 job。新模拟入口仅在测试进程内为旧 MockBoard 加上 v2 任务标识；真实 --run 不加载模拟器。

当前 RTL 接受有限 ASCII 字节并将 LF 输出为独立布局事件；中文 UTF-8 不可截断为 ASCII。未来中文路径必须解码 Unicode 并进入实际中文语言/编码模块。在此之前，桥接应明确拒绝未支持文字并丢弃整页部分结果。
