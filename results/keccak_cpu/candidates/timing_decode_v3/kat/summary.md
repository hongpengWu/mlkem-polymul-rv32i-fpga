# ML-KEM-1024 CPU + Keccak official KAT

Status: **PASS**, 145/145 unique official cases.

PicoRV32 fast CPU plus real generated Keccak RTL, official K4 cases; not board measurement or certification.

Raw rdcycle API intervals including CPU/MMIO work and zeroization; empty bracket retained; seed decapsulation includes key expansion. Busy cycles measure HLS activity; remaining API cycles also include transfers and CPU work, not pure transfer overhead.

| Operation | Return | Cases | CPU cycles | Accelerated cycles | Ratio of sums |
|---|---:|---:|---:|---:|---:|
| decapsulation | 0 | 20 | 331730912 | 92092840 | 3.602x |
| decapsulationKeyCheck | -5 | 10 | 18793140 | 752230 | 24.983x |
| decapsulationKeyCheck | 0 | 10 | 18793030 | 752120 | 24.987x |
| decapsulationSeed | 0 | 10 | 295059990 | 77103920 | 3.827x |
| encapsulation | 0 | 50 | 700468926 | 192648902 | 3.636x |
| encapsulationKeyCheck | -4 | 10 | 2574170 | 2574170 | 1.000x |
| encapsulationKeyCheck | 0 | 10 | 2574060 | 2574060 | 1.000x |
| keyGen | 0 | 25 | 329300132 | 78355267 | 4.203x |

API cycle sums: CPU 1,699,294,360; accelerated 446,853,509; ratio **3.802800x**. This ratio applies to this official case mix.

Hardware commands: 3,188 starts, including 68 continuation squeezes. HLS busy: 1,980,263 cycles. Buffer transfers: 257,851 writes / 435,632 reads, in 32-bit words including context.

Completed batches: 19. Run-duration sum: 10,961.816 s. Sum of individual simulator run durations, including compilation/elaboration; not uninterrupted wall elapsed time.

Maximum observed stack: 24,384 bytes, from verified final PASS records; not a worst-case bound.

Only successful, hash-verified, disjoint attempts are included. Every result checks official identities, byte counts, returns, CPU configuration, measured boundaries and exact expected hardware command/transfer counts.

Strict recollection requires every manifest run_dir/snapshot directory, retained outside Git. Log and manifest hashes alone cannot reconstruct frozen firmware, testbench or generated HLS inputs.
