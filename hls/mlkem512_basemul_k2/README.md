# ML-KEM-512 K=2 cached BaseMul HLS

这是从标准库接口重新设计的第一版 HLS 核，独立于 `hls/src/` 中的旧完整时域多项式乘法核。

顶层 `mlkem512_basemul_acc_k2` 对应 portable ML-KEM 的
`polyvec_basemul_acc_montgomery_cached()`：输入是两个 NTT 域多项式向量和已经计算好的
`mulcache`，输出是 K=2 向量点积的 NTT 域结果。它不执行 NTT、逆 NTT、1441 缩放或压缩。

```text
a[2][256]        NTT 域矩阵行，标准库约束为 [0, 4095]
b[2][256]        NTT 域向量，signed lazy int16 表示
b_cache[2][128]  b 的 mulcache
result[256]      每个系数一次 Montgomery reduction 后的 NTT 域结果
```

`tb/` 中的 cache 生成和数学 oracle 是独立实现，覆盖零输入、规范输入、signed lazy 边界和
100 组确定性随机输入。它检查 signed 结果和模 `q=3329` 的 canonical 结果。

## 本机 C 仿真

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_csim.ps1
```

## Vivado/Vitis HLS 2024.2

在安装了 Vivado 2024.2 的 Tcl 环境中，从本目录执行：

```text
vitis_hls -f run_hls.tcl
```

脚本会创建本地 `mlkem512_basemul_k2_vivado/` 工程、运行 C 仿真和综合，并导出 IP。生成目录
是构建产物，默认不纳入 Git；源文件、testbench、配置和 Tcl 脚本才是可复现输入。

Windows 路径较长时，把本目录的 `src/`、`tb/`、`run_hls.tcl` 和配置复制到短路径（例如
`E:\hlsk2`）后从该目录运行。已用 Vitis HLS 2024.2 在短路径验证通过：C 仿真 103/103，
II=1，估算延迟 137 cycles，估算 Fmax 150.83 MHz，DSP/LUT/FF/BRAM 估算为
12/310/599/0。完整 HLS 报告和导出的 IP 归档在
[`results/accelerator_interface/hls_synthesis/`](../../results/accelerator_interface/hls_synthesis/)
和 [`ip/`](ip/)；这些是估算/综合阶段数据，不是最终 Vivado 布局布线资源。

也可以直接使用 `run_hls_short.ps1`，它会复制到短路径、调用 Vitis HLS，并把报告和 IP
归档回仓库：

```powershell
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_hls_short.ps1
```
