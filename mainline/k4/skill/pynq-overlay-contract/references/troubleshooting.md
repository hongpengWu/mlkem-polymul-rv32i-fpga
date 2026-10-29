# 故障定位与复用边界

| 症状/触发条件 | 检查顺序 | 退出与恢复 |
|---|---|---|
| SHA-256 不匹配 | 比对制品批次、文件名、拷贝完整性、manifest 版本；保留旧哈希 | 不下载；从可信构建产物重新取文件，不直接接受坏文件 |
| HWH 地址与契约不同 | 查看 `BASEVALUE/HIGHVALUE`、Block Design 地址段；确认 offset 是字节而非字 | 更新对应硬件的契约，或重建正确制品 |
| `ip_dict` 没有目标 IP | 先检查层级名，再检查是否 module-reference，以及 HWH 中精确地址范围 | 仅确认自定义模块映射后启用显式 MMIO 回退 |
| `register_map` 不可用或字段不存在 | 查看当前 HWH 的 registers 描述、PYNQ driver 绑定与版本；不要套别人的字段名 | 改用已审阅的 MMIO 契约，或修正 IP 打包元数据 |
| ID/ABI 不符或读出全0/全1 | 检查加载的 bit、PL 时钟/复位、AXI 基地址、寄存器偏移与接口版本 | 不启动计算；保留地址和读值 |
| 读 MMIO 卡死 | 优先查 PL 时钟、复位和 AXI 从端响应，再查互连地址；软件循环超时无法拯救总线阻塞 | 用平台看门狗或独立进程，必要时按板卡流程恢复；无自动重试 |
| 只在打印状态后超时 | 检查 done 是否 read-clear；日志或快照是否提前消耗完成位 | 只读一次并保存值，快照排除该寄存器 |
| 连续运行结果不稳定 | 检查上一次结束状态、复位协议、旧固件/计数器与多 Notebook 争用 | 单会话顺序访问；按实际协议复位，不猜复位位 |
| 换板后无法配置或运行 | 确认 part、PS 配置、引脚、电压、地址、时钟、镜像和 PYNQ 版本 | 重建该板制品；工具不会转换 bitstream |

## 经验来源

- `mainline/k4/pynq/mlkem1024.py::verify_bundle` 在导入 PYNQ 前绑定 bit/hwh 哈希并核对 MEMRANGE，启发了“离线先行”的制品检查。
- 同文件 `MLKEM1024.load` 明确记录 module-reference 不一定生成 `ip_dict`；该观察形成有条件的 MMIO 回退。
- `_verify_identity/reset/run_case` 与 `mainline/k4/rtl/mlkem1024_keccak_axi.sv` 提供 ID、ABI、时钟、复位和轮询契约的来源。硬编码常量已移到示例 JSON。
- `results/k4/paired_firmware/board_20261023/summary.md` 记录本队既有复位、坏 magic 和短超时恢复检查。该文件是历史实测证据，新 Skill 的离线故障注入与这些历史实测不能相互替代。
- W1C/read-clear 的通用规则属于接口语义扩展和本次离线防护验证；没有将其写成本队曾在板上发生的事故。

## 适用场景与失效条件

适用于有 PS/Linux/PYNQ 控制面和可审阅 AXI 寄存器映射的完整 Overlay，例如 FFT 控制器、图像预处理核、传感器采集控制与密码 IP。跨 Zynq/Zynq UltraScale+ 等平台复用时仍须准备目标平台支持的 PYNQ 镜像和 bit/hwh。

不适用于没有 PYNQ 的裸机板卡、仅 PCIe/XRT 管理的平台、未实现身份寄存器且无法建立可靠版本识别的设计、自动 partial reconfiguration、大小端或寄存器宽度与当前32位封装不符的接口。实际 AXI 事务可能阻塞时，需平台级恢复方案。DMA streaming 的 TLAST、TKEEP、通道状态和缓存一致性属于数据面协议，本 Skill 不为其提供未经项目验证的封装。
