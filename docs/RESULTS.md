# Results and boundaries

Historical configuration: PYNQ-Z2, 100 MHz, BRAM wrapper, mode-3 firmware, read-only VIO.

| Measurement | Historical result | Scope |
|---|---:|---|
| Core | 4789 cycles / 47.89 us | Wrapper internal busy counter |
| Input write | 5873 cycles | CPU transfer loop, includes CPU overhead |
| Start | 19 cycles | CPU launch write |
| Poll | 4827 cycles | Overlaps hardware computation |
| Output read | 3233 cycles | CPU readback loop |
| Call | 13952 cycles / 139.52 us | Existing local inputs to local output; excludes generation/check |
| Routed LUT / FF | 3908 / 5053 | Full system including VIO |
| DSP / BRAM36 equivalent | 1 / 6.5 | Full system including VIO |
| WNS / WHS | +1.820 / +0.028 ns | Original board constraints at 100 MHz |

Do not add Core to Poll or Call. Transfer time is not exclusively AXI stall time. Fractional BRAM36 is a capacity/resource equivalence, not a physical half block. Positive slack proves closure under the given constraints, not measured maximum frequency or power.

The archived physical-board snapshot reports done=1, trap=0, status=0x600d600d and the above cycle counts. Only one numeric board snapshot is included. Three reset runs with an independent 256-coefficient oracle are RTL simulation evidence, not three independently archived board measurements.

Historical BRAM comparison (system OOC, not the VIO board scope): LUT 14673 to 2936, FF 14118 to 2759, RAMB18 equivalent 10 to 13; call 13824 to 13952. Core stays 4789. This is an area trade-off with one extra read-response cycle per 32-bit output word.

Software audit: 2050106 cycles inside the PolyMul function, 2050123 in its surrounding rdcycle window. This is a specific RV32I -O2 software reference measured in RTL simulation, not an optimized universal software baseline or a new board result.

`evidence/historical/` holds imported reports. Only local directory roots and hostnames are redacted; measured values are unchanged. SOURCE_MANIFEST records the pre-redaction imports, FINAL_MANIFEST records distributable hashes. New migration tests are documented separately in MIGRATION_VALIDATION.md.
