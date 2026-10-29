# 契约格式与运行方式

所有命令从 `skill/pynq-overlay-contract/` 执行。PC 只需 Python 3.6+ 标准库；板上还需与板卡镜像匹配的 PYNQ。Python 版本建议沿用已验证镜像，迁移前记录 `python --version`、PYNQ 版本、板型和 FPGA part。该工具仅面向完整、同名 bit/hwh Overlay，不覆盖 partial bitstream、XSA、DTBO 或可重配置分区依赖的自动部署。

## 先用项目现成制品做离线检查

```console
python scripts/overlay_contract.py assets/mlkem1024.contract.json --bundle-dir ../../release/mlkem1024_pynq --output ../../results/skill_checks/overlay_check.json
```

成功输出 `passed=true, hardware_verified=false`。这只说明文件哈希与 HWH 地址契约一致；不会导入 PYNQ，也不会访问板卡。项目发布包不同批次不能混用；若换发布包，重新审查与封装，不能为消除错误而盲目更新哈希。

## 换题目与换板卡

1. 复制 `assets/vector.template.json`，按真实设计修改 IP 层级名、地址、跨度、寄存器与身份字段。模板中的 `0x56454331` 仅是演示值，硬件未实现该值时必须修改契约或在 RTL 增加稳定身份寄存器。
2. 在目标板的工程中生成同名 bit/hwh。先确认 FPGA part、时钟、复位、外部引脚与板卡兼容；HWH 地址校验不能证明这些条件。
3. 对确认后的制品封装哈希，再执行离线检查。哈希用于绑定版本，不是来源认证或数字签名。

```console
python scripts/seal_contract.py assets/vector.template.json --bundle-dir /home/xilinx/vector_release --output /home/xilinx/vector_release/contract.json
python scripts/overlay_contract.py /home/xilinx/vector_release/contract.json
python scripts/overlay_contract.py /home/xilinx/vector_release/contract.json --download --output /home/xilinx/vector_release/load_check.json
```

最后一条在板上下载 PL，可能使现有会话失效。只在计划运行此 Overlay 时执行。`--download` 之后失败，PL 可能已经配置为新 Overlay；工具不会自动回滚。

## JSON 字段

| 字段 | 约束与含义 |
|---|---|
| `schema` | 当前为整数 `1` |
| `bitstream/hwh` | 平面文件名、同名 `.bit/.hwh`，不允许目录、盘符或越出制品目录的符号链接 |
| `files` | `{文件名: 小写64位SHA-256}`；bit/hwh 必须存在，可附加其他需绑定的文件 |
| `ip.name` | PYNQ `ip_dict` 中的层级名，如 `my_accel_0` 或 `subsystem/my_accel_0` |
| `ip.base_address/address_range` | 整数或 `0x` 字符串，32 位对齐，与 HWH 的整个 MEMRANGE 精确一致 |
| `ip.allow_mmio_fallback` | 默认 false；module-reference 经 HWH 和 RTL 确认后才启用 |
| `registers` | 命名描述，每项至少有 `offset/access`，均为32位寄存器 |
| `registers.*.snapshot` | 默认 false，只对无副作用的 `ro/rw` 显式设 true |
| `identity` | 非空数组，`register/equals`，可选 `mask`；必须引用稳定 `ro` 寄存器 |

`wo` 只能写；`w1c` 只提供直接写，若同一地址还有状态读取需求，应按其真实语义扩展封装，不能随意把它声明为普通 `rw`；`rc` 表示读取有清除副作用，只支持显式读取。HLS 控制寄存器往往混合 start、done、idle 等语义，应整体标为 `rc` 避免被快照消耗；启动写操作通过审阅后的原生 `ip.write()` 完成，或为该协议新增有针对性的访问器，不用通用读改写。

`RegisterIO` 只提供寄存器封装；RAM 窗口、64 位指针、计数器高低位一致读取、突发数据与 DMA 需在设备适配层按协议实现。它不自动猜测从 HWH 缺失的 ID/ABI。

## Python 访问范式

把 `scripts/` 加入 Python 模块搜索路径，或把辅助脚本与 Notebook 放在一起。

```python
from overlay_contract import connect

# 默认已加载校验；若本次任务需要配置 PL，明确设置 download=True。
overlay, regs, evidence = connect("contract.json", download=False)
print(evidence)
print(regs.snapshot())
regs.write("length", 256)   # 仅当契约中 length 是实际可写寄存器
```

对有独立控制与状态寄存器的设计，可以明确启动和完成值后调用：

```python
regs.write("command", 1)
regs.poll("status", mask=0x2, expected=0x2, timeout=2.0,
          error={"register": "error", "mask": 0xffffffff})
```

这个片段是接口模式示意，`command/status/error` 必须存在于自己的契约，不适用于原样运行 `vector.template.json`。错误检查先于完成检查；完成与错误位在同一寄存器时复用同一次读取。

## register_map 使用范式

当 PYNQ 已根据 HWH 暴露寄存器及字段时，`register_map` 能避免手写偏移；它的名字来自当前 HWH，不能假定所有 IP 都叫 `CTRL/AP_START`。

```python
# 先看元数据，不读取有副作用的硬件寄存器。
info = overlay.ip_dict["my_accel_0"]
print(info.get("registers", {}))
ip = overlay.my_accel_0

# 以下仅适用于 HWH 中有 n_elements 的内核。
ip.register_map.n_elements = 256
# 启动位明确后直接写完整控制字；0x00 和 0x01 必须来自当前接口头文件。
ip.write(0x00, 0x01)
```

对全部寄存器均无读副作用的 IP，可用 `print(ip.register_map)` 查看当前值。含 `ap_done` 读清、FIFO 出队或中断确认的 IP，不要把整个 `register_map` 打印到日志。PYNQ 解析不到寄存器时，用 HWH 地址范围 + 已审阅的 JSON `RegisterIO`，不要伪造字段名来绕过。

## 官方 API 参考

- PYNQ Overlay 与元数据：https://pynq.readthedocs.io/en/latest/pynq_libraries/overlay.html
- PYNQ MMIO：https://pynq.readthedocs.io/en/latest/pynq_libraries/mmio.html
- PYNQ Overlay API：https://pynq.readthedocs.io/en/latest/pynq_package/pynq.overlay.html

以目标镜像对应的版本文档和实际 `ip_dict` 为准。核心工具不依赖在线文档即可执行离线检查。
