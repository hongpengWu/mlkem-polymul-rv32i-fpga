"""Build a CPU-executed MMIO smoke image; expectations remain only in RTL TB."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool-dir', type=Path, default=Path('E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin'))
    args = parser.parse_args()
    out = ROOT / 'build/mlkem512_accel'
    out.mkdir(parents=True, exist_ok=True)
    vectors = ROOT / 'tb/accelerator/vectors'
    def coeffs(c, name):
        vals = [int(v, 16) for v in (vectors / f'case_{c:03d}_{name}.mem').read_text().split()]
        return '{' + ','.join(str(v if v < 32768 else v-65536) for v in vals) + '}'
    rows=[]
    for c in range(3):
        groups=['{'+','.join(coeffs(c,n) for n in pair)+'}' for pair in [('a0','a1'),('b0','b1'),('cache0','cache1')]]
        rows.append('{'+','.join(groups)+'}')
    header=out/'smoke_inputs.h'
    header.write_text('static const struct { int16_t a[2][256], b[2][256], cache[2][128]; } smoke_inputs[3] = {\n'+',\n'.join(rows)+'\n};\n', encoding='ascii')
    def tool(name): return args.tool_dir / f'riscv64-unknown-elf-{name}.exe'
    def run(cmd):
        p = subprocess.run(list(map(str,cmd)), cwd=ROOT, capture_output=True, text=True)
        if p.returncode: raise RuntimeError(p.stdout+p.stderr)
        return p.stdout
    common=ROOT/'firmware/mlkem_baseline'; src=ROOT/'firmware/mlkem512_accel'
    elf=out/'smoke.elf'; binary=out/'smoke.bin'
    cmd=[tool('gcc'),'-march=rv32im','-mabi=ilp32','-O3','-std=c11','-ffreestanding','-fno-builtin','-fno-pic','-msmall-data-limit=0','-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles','-Wl,--build-id=none','-I',out,'-T',common/'link.ld',common/'startup.S',src/'smoke.c',src/'basemul_mmio.c','-lgcc','-o',elf]
    run(cmd); run([tool('objcopy'),'-O','binary',elf,binary])
    data=binary.read_bytes(); assert len(data)<0xbff0
    image=ROOT/'firmware/images/mlkem512_accel/smoke.mem'; image.parent.mkdir(parents=True,exist_ok=True)
    padded=data+bytes(65536-len(data))
    image.write_text(''.join(f'{int.from_bytes(padded[i:i+4],"little"):08x}\n' for i in range(0,len(padded),4)),encoding='ascii',newline='\n')
    (out/'disassembly.txt').write_text(run([tool('objdump'),'-d',elf]),encoding='ascii')
    evidence=ROOT/'results/accelerator_cpu'; evidence.mkdir(parents=True,exist_ok=True)
    source_files=[common/'startup.S',common/'link.ld',src/'smoke.c',src/'basemul_mmio.c',src/'basemul_mmio.h',Path(__file__)]+list(vectors.glob('case_*.mem'))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (evidence/'smoke_build.json').write_text(json.dumps({'scope':'CPU MMIO smoke; not official KAT or complete KEM','isa':'rv32im','ram_bytes':65536,'binary_bytes':len(data),'compiler':run([tool('gcc'),'--version']).splitlines()[0],'command':list(map(str,cmd)),'firmware_sha256':digest(image),'source_sha256':{p.relative_to(ROOT).as_posix():digest(p) for p in source_files}},indent=2)+'\n',encoding='utf-8')
    print(f'ACCEL_SMOKE_BUILD_PASS image_bytes={len(data)}')

if __name__=='__main__': main()
