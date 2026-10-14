"""Build a separate RV32IM-fast phase-instrumented copy; never rewrite the baseline."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build/mlkem512_profile'
RESULTS = ROOT / 'results/official_baseline/mlkem512/profile'
TOOLS = Path('E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin')

# Existing function boundaries; scalar Montgomery/Barrett helpers remain inline
# within NTT/INTT/basemul so the measured program is not flooded with markers.
GROUPS = [
    ('kem.c', 'api_control', 'mlk_kem_keypair_derand mlk_kem_enc_derand mlk_kem_dec mlk_kem_check_pk mlk_kem_check_sk'),
    ('indcpa.c', 'kpke_control', 'mlk_indcpa_keypair_derand mlk_indcpa_enc mlk_indcpa_dec'),
    ('indcpa.c', 'matrix_control', 'mlk_gen_matrix'),
    ('sampling.c', 'rejection_sampling', 'mlk_rej_uniform'),
    ('poly_k.c', 'noise_control', 'mlk_poly_getnoise_eta1_4x mlk_poly_getnoise_eta2 mlk_poly_getnoise_eta1122_4x'),
    ('sampling.c', 'noise_cbd', 'mlk_poly_cbd2 mlk_poly_cbd3'),
    ('fips202/keccakf1600.c', 'keccak_permutation', 'mlk_keccakf1600_permute'),
    ('fips202/fips202.c', 'sha_sponge', 'mlk_shake128_absorb_once mlk_shake128_squeezeblocks mlk_shake256 mlk_sha3_256 mlk_sha3_512'),
    ('fips202/fips202x4.c', 'sha_sponge', 'mlk_shake128x4_absorb_once mlk_shake128x4_squeezeblocks mlk_shake256x4'),
    ('poly.c', 'ntt', 'mlk_poly_ntt'),
    ('poly.c', 'intt', 'mlk_poly_invntt_tomont'),
    ('poly_k.c', 'basemul_acc', 'mlk_polyvec_basemul_acc_montgomery_cached'),
    ('poly.c', 'mulcache', 'mlk_poly_mulcache_compute'),
    ('poly.c', 'explicit_reduce_convert', 'mlk_poly_reduce mlk_poly_tomont'),
    ('poly.c', 'poly_add_sub', 'mlk_poly_add mlk_poly_sub'),
    ('compress.c', 'compression', 'mlk_poly_compress_d4 mlk_poly_compress_d10'),
    ('compress.c', 'decompression', 'mlk_poly_decompress_d4 mlk_poly_decompress_d10'),
    ('compress.c', 'encoding', 'mlk_poly_tobytes mlk_poly_frombytes mlk_poly_frommsg mlk_poly_tomsg'),
    ('verify.h', 'zeroize', 'mlk_zeroize'),
    ('runtime.c', 'memory_copy', 'memcpy'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(test, message):
    if not test:
        raise ValueError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def body_offsets(text, name):
    # Blank comments/strings without changing positions before balancing C and
    # contract parentheses. Reject prototypes/calls; only accept a following body.
    cleaned = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                     lambda m: ' ' * len(m[0]), text, flags=re.S)
    def after_paren(pos):
        require(cleaned[pos] == '(', 'Expected opening parenthesis')
        depth = 0
        for i in range(pos, len(cleaned)):
            depth += (cleaned[i] == '(') - (cleaned[i] == ')')
            if depth == 0:
                return i + 1
        raise ValueError('Unbalanced C parentheses')
    found = []
    for m in re.finditer(r'\b' + re.escape(name) + r'\s*\(', cleaned):
        pos = after_paren(cleaned.index('(', m.start()))
        while pos < len(cleaned) and cleaned[pos].isspace(): pos += 1
        if cleaned.startswith('__contract__', pos):
            pos = after_paren(cleaned.index('(', pos))
            while pos < len(cleaned) and cleaned[pos].isspace(): pos += 1
        if pos < len(cleaned) and cleaned[pos] == '{':
            found.append(pos + 1)
    require(len(found) == 1, f'Expected exactly one definition of {name}, found {len(found)}')
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool-dir', type=Path, default=TOOLS)
    args = parser.parse_args()
    baseline = ROOT / 'results/official_baseline/mlkem512'
    baseline_manifest = json.loads((baseline / 'build_manifest.json').read_text(encoding='utf-8'))
    original = next(b for b in baseline_manifest if b['isa'] == 'rv32im')
    # All frozen firmware/library/fixture inputs must still match before creating copies.
    for name, digest in original['source_sha256'].items():
        require(sha(ROOT / name) == digest, f'Baseline changed: {name}')
    vendor = ROOT / 'third_party/mlkem-native'
    vm = json.loads((vendor / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    generated = BUILD / 'generated'
    lib = generated / 'mlkem'
    for entry in vm['files']:
        path = vendor / entry['path']
        require(sha(path) == entry['sha256'], f'Vendor changed: {path}')
        if entry['path'].startswith('mlkem/'):
            dst = generated / entry['path']
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(path.read_bytes())
    common = ROOT / 'firmware/mlkem_baseline'
    runtime = generated / 'runtime.c'
    runtime.write_bytes((common / 'runtime.c').read_bytes())
    originals = {}
    phase_map = [dict(id=0, name='unclassified', category='unclassified', source='', function='')]
    for rel, category, names in GROUPS:
        path = runtime if rel == 'runtime.c' else lib / 'src' / rel
        text = path.read_text(encoding='utf-8')
        originals.setdefault(path, text)
        for name in names.split():
            phase = len(phase_map)
            offset = body_offsets(text, name)
            text = text[:offset] + f'\n  PROFILE_SCOPE({phase}); /* profiling-only boundary */\n' + text[offset:]
            source = 'firmware/mlkem_baseline/runtime.c' if rel == 'runtime.c' else f'third_party/mlkem-native/mlkem/src/{rel}'
            phase_map.append(dict(id=phase, name=name.removeprefix('mlk_'), category=category, source=source, function=name))
        path.write_text(text, encoding='utf-8', newline='\n')
    require(len(phase_map) <= 64, 'Too many phases for the passive monitor')
    # Driver is generated from the unchanged official driver, with only hook gating.
    driver_src = ROOT / 'firmware/mlkem512_suite/kat_suite.c'
    driver = generated / 'profile_main.c'
    before = driver_src.read_text(encoding='utf-8')
    text = before.replace('static uint32_t cursor;', 'static uint32_t cursor;\nvolatile uint32_t mlkem_profile_enabled;')
    for old, new in [('        start = kat_cycle();', '        start = kat_cycle();\n        mlkem_profile_enabled = 1;'),
                     ('        stop = kat_cycle();', '        mlkem_profile_enabled = 0;\n        stop = kat_cycle();')]:
        require(text.count(old) == 1, 'Driver anchor changed')
        text = text.replace(old, new)
    driver.write_text(text, encoding='utf-8', newline='\n')
    originals[driver] = before
    patches = []
    for path, before in originals.items():
        patches.extend(difflib.unified_diff(before.splitlines(True), path.read_text(encoding='utf-8').splitlines(True),
                       fromfile=path.relative_to(generated).as_posix(), tofile=path.relative_to(generated).as_posix()))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / 'instrumentation.patch').write_text(''.join(patches), encoding='utf-8', newline='\n')
    profile = ROOT / 'firmware/mlkem512_profile'
    def tool(name):
        p = args.tool_dir / f'riscv64-unknown-elf-{name}.exe'
        require(p.is_file(), f'Missing compiler tool: {p}')
        return p
    def run(command):
        proc = subprocess.run(list(map(str, command)), cwd=ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        require(proc.returncode == 0, f'Command failed: {command}\n{proc.stdout}')
        return proc.stdout
    flags = original['flags'][:original['flags'].index('-I')]
    flags += ['-I', str(profile), '-I', str(common), '-I', str(lib),
              '-DMLK_CONFIG_FILE=<mlkem_config.h>', '-include', str(profile / 'profile_protocol.h')]
    sources = [common / 'startup.S', driver, runtime] + sorted((lib / 'src').glob('*.c')) + sorted((lib / 'src/fips202').glob('*.c'))
    out = BUILD / 'firmware'
    out.mkdir(parents=True, exist_ok=True)
    logs, commands, objects = [], [], []
    for src in sources:
        obj = out / (src.stem + '.o')
        # C declarations must not be force-included in the assembly startup.
        sf = flags[:-2] if src.suffix == '.S' else flags
        command = [tool('gcc'), *sf, '-c', src, '-o', obj]
        logs.append(run(command)); commands.append(list(map(str, command))); objects.append(obj)
    elf, binary = out / 'mlkem512_profile.elf', out / 'mlkem512_profile.bin'
    cmd = [tool('gcc'), *flags, '-nostdlib', '-nostartfiles', '-Wl,--build-id=none', '-Wl,--gc-sections',
           f'-Wl,-Map,{out / "mlkem512_profile.map"}', '-T', common / 'link.ld', *objects, '-lgcc', '-o', elf]
    logs.append(run(cmd)); commands.append(list(map(str, cmd)))
    (out / 'build.txt').write_text('\n'.join(logs), encoding='utf-8')
    symbols_text = run([tool('nm'), '-n', elf])
    symbols = {m[3]: int(m[1], 16) for line in symbols_text.splitlines()
               if (m := re.fullmatch(r'([0-9a-fA-F]+)\s+(\w)\s+(\S+)', line))}
    require(not run([tool('nm'), '-u', elf]).strip(), 'Unresolved symbols')
    require(symbols['_start'] == 0 and symbols['__stack_top'] == 65520 and
            symbols['__image_end'] <= symbols['__stack_bottom'] == 49136, 'Memory layout changed')
    for kind, args2 in [('disassembly.txt', ['objdump', '-d']), ('size.txt', ['size', '-A']), ('attributes.txt', ['readelf', '-A'])]:
        (out / kind).write_text(run([tool(args2[0]), *args2[1:], elf]), encoding='ascii')
    (out / 'symbols.txt').write_text(symbols_text, encoding='ascii')
    run([tool('objcopy'), '-O', 'binary', elf, binary])
    data = binary.read_bytes()
    image = ROOT / 'firmware/images/mlkem512_profile/rv32im.mem'
    image.parent.mkdir(parents=True, exist_ok=True)
    padded = data + bytes(65536 - len(data))
    image.write_text(''.join(f'{int.from_bytes(padded[n:n+4], "little"):08x}\n' for n in range(0,65536,4)), encoding='ascii', newline='\n')
    originals_inputs = [Path(__file__), profile / 'profile_protocol.h', profile / 'mlkem_config.h', driver_src,
                       common / 'startup.S', common / 'runtime.c', common / 'link.ld', common / 'kat_protocol.h', vendor / 'SOURCE_MANIFEST.json']
    originals_inputs += [vendor / e['path'] for e in vm['files']]
    fixed = ['results/official_baseline/mlkem512/build_manifest.json','results/official_baseline/mlkem512/cases.csv',
             'results/official_baseline/mlkem512/summary.json','firmware/images/mlkem512_suite/rv32im.mem',
             'tb/software/mlkem512_suite/cases.json','tb/software/mlkem512_suite/mlkem512_input.mem',
             'tb/software/mlkem512_suite/mlkem512_expected.mem','rtl/cpu/picorv32.v','rtl/benchmark/cpu_benchmark_system.v']
    record = dict(isa='rv32im',config='rv32im_fast',compiler=run([tool('gcc'),'--version']).splitlines()[0],
        flags=flags,commands=commands,ram_bytes=65536,stack_top=65520,stack_bottom=49136,stack_reserved=16384,
        binary_bytes=len(data),static_end=symbols['__image_end'],firmware=image.relative_to(ROOT).as_posix(),
        firmware_sha256=sha(image),elf_sha256=sha(elf),phase_map=phase_map,
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in originals_inputs},
        baseline_paths_sha256={p:sha(ROOT/p) for p in fixed},
        generated_sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(generated.rglob('*')) if p.is_file()],
        instrumentation_patch_sha256=sha(RESULTS/'instrumentation.patch'),
        notes='Nested MMIO markers include observation and compiler perturbation. Exclusive cycles partition profiled API; inclusive times overlap. No accelerator traffic measured.')
    save(RESULTS / 'build_manifest.json', record)
    save(RESULTS / 'phase_map.json', phase_map)
    (RESULTS / 'stack_frames.txt').write_text('\n'.join(p.read_text() for p in sorted(out.glob('*.su'))), encoding='utf-8')
    print(f'PROFILE_BUILD_PASS image_bytes={len(data)} static_end={symbols["__image_end"]} phases={len(phase_map)}')


if __name__ == '__main__':
    main()
