# RV32IM-fast + BaseMul 接口验证

2026-09-25：Vivado 2024.2 RTL 仿真通过。真实 PicoRV32 执行 C 驱动，经过 AXI 到 native
MMIO 桥、BRAM 和 HLS 核，再由 CPU 读回全部结果并输出给 TB。TB 独立保留预期系数，
固件仅含输入，不含预期输出。原 CPU-only baseline、固件和第三方库没有修改。

| 输入 | 驱动调用周期 | 核心周期 | 输入写/结果读 | 系数核对 |
|---|---:|---:|---:|---:|
| 零值 | 48,632 | 136 | 640 / 128 | 256 / 256 |
| signed lazy 边界 | 48,632 | 136 | 640 / 128 | 256 / 256 |
| 确定性随机 | 48,632 | 136 | 640 / 128 | 256 / 256 |

调用周期为两次 `rdcycle` 之差，包含 C 驱动的状态检查、打包写入、启动、轮询、读回和
结果写入 CPU 数组，排除向 TB 输出检查数据。按 100 MHz 换算为 486.32 μs；这是 RTL
仿真换算，CPU 集成系统尚未布局布线或上板。核心周期已包含在调用周期内，不能重复相加。
固件有效镜像 8,692 B，统一使用 64 KiB RAM、16 KiB 栈预留。

原始证据：[smoke_simulate.log](../results/accelerator_cpu/smoke_simulate.log)、
[编译与输入哈希](../results/accelerator_cpu/smoke_build.json)。重跑命令：

```powershell
python scripts/mlkem512_accel/build_smoke.py
vivado -mode batch -source scripts/mlkem512_accel/run_smoke.tcl
```

新增系统为 `rtl/accelerator/mlkem512_accel_system.sv`；驱动在
`firmware/mlkem512_accel/`；仿真临时工程在 `build/cpu_accel_smoke/`。

当前仅验证局部接口，不是完整 ML-KEM，也不是官方 KAT。下一步将标准库的 K=2 cached
BaseMul 调用接到此驱动，先跑官方 KeyGen/Encaps/Decaps 代表例，再扩展 145 条回归。
当前驱动未擦除加速器 BRAM，正式安全边界和公平 API 对照须纳入敏感数据清零成本；
本表不能直接与完整 KEM 软件周期计算加速比。

## 标准库接入准备

已新增 `native_basemul.h/.c`：通过独立编译参数启用标准库现有的 K=2 native hook，
直接调用 MMIO 驱动。第三方源码和软件 baseline 均未改动，硬件错误直接报告失败，
不会静默退回软件计算。结构大小以编译期断言核对。

`python scripts/mlkem512_accel/build_kat.py` 已编译、链接完整官方套件驱动，生成
`firmware/images/mlkem512_accel/kat.mem`（有效镜像 26,944 B）。已检查第三方源码哈希、
native hook 的真实调用重定位及最终 ELF 符号。证据为
[kat_build.json](../results/accelerator_cpu/kat_build.json)。

**仅完成编译链接，官方 KAT 尚未运行。** 下一步让官方套件 TB 使用新 CPU 系统和镜像，
补充 MMIO 地址白名单及硬件调用次数检查，先验证代表例。
