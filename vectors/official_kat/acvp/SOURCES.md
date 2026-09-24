# ACVP ML-KEM 官方向量

本目录保存用于主机端 FIPS 203/ACVP 兼容性验证的官方 JSON 向量。`prompt.json`
是实现需要处理的输入，`expectedResults.json` 是对应的参考结果。它们用于验证
完整 ML-KEM 的 keyGen、encapsulation、decapsulation 和 key-check 接口；它们不是
可以直接烧录到 PicoRV32 的固件镜像。

向量来自 [NIST ACVP-Server](https://github.com/usnistgov/ACVP-Server)，固定到
提交 [`975de31eb83d87039ec88934fdc47d8c312b892d`](https://github.com/usnistgov/ACVP-Server/tree/975de31eb83d87039ec88934fdc47d8c312b892d)。
采集日期：2026-09-23。表中的字节数和 SHA-256 针对仓库中实际保存的文件，便于
下载后复核完整性。

主机参考实现固定为 `pq-code-package/mlkem-native` 提交
[`b3ba7b32773e657dd37f6f87bce82528459ad8a4`](https://github.com/pq-code-package/mlkem-native/tree/b3ba7b32773e657dd37f6f87bce82528459ad8a4)。
该源码只保存在本地忽略目录 `build/kat_sources/mlkem-native/`，不会成为 FPGA 工程的源文件。

## 文件清单

| 本地文件 | ACVP-Server 原始路径 | 字节数 | SHA-256 |
|---|---|---:|---|
| `fips203/ML-KEM-keyGen/prompt.json` | `gen-val/json-files/ML-KEM-keyGen-FIPS203/prompt.json` | 16,066 | `3f9ce34f6c836c77958bad2729e837c3b213f44ac36c3065976e7acca6389523` |
| `fips203/ML-KEM-keyGen/expectedResults.json` | `gen-val/json-files/ML-KEM-keyGen-FIPS203/expectedResults.json` | 544,032 | `a253d0ad91c95ebea5b409673defef0aa49d65d4ed72286399e2e798ddf073a4` |
| `fips203/ML-KEM-encapDecap/prompt.json` | `gen-val/json-files/ML-KEM-encapDecap-FIPS203/prompt.json` | 624,189 | `998e22dfb12efb14ce9fdff911ca634b13612819a1806f25da69adba7e16db91` |
| `fips203/ML-KEM-encapDecap/expectedResults.json` | `gen-val/json-files/ML-KEM-encapDecap-FIPS203/expectedResults.json` | 190,940 | `9089ec6ff2424da9f2782b89b2f831a329a3e28d6e5e24b802b78ff36ac61cdf` |
| `fips203-tr1/ML-KEM-encapDecap/prompt.json` | `gen-val/json-files/ML-KEM-encapDecap-FIPS203-tr1/prompt.json` | 700,234 | `a25430d886a8212a21ed0d4015eb91aa30d555588465d47da04ffb45236d27fd` |
| `fips203-tr1/ML-KEM-encapDecap/expectedResults.json` | `gen-val/json-files/ML-KEM-encapDecap-FIPS203-tr1/expectedResults.json` | 194,889 | `aa846067d30bebcfe4e839b076b1df5cdeb14332912b3e02dfe8d00c614098b4` |

对应的可点击原始地址可由上表的提交固定地址和原始路径拼接得到，例如：

`https://raw.githubusercontent.com/usnistgov/ACVP-Server/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-KEM-keyGen-FIPS203/prompt.json`

`FIPS203-tr1` 是 ACVP 的过渡版本，单独保存用于兼容性回归，不替代正式
`FIPS203` 向量。正式文件的顶层 `revision` 为 `FIPS203`，过渡文件的顶层
`revision` 为 `FIPS203-tr1`。

## 结构检查

从仓库根目录执行：

```text
python scripts/kat/validate_acvp_json.py
```

检查脚本会解析每一对 JSON，核对 revision、模式、测试组、`tgId`、`tcId` 以及
prompt/expected 的对应关系，并检查十六进制字段格式。该检查不运行 ML-KEM，也
不代表当前 FPGA 固件已经通过 KAT。
