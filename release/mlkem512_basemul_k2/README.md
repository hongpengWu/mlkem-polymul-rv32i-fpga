# 独立 BaseMul 验证 bitstream

`mlkem512_basemul_k2_validation.bit` 由 Vivado 2024.2 面向 PYNQ-Z2
`xc7z020clg400-1` 生成。输入为板载 125 MHz 时钟，MMCM 输出 100 MHz。

顶层使用确定性非零向量执行 MMIO 装载、HLS 运算和结果读回比较。LED0 为通过，LED1
为失败，LED2 为运行中，LED3 为时钟未锁定；BTN0 复位并重新运行。固定向量仅用于自检，
HLS 运算核没有按该向量特化。

工程为 `vivado/mlkem512_basemul_k2/basemul.xpr`，重建入口为
`scripts/mlkem512_basemul_k2/implement.tcl`。哈希见上一级 `SHA256SUMS`，实现报告见
`results/accelerator_interface/vivado_impl/`。

当前仅完成 RTL 仿真及实现，尚未实板烧录；本产物不包含 PicoRV32 或完整 ML-KEM。
