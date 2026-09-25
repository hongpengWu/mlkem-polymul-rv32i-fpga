"""Build official-suite firmware with only cached BaseMul routed to MMIO.
Compilation/link validation only; this command does not run official KAT.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tool-dir',type=Path,default=Path('E:/Xilinx/Vivado/2024.2/gnu/riscv/nt/riscv64-unknown-elf/bin'))
    args=p.parse_args()
    vendor=ROOT/'third_party/mlkem-native'; lib=vendor/'mlkem'
    common=ROOT/'firmware/mlkem_baseline'; suite=ROOT/'firmware/mlkem512_suite'
    accel=ROOT/'firmware/mlkem512_accel'; out=ROOT/'build/mlkem512_accel/kat'
    out.mkdir(parents=True,exist_ok=True)
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=json.loads((vendor/'SOURCE_MANIFEST.json').read_text())
    for entry in manifest['files']:
        if digest(vendor/entry['path'])!=entry['sha256']: raise RuntimeError('Vendor changed: '+entry['path'])
    def tool(name): return args.tool_dir/f'riscv64-unknown-elf-{name}.exe'
    def run(cmd):
        result=subprocess.run(list(map(str,cmd)),cwd=ROOT,text=True,capture_output=True)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        return result.stdout
    flags=['-march=rv32im','-mabi=ilp32','-O3','-std=c11','-ffreestanding','-fno-builtin','-fno-pic','-msmall-data-limit=0','-ffunction-sections','-fdata-sections','-fno-tree-loop-distribute-patterns','-fstack-usage','-Wall','-Wextra','-Werror','-I',suite,'-I',common,'-I',lib,'-I',accel,'-DMLK_CONFIG_FILE=<mlkem_config.h>']
    sources=[common/'startup.S',suite/'kat_suite.c',common/'runtime.c',accel/'basemul_mmio.c',accel/'native_basemul.c']+sorted((lib/'src').glob('*.c'))+sorted((lib/'src/fips202').glob('*.c'))
    objects=[]; commands=[]
    for source in sources:
        obj=out/(source.stem+'.o')
        hook=['-include',accel/'native_basemul.h'] if source.name=='poly_k.c' else []
        cmd=[tool('gcc'),*flags,*hook,'-c',source,'-o',obj]
        run(cmd); commands.append(list(map(str,cmd))); objects.append(obj)
    elf=out/'mlkem512_accel.elf'; binary=out/'mlkem512_accel.bin'
    cmd=[tool('gcc'),*flags,'-nostdlib','-nostartfiles','-Wl,--build-id=none','-Wl,--gc-sections','-T',common/'link.ld',*objects,'-lgcc','-o',elf]
    run(cmd); commands.append(list(map(str,cmd)))
    if run([tool('nm'),'-u',elf]).strip(): raise RuntimeError('Unresolved symbols')
    symbols=run([tool('nm'),'-n',elf]); (out/'symbols.txt').write_text(symbols,encoding='ascii')
    for name in ['mlk_polyvec_basemul_acc_montgomery_cached_k2_native','mlkem512_basemul_mmio','pico_mlkem512_keypair_derand','pico_mlkem512_enc_derand','pico_mlkem512_dec']:
        if name not in symbols: raise RuntimeError('Missing symbol: '+name)
    reloc=run([tool('objdump'),'-dr',out/'poly_k.o'])
    if 'R_RISCV_CALL_PLT\tmlk_polyvec_basemul_acc_montgomery_cached_k2_native' not in reloc:
        raise RuntimeError('Library does not call the hardware hook')
    run([tool('objcopy'),'-O','binary',elf,binary]); data=binary.read_bytes()
    assert len(data)<=0xbff0
    image=ROOT/'firmware/images/mlkem512_accel/kat.mem'; image.parent.mkdir(parents=True,exist_ok=True)
    padded=data+bytes(65536-len(data))
    image.write_text(''.join(f'{int.from_bytes(padded[i:i+4],"little"):08x}\n' for i in range(0,len(padded),4)),encoding='ascii',newline='\n')
    evidence=ROOT/'results/accelerator_cpu'; evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'kat_hook_link.txt').write_text(reloc,encoding='ascii')
    inputs=sources+[accel/'native_basemul.h',accel/'basemul_mmio.h',common/'link.ld',suite/'mlkem_config.h',Path(__file__)]
    (evidence/'kat_build.json').write_text(json.dumps({'status':'BUILD_LINK_PASS_NOT_EXECUTED','isa':'rv32im','binary_bytes':len(data),'ram_bytes':65536,'native_hook_linked':True,'vendor_sha256_verified':True,'firmware_sha256':digest(image),'compiler':run([tool('gcc'),'--version']).splitlines()[0],'commands':commands,'source_sha256':{x.relative_to(ROOT).as_posix():digest(x) for x in inputs}},indent=2)+'\n',encoding='utf-8')
    print(f'ACCEL_KAT_BUILD_LINK_PASS image_bytes={len(data)} official_execution=pending')

if __name__=='__main__': main()
