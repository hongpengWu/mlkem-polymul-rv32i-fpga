# ML-KEM-512 K=2 cached BaseMul HLS

这是当前维护的 HLS 设计，直接对应 portable ML-KEM 的
`polyvec_basemul_acc_montgomery_cached()` 接口。它独立于已经移除的旧完整时域乘法核。

顶层 `mlkem512_basemul_acc_k2` 接收两个 NTT 域多项式向量和显式 `mulcache`，输出 K=2
向量点积结果。它不执行 NTT、逆 NTT、1441 缩放、压缩或解压。

```text
a[2][256]        NTT 域矩阵行
b[2][256]        NTT 域向量
b_cache[2][128]  b 的 mulcache
result[256]      K=2 cached BaseMul 输出
```

## C 仿真

```powershell
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_csim.ps1
```

testbench 覆盖零输入、边界和确定性随机输入，共 103 个检查。

## Vitis HLS 2024.2

从短路径运行：

```powershell
powershell -ExecutionPolicy Bypass -File hls/mlkem512_basemul_k2/run_hls_short.ps1
```

脚本会复制源文件、TB、Tcl 和配置到短路径，调用 `vitis_hls.bat`，再把报告和导出 IP
归档回仓库。也可以在本目录执行 `vitis_hls -f run_hls.tcl`。本地工程、缓存和临时日志
不提交；源码、配置和 `ip/*.zip` 是可复现输入。

已验证结果：C 仿真 103/103，II=1，估算 137 cycles、150.83 MHz，DSP/LUT/FF/BRAM
估算为 12/310/599/0。完整证据在 [`results/accelerator_interface/hls_synthesis/`](../../results/accelerator_interface/hls_synthesis/)。

该 IP 使用 `ap_ctrl_hs + ap_memory`，还没有 AXI wrapper 或 Vivado 顶层。接入时必须新建
adapter，并将核心、事务、CPU API 和完整 KEM 周期分别记录。
