# Third-party notices and publication status

No project-wide license has been selected. The owner confirmed permission for public hosting on 2026-09-21. That confirmation is not an independent legal audit and does not grant a blanket open-source license. Existing third-party licenses and notices continue to apply to their respective files.

1. `rtl/cpu/picorv32.v` is PicoRV32, copyright Claire Xenia Wolf. Its permissive ISC-style notice is retained verbatim in the file. Upstream: https://github.com/YosysHQ/picorv32 . The exact upstream commit of this local snapshot has not yet been established; the import hash is recorded in SOURCE_MANIFEST.csv. Do not remove the notice or claim authorship of the CPU.
2. `rtl/accelerator/` contains AMD Vitis HLS 2025.2 generated RTL and ROM initialization data. Original Xilinx/AMD notices remain intact. Confirm applicable generated-output redistribution terms before publishing; this document does not grant rights to AMD tools or library/IP source.
3. VIO and FPGA primitives come from the installed AMD tools. No vendor installation, VIO output tree or simulation library is redistributed here.
4. HLS/software arithmetic uses established Kyber/ML-KEM transforms and constants. Audit code provenance and any reference-code license obligations before selecting a project license. Algorithm familiarity alone does not establish code authorship.
5. Confirm internship/institution/supervisor IP permission before public publication. Do not include CityU logos, professor correspondence, private reports or third-party paper PDFs without appropriate permission. None are intentionally included in this candidate.

This is research prototype code. Functional test coverage is bounded. No formal security, side-channel or fault-resistance guarantee is made. One DSP is a resource objective, not proof of minimum area or energy.
