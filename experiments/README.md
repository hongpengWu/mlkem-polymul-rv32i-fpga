# Historical controls

`register_wrapper/` is the old non-BRAM wrapper and tests written for its internal arrays. Its module name intentionally matches the active wrapper. Never compile both implementations together. The main scripts include only `rtl/axi/`.

These files are retained as experimental controls, not a second default project. Their fixed expectations and array hierarchy do not describe the current BRAM implementation. The old six-stage/input-preparation/transfer-loop reports remain in the original local engineering archive; only selected final evidence is included here. No historical experiment is claimed rerun merely because its source has been copied.
