---
name: pynq-accelerator-validation
description: 为 PYNQ 加速器组织黄金参考比对、预热和重复测量，区分主机墙钟与硬件周期，解析 HLS/Vivado 资源证据并生成 JSON/Markdown 报告。适用于板上验收、性能回归和跨算法复用的测试骨架。
---

# PYNQ 加速器验证与报告

把设备操作封装成适配器，把测试向量、比较规则和重复次数放入计划文件。运行器不包含算法、板型或寄存器常量，适用于定点 DSP、图像处理、CRC、密码运算及浮点内核。

## 执行流程

1. 先读 [计划与适配器协议](references/adapter.md)，确认输入/输出编码、独立黄金来源、完成协议、计时区间、硬件计数器频率及复位方法。密码与整数结果默认精确比较；浮点容差由需求确定，不为使测试通过而放宽。
2. 在 PC 运行 `assets/vector_demo.plan.json` 与 `assets/vector_demo_adapter.py`，确认工具链和报告流程。该例为饱和向量加法，无需 PYNQ，结果必须标为 `offline-demo`。
3. 参照协议接入自己的 PYNQ 驱动，适配器实现 `create/describe/run/close`。`create` 完成 Overlay/ABI 校验与资源分配，`run` 必须实施有界轮询和数据传输，`close` 使用已确认的协议回收资源。板上计划与适配器均显式声明 `board-live`。
4. 黄金向量在计划中固定，记录来源与版本。输入必须每次重建，避免前一轮修改污染重复测试。预热结果也要比对；首个故障停止会话并保存结果，先定位再决定是否重试。
5. 执行 `scripts/validate_accelerator.py <计划> --adapter <适配器.py> --output <新结果目录>`。检查退出码以及 `report.json` 的 `passed/performance_eligible`，再阅读 Markdown 报告。
6. 若提供 HLS XML 或 Vivado utilization，必须声明 `kind/stage/scope`。报告缺失、不认识或阶段矛盾时失败；不把缺失资源当零，不把 HLS 时钟估计当实现后频率或时序收敛结论。

## 计时和证据约束

- 预热、Overlay 加载、固件下载、运行器的黄金比对与文件落盘不计入运行器墙钟；适配器内部自行做的比对仍包含在墙钟中，须在说明中披露。
- 硬件周期仅在适配器给出 `device_cycles/frequency_hz/cycle_scope` 时记录；不能用主机时间倒推设备周期。
- 保留逐次记录和各用例 median/P95/max。少量样本的 P95 仅作描述，不能宣称稳定尾延迟。
- 任一预热、实测、清理或资源解析失败时，`performance_eligible=false`；已成功样本也不能当成完整通过的性能结论。
- 跨方案比较必须具有相同工作量、输入、板卡/频率条件和计时范围。该工具不自动生成加速比，防止混合 RTL 历史记录与板上测量。
- 适配器是本地可执行 Python 代码，仅加载已审阅的文件。调用外层计时不能抢占卡住的驱动；硬件 DMA/MMIO 等待必须在适配器中实施超时或由独立进程/看门狗处置。

## 资源与验证

- [适配器契约、数据计划和命令](references/adapter.md)
- [故障定位、经验出处与迁移边界](references/troubleshooting.md)
- `assets/mlkem1024_board_adapter.py` 和 `scripts/make_mlkem_plan.py`：接入本队既有驱动的可执行实例，板上调用会下载 Overlay。
- `assets/vector_demo_adapter.py`：与本题无关的完整离线示例。

验证范围、原始代码路径和既有板上证据见 [技能包总说明](../README.md)。新生成工具尚未在其他板卡上运行时，必须保留这一边界，不将项目历史实测替代为本工具实测。
