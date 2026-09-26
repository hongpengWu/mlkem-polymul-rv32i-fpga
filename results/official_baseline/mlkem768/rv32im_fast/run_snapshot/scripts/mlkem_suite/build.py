"""Build parameterized ML-KEM CPU-only KAT firmware for RV32I/RV32IM."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path('E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin')
M_OPS = {'mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameter-set', type=int, required=True, choices=(512, 768, 1024))
    parser.add_argument('--tool-dir', type=Path, default=TOOLS)
    parser.add_argument('--ram-bytes', type=int, default=None)
    parser.add_argument('--stack-bytes', type=int, default=None)
    args = parser.parse_args()
    level = args.parameter_set
    # K=3/K=4 need more call stack than the K=2 16 KiB reservation.  Keep
    # their CPU-only correctness fixture honest by using the same 128 KiB /
    # 32 KiB memory envelope for both levels; the K=2 baseline is unchanged.
    ram_bytes = args.ram_bytes or (65536 if level == 512 else 131072)
    stack_bytes = args.stack_bytes or (16384 if level == 512 else 32768)
    require(ram_bytes > stack_bytes and ram_bytes % 4 == 0, 'RAM/stack sizes are invalid')
    vendor = ROOT / 'third_party/mlkem-native'
    lib_src = vendor / 'mlkem'
    src = ROOT / 'firmware/mlkem_suite'
    common = ROOT / 'firmware/mlkem_baseline'
    fixtures = ROOT / f'tb/software/mlkem{level}_suite'
    build = ROOT / f'build/mlkem{level}_suite'
    images = ROOT / f'firmware/images/mlkem{level}_suite'
    results = ROOT / f'results/official_baseline/mlkem{level}'
    manifest = json.loads((vendor / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        require(digest(vendor / entry['path']) == entry['sha256'], f'Vendored source changed: {entry["path"]}')

    def tool(name):
        path = args.tool_dir / ('riscv64-unknown-elf-' + name + '.exe')
        require(path.is_file(), f'Missing tool: {path}')
        return path

    def run(command):
        p = subprocess.run([str(x) for x in command], cwd=ROOT, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        require(p.returncode == 0, f'Command failed: {command}\n{p.stdout}')
        return p.stdout

    print(run([sys.executable, ROOT / 'scripts/kat/validate_acvp_json.py']).strip())
    print(run([sys.executable, ROOT / 'scripts/kat/package_mlkem.py', '--parameter-set', str(level)]).strip())
    images.mkdir(parents=True, exist_ok=True); results.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)
    linker = build / 'link.ld'
    linker.write_text(f'''ENTRY(_start)\nMEMORY {{ ram (rwx) : ORIGIN = 0, LENGTH = {ram_bytes} }}\n'''
                      f'''__stack_top = ORIGIN(ram) + LENGTH(ram) - 16;\n__stack_bottom = __stack_top - {stack_bytes};\n'''
                      '''SECTIONS {\n .text : { KEEP(*(.text.startup.boot)) *(.text.startup*) *(.text*) } > ram\n'''
                      ''' .rodata : ALIGN(4) { *(.rodata*) *(.srodata*) } > ram\n'''
                      ''' .data : ALIGN(4) { __global_pointer$ = . + 0x800; *(.sdata*) *(.data*) } > ram\n'''
                      ''' .bss (NOLOAD) : ALIGN(4) { __bss_start = .; *(.sbss*) *(.bss*) *(COMMON) . = ALIGN(4); __bss_end = .; } > ram\n'''
                      ''' __image_end = .; ASSERT(_start == ORIGIN(ram), "KAT reset entry must be at address zero")\n'''
                      ''' ASSERT(__image_end <= __stack_bottom, "KAT image overlaps reserved stack")\n'''
                      ''' /DISCARD/ : { *(.comment) *(.eh_frame*) }\n}\n''', encoding='ascii')
    version = run([tool('gcc'), '--version']).splitlines()[0]
    sources = [common / 'startup.S', src / 'kat_suite.c', common / 'runtime.c']
    sources += sorted((lib_src / 'src').glob('*.c')) + sorted((lib_src / 'src/fips202').glob('*.c'))
    records = []
    for isa in ('rv32i', 'rv32im'):
        out = build / isa; out.mkdir(parents=True, exist_ok=True)
        flags = [f'-march={isa}', '-mabi=ilp32', '-O3', '-std=c11', '-ffreestanding', '-fno-builtin', '-fno-pic',
                 '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections', '-fno-tree-loop-distribute-patterns',
                 '-fstack-usage', '-Wall', '-Wextra', '-Werror', '-I', str(src), '-I', str(common), '-I', str(lib_src),
                 '-DMLK_CONFIG_FILE=<mlkem_config.h>', f'-DMLKEM_LEVEL={level}', f'-DMLKEM_NAMESPACE=pico_mlkem{level}']
        objects, logs, commands = [], [], []
        for path in sources:
            obj = out / (path.stem + '.o')
            command = [tool('gcc'), *flags, '-c', path, '-o', obj]
            logs.append(run(command)); commands.append([str(x) for x in command]); objects.append(obj)
        elf = out / f'mlkem{level}.elf'; binary = out / f'mlkem{level}.bin'
        command = [tool('gcc'), *flags, '-nostdlib', '-nostartfiles', '-Wl,--build-id=none', '-Wl,--gc-sections',
                   f'-Wl,-Map,{out / f"mlkem{level}.map"}', '-T', linker, *objects, '-lgcc', '-o', elf]
        logs.append(run(command)); commands.append([str(x) for x in command])
        (out / 'build.txt').write_text('\n'.join(logs), encoding='utf-8')
        dump = run([tool('objdump'), '-d', elf]); (out / 'disassembly.txt').write_text(dump, encoding='ascii')
        attrs = run([tool('readelf'), '-A', elf]); (out / 'attributes.txt').write_text(attrs, encoding='ascii')
        require('rv32i' in attrs and (('m2p0' in attrs) == (isa == 'rv32im')), f'ELF ISA mismatch for {isa}')
        size = run([tool('size'), '-A', elf]); (out / 'size.txt').write_text(size, encoding='ascii')
        nm = run([tool('nm'), '-n', elf]); (out / 'symbols.txt').write_text(nm, encoding='ascii')
        require(not run([tool('nm'), '-u', elf]).strip(), 'Unresolved symbols')
        symbols = {m[3]: int(m[1], 16) for line in nm.splitlines() if (m := re.fullmatch(r'([0-9a-fA-F]+)\s+(\w)\s+(\S+)', line))}
        require(symbols['_start'] == 0 and symbols['__image_end'] <= symbols['__stack_bottom'], 'RAM/stack overlap')
        counts = {}; function = ''; by_function = {}
        for line in dump.splitlines():
            if match := re.match(r'[0-9a-f]+ <([^>]+)>:', line): function = match[1]
            if match := re.match(r'\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(\S+)', line):
                op = match[1]; counts[op] = counts.get(op, 0) + 1
                if op in M_OPS: by_function[function] = by_function.get(function, 0) + 1
        m_count = sum(counts.get(op, 0) for op in M_OPS)
        require((m_count == 0) if isa == 'rv32i' else (m_count > 0), f'Incorrect M instruction count for {isa}')
        run([tool('objcopy'), '-O', 'binary', elf, binary])
        data = binary.read_bytes(); require(len(data) <= symbols['__stack_bottom'], 'Binary exceeds RAM reservation')
        data += bytes(ram_bytes - len(data)); image = images / f'{isa}.mem'
        image.write_text(''.join(f'{int.from_bytes(data[n:n+4], "little"):08x}\n' for n in range(0, len(data), 4)), encoding='ascii')
        record = dict(parameter_set=level, isa=isa, compiler=version, ram_bytes=ram_bytes, stack_reserved=stack_bytes,
                      binary_bytes=len(binary.read_bytes()), static_end=symbols['__image_end'], stack_top=symbols['__stack_top'],
                      stack_bottom=symbols['__stack_bottom'], firmware=image.relative_to(ROOT).as_posix(), firmware_sha256=digest(image),
                      elf_sha256=digest(elf), instruction_counts=counts, static_m_instructions=m_count,
                      m_instructions_by_function=by_function)
        records.append(record)
        print(f'MLKEM{level}_FIRMWARE_PASS isa={isa} image_bytes={record["binary_bytes"]} static_end={record["static_end"]} stack_reserved={stack_bytes} m_instructions={m_count}')
    (results / 'build_manifest.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
