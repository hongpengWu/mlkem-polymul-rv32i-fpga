# ML-KEM-512 CPU + accelerator comparison

Status: **PASS** (145/145 cases)

| operation | samples | software mean/min/max | hardware mean/min/max | speedup (sum) | speedup (per sample) |
|---|---:|---:|---:|---:|---:|
| keyGen | 25 | 5269404.0/5192604/5821023 | 5298118.0/5221318/5849737 | 0.9946x | 0.9946x |
| encapsulation | 50 | 5581096.6/5529379/6157711 | 5624167.6/5572450/6200782 | 0.9923x | 0.9923x |
| decapsulation | 20 | 6937739.2/6935627/6939396 | 6995167.2/6993055/6996824 | 0.9918x | 0.9918x |
| decapsulationSeed | 10 | 12132085.4/12126794/12135778 | 12218227.4/12212936/12221920 | 0.9929x | 0.9929x |
| encapsulationKeyCheck | 20 | 128937.5/128932/128943 | 128937.5/128932/128943 | 1.0000x | 1.0000x |
| decapsulationKeyCheck | 20 | 941446.5/941441/941452 | 941446.5/941441/941452 | 1.0000x | 1.0000x |

Phase ratios use accelerated measured API cycles:

| scope | load | core | read | remaining API |
|---|---:|---:|---:|---:|
| all | 0.0207 | 0.0001 | 0.0028 | 0.9764 |
| keyGen | 0.0160 | 0.0001 | 0.0022 | 0.9817 |
| encapsulation | 0.0226 | 0.0001 | 0.0031 | 0.9742 |
| decapsulation | 0.0242 | 0.0001 | 0.0033 | 0.9724 |
| decapsulationSeed | 0.0208 | 0.0001 | 0.0029 | 0.9763 |
| encapsulationKeyCheck | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| decapsulationKeyCheck | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
