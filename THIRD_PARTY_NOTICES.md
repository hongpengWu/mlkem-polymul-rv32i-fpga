# 第三方组件说明

本仓库尚未指定统一项目许可证。各第三方文件中保留的版权和许可声明适用于对应组件。

| 组件 | 来源与说明 |
|---|---|
| `rtl/cpu/picorv32.v` | [PicoRV32](https://github.com/YosysHQ/picorv32)，版权属于 Claire Xenia Wolf。文件保留原始 ISC 风格许可声明；该快照的具体上游提交尚未确定。 |
| `rtl/accelerator/` | AMD Vitis HLS 2025.2 生成的 RTL 和 ROM 初始化数据。原文件中的 Xilinx/AMD 声明保持不变。 |
| VIO 与 FPGA 原语 | 由用户安装的 AMD 工具提供。工具安装文件、生成 IP 缓存及仿真库不随仓库分发。 |
| HLS 与固件算法 | 使用 Kyber/ML-KEM 的变换与常数；参考实现的具体来源及适用许可仍需维护者补充确认。 |
| `vectors/official_kat/acvp/` | NIST ACVP-Server 固定提交导出的 ML-KEM FIPS 203/FIPS203-tr1 JSON 测试向量；来源、提交和文件哈希见同目录 `SOURCES.md`。 |
| 主机端 KAT 参考实现 | `mlkem-native` 固定提交仅作为本地 `build/` 下的验证输入，不随本仓库源码分发；其许可证和提交信息由该上游仓库维护。 |

Vivado 2024.2 是本工程当前的创建与实现工具版本；该版本信息不改变原有 HLS 生成文件的来源记录。
