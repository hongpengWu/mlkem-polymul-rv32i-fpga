# ML-KEM-1024 CPU + Keccak official KAT

Status: **PARTIAL**, 3/145 unique official cases.

PicoRV32 fast CPU plus real generated Keccak RTL, official K4 cases; not board measurement or certification.

Raw rdcycle API intervals including CPU/MMIO work and zeroization; empty bracket retained; seed decapsulation includes key expansion. Busy cycles measure HLS activity; remaining API cycles also include transfers and CPU work, not pure transfer overhead.

| Operation | Return | Cases | CPU cycles | Accelerated cycles | Ratio of sums |
|---|---:|---:|---:|---:|---:|
| decapsulation | 0 | 1 | 17088709 | 4658623 | 3.668x |
| encapsulation | 0 | 1 | 13908293 | 3841529 | 3.621x |
| keyGen | 0 | 1 | 13046698 | 3120949 | 4.180x |

Hardware commands: 85 starts, including 4 continuation squeezes.

Only successful, hash-verified, disjoint attempts are included. Every result checks official identities, byte counts, returns, CPU configuration, measured boundaries and exact expected hardware command/transfer counts.

This pilot does not establish full 145-case RTL coverage. Selected original indices: [0, 1, 115].
