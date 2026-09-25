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

## HLS 接口与计时边界

Vitis HLS 2024.2 生成的是 `ap_ctrl_hs` 加 `ap_memory` 数组接口，不是 AXI-Lite IP。
后续 adapter 必须定义：

1. 控制寄存器、启动/完成和错误状态；
2. BRAM/AXI 中四个数组的地址、打包和端序；
3. busy 期间的访问规则；
4. CPU 写入、启动、等待、读回和清零的计时边界。

端到端加速比必须同时报告 HLS 核心周期、AXI/BRAM 事务周期、CPU API 周期和完整 KEM
周期。不能只使用 HLS 报告的 137 cycles。

## 已完成验证

- 新 HLS C 仿真：103/103；
- Vitis HLS 2024.2 综合：II=1，估算 137 cycles，150.83 MHz，DSP/LUT/FF/BRAM 为
  12/310/599/0；
- 软件 oracle：对零、边界和确定性随机 NTT 域输入检查 cached/direct BaseMul 的
  canonical mod-q 结果一致；
- 接口审计：[`scripts/mlkem512_interface/audit.py`](../scripts/mlkem512_interface/audit.py)
  生成 [`current_contract.json`](../results/accelerator_interface/current_contract.json)。

这些结果不代表 AXI、RTL、Vivado 顶层或完整 KEM 已验证。下一阶段应先导出标准库真实
中间值，再实现独立 adapter 和少量官方记录回归；通过后才扩展到 145 条和实体板。
