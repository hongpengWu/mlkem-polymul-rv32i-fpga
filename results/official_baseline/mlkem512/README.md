# ML-KEM-512 CPU baseline

2026-09-24：RV32I、RV32IM 迭代、RV32IM 快速各完成 145 / 145 条固定版本公开 ACVP 记录。

- [统计表](summary.md)、[逐条结果](cases.csv)、[统计与证据哈希](summary.json)。
- [构建清单](build_manifest.json)：相同源码/编译器/优化级别，仅 ISA 不同；IM 两组共用镜像。
- [关机前保存的 94 条记录](checkpoint/README.md) 与 [44 个续跑批次](batches/) 合并，每组原始编号恰好一次。
- [负向检查](negative_check/README.md)：预期字节翻转后准确拒绝。

复验：`python scripts/mlkem512_suite/collect_resumed.py --check`。
续跑入口会跳过已验证的全部成功批次。`project.xpr` 是批次来源归档；常规主套件工程位于 `vivado/mlkem512_*`。

这是纯 CPU RTL 回归，尚未接入 PQC 加速器，尚无本配置的综合/布线、实板数据或认证结论。完整测量边界见 [协议](../../../docs/MLKEM512_BENCHMARK_PROTOCOL.md)。
