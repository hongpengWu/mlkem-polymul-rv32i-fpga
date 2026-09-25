"""Build the complete deterministic ML-KEM-512 suite for RV32I and RV32IM."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path('E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin')
M_OPS = {'mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu'}
RAM_BYTES = 65536
RESULTS = ROOT / 'results/official_baseline/mlkem512'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool-dir', type=Path, default=TOOLS)
    args = parser.parse_args()
    vendor = ROOT / 'third_party/mlkem-native'
    src = ROOT / 'firmware/mlkem512_suite'
    common = ROOT / 'firmware/mlkem_baseline'
    fixtures = ROOT / 'tb/software/mlkem512_suite'
    build = ROOT / 'build/mlkem512_suite'
    images = ROOT / 'firmware/images/mlkem512_suite'
    manifest = json.loads((vendor / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        require(digest(vendor / entry['path']) == entry['sha256'],
                f"Vendored source changed: {entry['path']}")

    def run(command):
        p = subprocess.run([str(x) for x in command], cwd=ROOT, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        require(p.returncode == 0, f'Command failed: {command}\n{p.stdout}')
        return p.stdout

    print(run([sys.executable, ROOT / 'scripts/kat/validate_acvp_json.py']).strip())
    print(run([sys.executable, ROOT / 'scripts/kat/package_mlkem512.py']).strip())

    def tool(name):
        path = args.tool_dir / ('riscv64-unknown-elf-' + name + '.exe')
        require(path.is_file(), f'Missing tool: {path}')
        return path

    images.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    version = run([tool('gcc'), '--version']).splitlines()[0]
    lib_src = vendor / 'mlkem'
    sources = [common / 'startup.S', src / 'kat_suite.c', common / 'runtime.c']
    sources += sorted((lib_src / 'src').glob('*.c'))
    sources += sorted((lib_src / 'src/fips202').glob('*.c'))
    records = []
    for isa in ['rv32i', 'rv32im']:
        out = build / isa
        out.mkdir(parents=True, exist_ok=True)
        flags = [f'-march={isa}', '-mabi=ilp32', '-O3', '-std=c11', '-ffreestanding',
                 '-fno-builtin', '-fno-pic', '-msmall-data-limit=0',
                 '-ffunction-sections', '-fdata-sections',
                 '-fno-tree-loop-distribute-patterns', '-fstack-usage',
                 '-Wall', '-Wextra', '-Werror', '-I', str(src), '-I', str(common),
                 '-I', str(lib_src), '-DMLK_CONFIG_FILE=<mlkem_config.h>']
        objects, commands, logs = [], [], []
        for path in sources:
            obj = out / (path.stem + '.o')
            command = [tool('gcc'), *flags, '-c', path, '-o', obj]
            logs.append(run(command))
            commands.append([str(x) for x in command])
            objects.append(obj)
        elf, binary = out / 'mlkem512.elf', out / 'mlkem512.bin'
        command = [tool('gcc'), *flags, '-nostdlib', '-nostartfiles',
                   '-Wl,--build-id=none', '-Wl,--gc-sections',
                   f'-Wl,-Map,{out / "mlkem512.map"}', '-T', common / 'link.ld',
                   *objects, '-lgcc', '-o', elf]
        logs.append(run(command))
        commands.append([str(x) for x in command])
        (out / 'build.txt').write_text('\n'.join(logs), encoding='utf-8')
        dump = run([tool('objdump'), '-d', elf])
        (out / 'disassembly.txt').write_text(dump, encoding='ascii')
        attrs = run([tool('readelf'), '-A', elf])
        require('rv32i' in attrs and (('m2p0' in attrs) == (isa == 'rv32im')), 'ELF ISA mismatch')
        (out / 'attributes.txt').write_text(attrs, encoding='ascii')
        size = run([tool('size'), '-A', elf])
        (out / 'size.txt').write_text(size, encoding='ascii')
        nm = run([tool('nm'), '-n', elf])
        (out / 'symbols.txt').write_text(nm, encoding='ascii')
        require(not run([tool('nm'), '-u', elf]).strip(), 'Unresolved symbols')
        symbols = {m[3]: int(m[1], 16) for line in nm.splitlines()
                   if (m := re.fullmatch(r'([0-9a-fA-F]+)\s+(\w)\s+(\S+)', line))}
        require(symbols['_start'] == 0 and symbols['__stack_top'] == 0xfff0,
                'Reset entry or stack top mismatch')
        require(symbols['__image_end'] <= symbols['__stack_bottom'] == 0xbff0,
                'Static image overlaps the 16 KiB stack')
        counts, by_function = {}, {}
        function = ''
        for line in dump.splitlines():
            if match := re.match(r'[0-9a-f]+ <([^>]+)>:', line):
                function = match[1]
            if match := re.match(r'\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(\S+)', line):
                op = match[1]
                counts[op] = counts.get(op, 0) + 1
                if op in M_OPS:
                    by_function[function] = by_function.get(function, 0) + 1
        m_count = sum(counts.get(op, 0) for op in M_OPS)
        require((m_count == 0) if isa == 'rv32i' else (m_count > 0),
                f'Incorrect M instruction count for {isa}: {m_count}')
        for api in ['keypair_derand', 'enc_derand', 'dec', 'check_pk', 'check_sk']:
            require('pico_mlkem512_' + api in symbols, 'Missing real API: ' + api)
        run([tool('objcopy'), '-O', 'binary', elf, binary])
        data = binary.read_bytes()
        require(len(data) <= symbols['__stack_bottom'], 'Binary exceeds memory reservation')
        data += bytes(RAM_BYTES - len(data))
        image = images / (isa + '.mem')
        image.write_text(''.join(f'{int.from_bytes(data[n:n+4], "little"):08x}\n'
                                 for n in range(0, len(data), 4)), encoding='ascii')
        libgcc = Path(run([tool('gcc'), f'-march={isa}', '-mabi=ilp32',
                           '-print-libgcc-file-name']).strip())
        stack_usage = '\n'.join(p.read_text() for p in sorted(out.glob('*.su')))
        (RESULTS / f'{isa}_stack_frames.txt').write_text(stack_usage, encoding='utf-8')
        (RESULTS / f'{isa}_size.txt').write_text(size, encoding='ascii')
        source_inputs = list(src.glob('*')) + list(fixtures.glob('*'))
        source_inputs += [common / n for n in ['startup.S', 'runtime.c', 'kat_protocol.h', 'link.ld']]
        source_inputs += [Path(__file__), ROOT / 'scripts/kat/package_mlkem512.py']
        source_inputs += [vendor / e['path'] for e in manifest['files']]
        record = dict(isa=isa, compiler=version, flags=flags, commands=commands,
                      ram_bytes=RAM_BYTES, binary_bytes=len(binary.read_bytes()),
                      static_end=symbols['__image_end'], stack_top=symbols['__stack_top'],
                      stack_bottom=symbols['__stack_bottom'], stack_reserved=16384,
                      instruction_counts=counts, static_m_instructions=m_count,
                      m_instructions_by_function=by_function,
                      firmware=image.relative_to(ROOT).as_posix(), firmware_sha256=digest(image),
                      elf_sha256=digest(elf), libgcc_path=str(libgcc), libgcc_sha256=digest(libgcc),
                      mlkem_native_commit=manifest['source_commit'],
                      source_sha256={p.relative_to(ROOT).as_posix(): digest(p)
                                     for p in sorted(source_inputs) if p.is_file()})
        records.append(record)
        print(f'MLKEM_FIRMWARE_PASS isa={isa} image_bytes={record["binary_bytes"]} '
              f'static_end={record["static_end"]} stack_reserved=16384 m_instructions={m_count}')
    (RESULTS / 'build_manifest.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
