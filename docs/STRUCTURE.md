# 目录与维护规则

`24-2hp` 只保留当前可复现成果：CPU-only baseline、官方 KAT 软件回归和新的标准接口
BaseMul HLS 及其独立 MMIO/BRAM/PYNQ-Z2 验证路径。旧完整时域核、旧 AXI wrapper、旧
板级顶层、transfer 固件及其工程已整体删除，避免出现“源码已删但 XPR 仍引用”的失效结构。

```text
mlkem-polymul-rv32i-fpga/
├── rtl/
│   ├── cpu/                    PicoRV32
│   ├── benchmark/              CPU-only 固件 RAM 和可配置系统 wrapper
│   └── accelerator/            HLS RTL、BRAM、MMIO adapter 和 PYNQ-Z2 BIST 顶层
├── hls/
│   └── mlkem512_basemul_k2/    新 HLS 源码、TB、Tcl、短路径脚本和导出 IP
├── firmware/
│   ├── cpu_baseline/           软件多项式 baseline
│   ├── mlkem_baseline/         官方 KeyGen 入口
│   ├── mlkem512_suite/         完整 ML-KEM-512 官方套件入口
│   ├── mlkem512_profile/       阶段 profiling 入口
│   └── images/                 CPU/ML-KEM 固件镜像
├── tb/
│   ├── cpu/                    M 扩展和周期验证
│   ├── software/               多项式、KeyGen、完整 KEM testbench 与 fixture
│   └── accelerator/            MMIO、BRAM、板级 BIST TB 和向量
├── scripts/
│   ├── cpu_baseline/           CPU 构建、仿真、实现和汇总
│   ├── mlkem_baseline/         KeyGen 构建和仿真
│   ├── mlkem512_suite/         145 条记录的批处理、恢复和汇总
│   ├── mlkem512_profile/       阶段测量
│   ├── mlkem512_interface/     接口审计和软件 oracle
│   ├── mlkem512_basemul_k2/    加速器 Vivado 仿真、实现和报告
│   └── kat/                    ACVP 结构检查和主机参考回归
├── vivado/                     CPU-only/ML-KEM 软件与独立加速器 XPR
├── release/                    CPU-only 与独立加速器 bitstream
├── results/                    官方回归、CPU 实现、HLS 和加速器证据
├── vectors/official_kat/       固定版本 ACVP/FIPS 203 向量
├── third_party/                固定提交的 mlkem-native portable C
├── constraints/                PYNQ-Z2 XDC，供新硬件顶层使用
└── docs/                       构建、验证、性能和路线记录
```

## 保留边界

- `rtl/cpu/`、`rtl/benchmark/`、`firmware/`、`tb/cpu/`、`tb/software/` 是软件 baseline 和
  官方 KAT 的执行输入，不随新 HLS 改动。
- `hls/mlkem512_basemul_k2/` 是当前唯一维护的 HLS 设计。`src/`、`tb/`、`hls_config.cfg`、
  `run_hls.tcl`、两个 PowerShell 入口和 `ip/` 归档共同构成可复现 HLS 工程。
- `rtl/accelerator/`、`tb/accelerator/` 和 `scripts/mlkem512_basemul_k2/` 共同构成独立
  MMIO/BRAM 验证路径；`vivado/mlkem512_basemul_k2/basemul.xpr` 是可直接打开的
  Vivado 2024.2 工程，`release/mlkem512_basemul_k2/` 保存匹配的 bitstream。
- `vivado/cpu_baseline_*`、`vivado/mlkem_keygen_*`、`vivado/mlkem512_*` 只保存可打开的
  XPR 和固件镜像；`.runs`、`.sim`、`.cache` 等生成目录不进版本库。
- `release/cpu_baseline_*` 是已有 CPU-only 实现产物。它们不是新 HLS 的 bitstream，也不
  代表 CPU+PL 加速系统已经完成。
- `results/official_baseline/`、`results/official_reference/`、`results/cpu_baseline/` 和
  `results/accelerator_interface/` 只保存可审计证据；后者包含 HLS、RTL、板级 BIST 和
  Vivado 实现结果，旧完整加速器结果已移除。

## 生成文件规则

Vitis HLS 和 Vivado 都会生成大量缓存、日志、波形和布局布线数据库。根目录 `.gitignore`
只保留可复现入口、XPR、MEM、XCI、BIT/LTX 和报告；重新生成时不要把 `.Xil`、`.runs`、
`.sim`、`.cache`、DCP 或临时目录加入 Git。

新 HLS 使用已验证的 native MMIO/BRAM adapter。后续 PicoRV32 接入需新增 CPU 总线桥接、
软件调用、阶段 oracle 和系统顶层，并更新端到端证据；不能把旧 AXI wrapper 恢复后当作新接口。
