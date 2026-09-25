# 第三方组件说明

本仓库尚未指定统一项目许可证。各第三方文件中保留的版权和许可声明适用于对应组件。

| 组件 | 来源与说明 |
|---|---|
| `rtl/cpu/picorv32.v` | [PicoRV32](https://github.com/YosysHQ/picorv32)，版权属于 Claire Xenia Wolf。文件保留原始 ISC 风格许可声明；该快照的具体上游提交尚未确定。 |
| `hls/mlkem512_basemul_k2/` | 本项目基于 AMD Vitis HLS 2024.2 的 HLS 源码、配置和导出 IP；工具生成缓存不随仓库分发。 |
| VIO 与 FPGA 原语 | 由用户安装的 AMD 工具提供。工具安装文件、生成 IP 缓存及仿真库不随仓库分发。 |
| HLS 与固件算法 | 使用 Kyber/ML-KEM 的变换与常数；参考实现的具体来源及适用许可仍需维护者补充确认。 |
| `vectors/official_kat/acvp/` | NIST ACVP-Server 固定提交导出的 ML-KEM FIPS 203/FIPS203-tr1 JSON 测试向量；来源、提交和文件哈希见同目录 `SOURCES.md`。 |
| `third_party/mlkem-native/` | [mlkem-native](https://github.com/pq-code-package/mlkem-native/tree/b3ba7b32773e657dd37f6f87bce82528459ad8a4) 固定提交 `b3ba7b32773e657dd37f6f87bce82528459ad8a4` 的 portable C 库子集，用于 PicoRV32 ML-KEM-512 KeyGen、Encaps、Decaps 和密钥检查。上游提供 **Apache-2.0 OR ISC OR MIT** 三选一许可，完整条款保存在 [`LICENSE`](third_party/mlkem-native/LICENSE)，逐文件 SPDX 与版权声明均保留。 |
| 主机端 KAT 参考实现 | 同一固定提交的完整 `mlkem-native` 开发树仍在本地忽略目录 `build/kat_sources/mlkem-native/` 中，用于 435 项主机回归。该完整开发树不随仓库分发；PicoRV32 所需 portable 库子集按上一行说明分发。 |

`third_party/mlkem-native/SOURCE_MANIFEST.json` 记录上游文件路径、大小、SHA-256 和
Git blob SHA-1；导入文件保持上游 Git blob 的原始字节内容，没有修改密码算法。
原生架构后端、证明、测试、示例和上游构建脚本未包含在该子集中。项目自己的裸机
适配和构建配置位于 `firmware/mlkem_baseline/`、`firmware/mlkem512_suite/` 及对应 scripts 目录；这不改变
第三方文件的许可或来源。PicoRV32 首个 KeyGen 用例通过只说明该次 RTL 仿真的功能
结果，不继承上游形式化验证、认证或其他平台安全测试的结论。

Vivado/Vitis HLS 2024.2 是当前工程的创建、综合和实现工具版本。新 HLS 的导出 IP 只代表
K=2 BaseMul 核心，尚未代表完整 CPU+PQC 顶层或实体板认证。
