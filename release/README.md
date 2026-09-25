# CPU-only 烧录产物

本目录保存当前仍可复现的 CPU-only Vivado 2024.2 bitstream：

```text
cpu_baseline_rv32i/cpu_baseline_rv32i.bit
cpu_baseline_rv32im_iterative/cpu_baseline_rv32im_iterative.bit
cpu_baseline_rv32im_fast/cpu_baseline_rv32im_fast.bit
```

这些 bitstream 只用于 CPU baseline 的资源、时序和板级准备，不包含新的 HLS BaseMul，也
不代表 CPU+PQC 加速系统已经完成。新 HLS 目前只有 HLS IP，待独立 AXI/BRAM adapter 和
Vivado 顶层完成后再生成新的系统 bitstream。

重新生成方式见 [`docs/BUILD.md`](../docs/BUILD.md)。替换 bitstream 时应同时更新
`docs/BENCHMARKS.md` 中的文件哈希和对应结果目录。
