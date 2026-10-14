"""Build the SAME C baseline for RV32I and RV32IM, with inspectable evidence."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOLS = Path('E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin')
M_OPS = {'mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu'}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool-dir', type=Path, default=DEFAULT_TOOLS)
    args = parser.parse_args()
    def tool(name):
        path = args.tool_dir/('riscv64-unknown-elf-' + name + '.exe')
        if not path.is_file():
            raise RuntimeError(f'Missing tool: {path}')
        return str(path)
    def run(command):
        result = subprocess.run([str(x) for x in command], cwd=ROOT, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        return result.stdout
    src = ROOT/'firmware/cpu_baseline'
    image_dir = ROOT/'firmware/images/cpu_baseline'
    image_dir.mkdir(parents=True, exist_ok=True)
    build = ROOT/'build/cpu_baseline/firmware'
    build.mkdir(parents=True, exist_ok=True)
    version = run([tool('gcc'), '--version']).splitlines()[0]
    records = []
    for isa in ['rv32i', 'rv32im']:
        out = build/isa
        out.mkdir(parents=True, exist_ok=True)
        flags = [f'-march={isa}', '-mabi=ilp32', '-O3', '-ffreestanding', '-fno-builtin',
                 '-fno-pic', '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections',
                 '-fno-tree-loop-distribute-patterns', '-fstack-usage', '-Wall', '-Wextra', '-Werror']
        objects, commands, logs = [], [], []
        for name in ['startup.S', 'benchmark.c', 'poly_ntt.c']:
            obj = out/(Path(name).stem+'.o')
            command = [tool('gcc'), *flags, '-I', src, '-c', src/name, '-o', obj]
            logs.append(run(command)); commands.append([str(x) for x in command]); objects.append(obj)
        elf, binary = out/'cpu_baseline.elf', out/'cpu_baseline.bin'
        command = [tool('gcc'), *flags, '-nostdlib', '-nostartfiles', '-Wl,--build-id=none',
                   '-Wl,--gc-sections', f'-Wl,-Map,{out/"cpu_baseline.map"}',
                   '-T', src/'link.ld', *objects, '-lgcc', '-o', elf]
        logs.append(run(command)); commands.append([str(x) for x in command])
        (out/'build.txt').write_text('\n'.join(logs), encoding='utf-8')
        dump = run([tool('objdump'), '-d', elf])
        (out/'disassembly.txt').write_text(dump, encoding='ascii')
        attrs = run([tool('readelf'), '-A', elf])
        (out/'attributes.txt').write_text(attrs, encoding='ascii')
        (out/'size.txt').write_text(run([tool('size'), '-A', elf]), encoding='ascii')
        nm = run([tool('nm'), '-n', elf])
        (out/'symbols.txt').write_text(nm, encoding='ascii')
        symbols = {m[3]: int(m[1], 16) for line in nm.splitlines()
                   if (m := re.fullmatch(r'([0-9a-fA-F]+)\s+(\w)\s+(\S+)', line))}
        assert symbols['_start'] == 0 and symbols['__stack_top'] == 0x3ff0
        assert symbols['__image_end'] <= symbols['__stack_bottom'] == 0x37f0
        counts, by_function = {}, {}
        function = ''
        for line in dump.splitlines():
            if match := re.match(r'[0-9a-f]+ <([^>]+)>:', line):
                function = match[1]
            if match := re.match(r'\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(\S+)', line):
                op = match[1]
                counts[op] = counts.get(op, 0)+1
                if op in M_OPS:
                    by_function[function] = by_function.get(function, 0)+1
        m_count = sum(counts.get(op, 0) for op in M_OPS)
        assert (m_count == 0) if isa == 'rv32i' else (m_count > 0)
        if isa == 'rv32im':
            for function in ['sw_ntt', 'sw_basemul', 'sw_invntt']:
                assert by_function.get(function, 0) > 0, f'No M instructions in {function}'
        run([tool('objcopy'), '-O', 'binary', elf, binary])
        data = binary.read_bytes()
        assert len(data) <= symbols['__stack_bottom']
        data += bytes(16384-len(data))
        image = image_dir/(isa+'.mem')
        image.write_text(''.join(f'{int.from_bytes(data[n:n+4], "little"):08x}\n'
                                 for n in range(0, len(data), 4)), encoding='ascii')
        libgcc = Path(run([tool('gcc'), f'-march={isa}', '-mabi=ilp32', '-print-libgcc-file-name']).strip())
        record = dict(isa=isa, compiler=version, flags=flags, commands=commands,
                      ram_bytes=16384, binary_bytes=len(binary.read_bytes()),
                      static_end=symbols['__image_end'], stack_top=symbols['__stack_top'],
                      stack_bottom=symbols['__stack_bottom'], stack_reserved=2048,
                      instruction_counts=counts, static_m_instructions=m_count,
                      m_instructions_by_function=by_function,
                      firmware=image.relative_to(ROOT).as_posix(), firmware_sha256=digest(image),
                      libgcc_path=str(libgcc), libgcc_sha256=digest(libgcc),
                      source_sha256={p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(src.iterdir())
                                     if p.suffix in ['.c', '.h', '.S', '.ld']})
        (out/'build.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
        records.append(record)
        print(f'CPU_FIRMWARE_PASS isa={isa} image_bytes={len(binary.read_bytes())} '
              f'static_end={symbols["__image_end"]} stack_reserved=2048 m_instructions={m_count}')
    (build/'builds.json').write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')
    # Keep the compiler, source, image and libgcc hashes beside the committed
    # measurements.  The detailed ELF/objdump files remain local build output.
    evidence = ROOT/'results/cpu_baseline/cpu_baseline_build_manifest.json'
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')

if __name__ == '__main__':
    main()
