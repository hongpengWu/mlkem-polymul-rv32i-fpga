# ML-KEM-512 加速器接口契约

更新时间：2026-09-25。本文件描述当前维护的新 HLS 边界。旧完整时域 HLS/RTL/AXI
链已经删除，因此不会再把旧地址映射误用于新核。

## 标准库调用边界

ML-KEM-512 使用 `K=2`、`N=256`、`q=3329`。`mlk_polyvec_basemul_acc_montgomery_cached()`
接收已经在 NTT 域的矩阵行和向量，同时接收向量第二操作数的 `mulcache`；每个输出系数
的 K=2 累加在 32 位中完成，最后做一次 Montgomery reduction。结果仍在 NTT 域，后续由
调用方决定是否做 `polyvec_tomont()` 或 inverse NTT。

标准库约定：

| 项目 | 约定 |
|---|---|
| 模数 | `q=3329` |
| Montgomery | `R=2^16`，`QINV=62209` |
| NTT 输入 | signed `int16_t`，允许懒约减范围 |
| 矩阵系数 | `K=2` 行，每行 256 个系数 |
| 向量系数 | `K=2` 个多项式，每个 256 个系数 |
| mulcache | 每个多项式 128 个系数 |
| 输出 | 256 个 signed `int16_t` NTT 域系数 |

## 新 HLS 顶层

源码：[`mlkem512_basemul_acc_k2.cpp`](../hls/mlkem512_basemul_k2/src/mlkem512_basemul_acc_k2.cpp)

```c
void mlkem512_basemul_acc_k2(
    const int16_t a[2][256],
    const int16_t b[2][256],
    const int16_t b_cache[2][128],
    int16_t result[256]);
```

| 端口 | 布局 | 语义 |
|---|---|---|
| `a` | `[2][256]` | NTT 域矩阵行 |
| `b` | `[2][256]` | NTT 域向量 |
| `b_cache` | `[2][128]` | `b` 的 mulcache |
| `result` | `[256]` | K=2 向量点积结果，仍在 NTT 域 |

核内 K=2 完全展开，按一对系数进行 `II=1` 流水。它不执行 NTT、inverse NTT、1441
缩放、压缩、解压或随机采样，也不生成 `b_cache`。保留显式 cache 输入是为了保持与
标准库调用边界一致，并支持后续比较“软件预计算 cache”和“硬件融合 cache”两种方案。

## MMIO adapter 与计时边界

Vitis HLS 2024.2 生成的是 `ap_ctrl_hs` 加 `ap_memory` 数组接口。当前已由
`rtl/accelerator/mlkem512_basemul_k2_mmio_adapter.sv` 包装成 native request/response
MMIO 总线；它不是 AXI-Lite，已通过 `mlkem512_accel_system.sv` 接入 PicoRV32。基址为
`0x50001000`，32 位访问按
little-endian 打包两个 signed `int16_t`：

| 偏移 | 范围/寄存器 | 说明 |
|---|---|---|
| `0x000–0x1ff` | A0 | 256 个系数 |
| `0x200–0x3ff` | A1 | 256 个系数 |
| `0x400–0x5ff` | B0 | 256 个系数 |
| `0x600–0x7ff` | B1 | 256 个系数 |
| `0x800–0x8ff` | cache0 | 128 个系数 |
| `0x900–0x9ff` | cache1 | 128 个系数 |
| `0xa00–0xbff` | result | 256 个只读结果系数 |
| `0x1000` | CONTROL | bit0 start，bit1 clear-done，bit2 clear-error |
| `0x1004` | STATUS | bit0 busy，bit1 done，bit2 error，bit3/4/5 为 HLS done/idle/ready |
| `0x1008` | CORE_CYCLES | 启动请求被接受至 adapter 采样到 HLS done 的边沿差，每次 start 归零 |
| `0x100c` | LOAD_WRITES | 复位以来有效且非零字节使能的输入写事务累计数 |
| `0x1010` | RESULT_READS | 复位以来有效结果读请求累计数 |
| `0x1014` | TRANSFER_CYCLES | 首次输入写到 result 最末字 `0xbfc` 读请求被接受，含首尾周期 |

同步 BRAM 具有两个 16 位端口；空闲时由主机访问，运行时由 HLS 访问。busy 期间输入和
结果窗口访问会被拒绝，结果仅在 done 后可读；8 KiB 窗口内非对齐或未映射访问置 error。
窗口外地址不响应，交由系统地址译码处理。每个 `valid && ready` 上升沿接受一条请求，
读请求下一周期给出 `rvalid`，没有响应反压；未来 CPU 桥接需等待读响应，不能把接受请求
当成读完成。复位清除控制状态，不清空 BRAM；首次任务前须装载全部输入，后续可复用。
当前没有输入完整性跟踪或自动清零，CPU 集成必须另行明确敏感数据的清零策略。

CONTROL 为低字节写 1 生效，done/error 为粘滞状态；新输入写或成功 start 会清除 done。
TRANSFER_CYCLES 的终点是最末地址读请求，不包含其响应与调用方检查，且不检查是否已读遍
其他结果地址。HLS 的 137 cycles 是工具估算口径，不能与 adapter 的 136 cycles 直接相减
得出优化收益。

端到端加速比必须同时报告 HLS 核心周期、MMIO/BRAM 事务周期、CPU API 周期和完整 KEM
周期。不能只使用 HLS 报告的 137 cycles。

## 已完成验证

- 新 HLS C 仿真：103/103；
- Vitis HLS 2024.2 综合：II=1，估算 137 cycles，150.83 MHz，DSP/LUT/FF/BRAM 为
  12/310/599/0；
- MMIO/BRAM RTL 仿真：3 组、768 个系数逐项通过；每组核心 136 cycles、输入 640 次写、
  128 次结果读、总传输 1800 cycles；字节使能、busy 保护、非法访问、重复启动和复位
  中止检查通过；
- PYNQ-Z2 BIST RTL 仿真：两次完整运行、256 个结果字检查和一次结果故障注入通过；
- Vivado 2024.2 实现：WNS/WHS 为 0.732/0.129 ns，BRAM 原语 8、DSP 原语 12，bitstream
  为 [`mlkem512_basemul_k2_validation.bit`](../release/mlkem512_basemul_k2/mlkem512_basemul_k2_validation.bit)。
- 软件 oracle：对零、边界和确定性随机 NTT 域输入检查 cached/direct BaseMul 的
  canonical mod-q 结果一致；
- 接口审计：[`scripts/mlkem512_interface/audit.py`](../scripts/mlkem512_interface/audit.py)
  生成 [`current_contract.json`](../results/accelerator_interface/current_contract.json)。

这些结果验证了 HLS→BRAM→MMIO→PicoRV32 的 ML-KEM-512 K=2 路径；官方 145 条
CPU+PQC RTL 回归已通过，但当前端到端为 0.9930×，不代表已取得系统级性能收益。
它也不代表实体板烧录或 ML-KEM-768/1024 硬件支持；后续需先优化接口批量化，再做参数集
扩展和实体板验证。
