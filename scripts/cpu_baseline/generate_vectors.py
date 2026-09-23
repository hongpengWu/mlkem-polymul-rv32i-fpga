"""Independent canonical input fixtures and O(N^2) negacyclic oracle."""
from pathlib import Path
import json

Q, N = 3329, 256
ROOT = Path(__file__).resolve().parents[2]

def vectors(case):
    a, b = [0] * N, [0] * N
    if case == 0:
        b = list(range(N))
    elif case == 1:
        a[0] = 1
        b = [(17*i*i + 31*i + 7) % Q for i in range(N)]
    elif case == 2:
        a[255], b[1] = 1, 1
    elif case == 3:
        a, b = [Q-1] * N, [Q-1] * N
    elif case == 4:
        a = [0 if i % 2 else Q-1 for i in range(N)]
        b = [Q-1 if i % 2 else 1 for i in range(N)]
    elif case == 5:
        a = [(17*i*i + 31*i + 7) % Q for i in range(N)]
        b = [(29*i*i + 11*i + 19) % Q for i in range(N)]
    else:
        state = [0xc0dec0de, 0x6d6c6b65][case-6]
        for i in range(N):
            state = (state * 1664525 + 1013904223) & 0xffffffff
            a[i] = state % Q
            state = (state * 1664525 + 1013904223) & 0xffffffff
            b[i] = state % Q
    return a, b

def oracle(a, b):
    out = [0] * N
    for i, av in enumerate(a):
        for j, bv in enumerate(b):
            k = i + j
            out[k % N] += av * bv * (1 if k < N else -1)
    return [x % Q for x in out]

def checksum(values):
    # Defined rotate/xor checksum: no multiply or divide in the firmware check.
    x = 0x811c9dc5
    for v in values:
        x = (((x << 5) | (x >> 27)) ^ v) & 0xffffffff
    return x

def main():
    names = ['zero', 'identity', 'ring_wrap', 'all_q_minus_1', 'alternating',
             'dense', 'random_c0dec0de', 'random_6d6c6b65']
    words, records, hashes = [], [], []
    for case, name in enumerate(names):
        a, b = vectors(case)
        out = oracle(a, b)
        words.extend(a + b + out)
        hashes.append(checksum(out))
        records.append(dict(case=case, name=name, checksum=f'{hashes[-1]:08x}'))
    dest = ROOT/'tb/software'
    dest.mkdir(parents=True, exist_ok=True)
    (dest/'cpu_polymul_vectors.mem').write_text(''.join(f'{x:08x}\n' for x in words), encoding='ascii')
    (dest/'cpu_polymul_vectors.json').write_text(json.dumps(records, indent=2)+'\n', encoding='ascii')
    header = '#ifndef CPU_BASELINE_VECTORS_H\n#define CPU_BASELINE_VECTORS_H\n#include <stdint.h>\n'
    header += '#define CPU_BENCHMARK_CASES 8\nstatic const uint32_t expected_checksums[8] = {\n'
    header += ''.join(f'    0x{x:08x}u,\n' for x in hashes)
    header += '};\n#endif\n'
    (ROOT/'firmware/cpu_baseline/vectors.h').write_text(header, encoding='ascii')
    print('CPU_VECTORS_PASS cases=8 coefficients=256 independent_negacyclic_oracle=1')

if __name__ == '__main__':
    main()
